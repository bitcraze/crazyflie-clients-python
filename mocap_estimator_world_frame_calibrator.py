#!/usr/bin/env python3
"""
Guided no-flight mocap/world-frame and estimator calibration logger.

This script streams VRPN mocap pose into the Crazyflie Kalman estimator, logs
stateEstimate.x/y/z against mocap x/y/z, and prompts the operator to place the
drone at known cage positions. It never arms the Crazyflie and never sends motor
or high-level-commander movement commands.
"""

import argparse
import csv
import math
import statistics
import time
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from threading import Lock
from threading import Thread


DEFAULT_URI = 'radio://0/80/2M'
DEFAULT_HOST_NAME = '192.168.1.42:3883'
DEFAULT_RIGID_BODY_NAME = 'crazyflie_21'
DEFAULT_OUTPUT_DIR = 'flight_logs'
LOG_PERIOD_MS = 100
MOCAP_TIMEOUT = 8.0
POSE_STALE_TIMEOUT = 0.30
ESTIMATE_STALE_TIMEOUT = 0.50
DEFAULT_NOSE_FRONT_YAW_DEG = -90.0
DEFAULT_MAX_LEVEL_ERROR_DEG = 5.0
DEFAULT_MAX_YAW_ERROR_DEG = 5.0
DEFAULT_MAX_SAMPLE_SPREAD_DEG = 3.0
DEFAULT_MIN_ORIENTATION_SAMPLES = 20
DEFAULT_YAW_JUMP_DEG = 45.0
DEFAULT_YAW_JUMP_MOVE_M = 0.03
DEFAULT_ORIENTATION_JUMP_DEG = 8.0
DEFAULT_MAX_ORIENTATION_REJECTION_RATIO = 0.01
DEFAULT_POSITION_CONVERGENCE_ERROR_M = 0.05
DEFAULT_POSITION_CONVERGENCE_DURATION_S = 2.0
DEFAULT_POSITION_CONVERGENCE_TIMEOUT_S = 10.0
DEFAULT_YAW_CONVERGENCE_ERROR_DEG = 5.0
DEFAULT_YAW_CONVERGENCE_DURATION_S = 1.0
DEFAULT_YAW_CONVERGENCE_TIMEOUT_S = 10.0
ROBUST_ORIENTATION_PERCENTILE = 90.0

DEFAULT_PHASES = [
    ('front', 'front of the cage'),
    ('center_after_front', 'center/start position'),
    ('back', 'back of the cage'),
    ('center_after_back', 'center/start position'),
    ('left', 'left side of the cage'),
    ('center_after_left', 'center/start position'),
    ('right', 'right side of the cage'),
    ('center_after_right', 'center/start position'),
    ('up', 'straight up to intended hover height'),
    ('center_end', 'center/start position'),
]


@dataclass(frozen=True)
class Quat:
    x: float
    y: float
    z: float
    w: float


def load_runtime_modules():
    import cflib.crtp
    import motioncapture
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    from cflib.utils.reset_estimator import reset_estimator

    return {
        'cflib_crtp': cflib.crtp,
        'motioncapture': motioncapture,
        'Crazyflie': Crazyflie,
        'LogConfig': LogConfig,
        'SyncCrazyflie': SyncCrazyflie,
        'reset_estimator': reset_estimator,
    }


class MocapState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.quat = None
        self.last_update = 0.0
        self.frame_count = 0
        self.orientation_result = {
            'orientation_packet_sequence': '',
            'orientation_packet_status': 'not-streamed',
            'orientation_rejection_reason': '',
            'orientation_accepted_count': 0,
            'extpos_fallback_count': 0,
            'orientation_rejected_count': 0,
            'corrected_mocap_roll_deg': '',
            'corrected_mocap_pitch_deg': '',
            'corrected_mocap_yaw_deg': '',
        }

    def update(self, position, quat, orientation_result=None):
        quat_copy = Quat(quat.x, quat.y, quat.z, quat.w)
        with self._lock:
            self.position = tuple(position)
            self.quat = quat_copy
            self.last_update = time.time()
            self.frame_count += 1
            if orientation_result is not None:
                self.orientation_result = dict(orientation_result)

    def snapshot(self):
        with self._lock:
            return self.position, self.quat, self.last_update, self.frame_count

    def snapshot_with_orientation(self):
        with self._lock:
            return (
                self.position,
                self.quat,
                self.last_update,
                self.frame_count,
                dict(self.orientation_result),
            )


class EstimateState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.battery_voltage = 0.0
        self.attitude = None
        self.position_last_update = 0.0
        self.attitude_last_update = 0.0

    def update_position(self, x, y, z, battery_voltage):
        with self._lock:
            self.position = (x, y, z)
            self.battery_voltage = battery_voltage
            self.position_last_update = time.time()

    def update_attitude(self, roll, pitch, yaw):
        with self._lock:
            self.attitude = (roll, pitch, yaw)
            self.attitude_last_update = time.time()

    def snapshot(self):
        with self._lock:
            return (
                self.position, self.attitude, self.battery_voltage,
                self.position_last_update, self.attitude_last_update,
            )


class MocapReader(Thread):
    def __init__(self, motioncapture_module, host_name, body_name, state):
        Thread.__init__(self)
        self.daemon = True
        self.motioncapture = motioncapture_module
        self.host_name = host_name
        self.body_name = body_name
        self.state = state
        self.on_pose = None
        self.error = None
        self._stay_open = True
        self._mc = None
        self._mc_lock = Lock()

    @staticmethod
    def _release_connection(mc):
        if mc is None:
            return
        for method_name in ('close', 'disconnect', 'shutdown'):
            method = getattr(mc, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

    def _detach_connection(self, expected=None):
        with self._mc_lock:
            if expected is not None and self._mc is not expected:
                return None
            mc = self._mc
            self._mc = None
            return mc

    def close(self):
        self._stay_open = False
        self.on_pose = None
        with self._mc_lock:
            mc = self._mc
        if mc is not None and any(
            callable(getattr(mc, method_name, None))
            for method_name in ('close', 'disconnect', 'shutdown')
        ):
            self._release_connection(self._detach_connection())

    def run(self):
        mc = None
        rigid_bodies = None
        obj = None
        pos = None
        quat = None
        try:
            mc = self.motioncapture.connect('vrpn', {'hostname': self.host_name})
            with self._mc_lock:
                self._mc = mc
            print(f"[INFO] Mocap connected, looking for '{self.body_name}'")
            found = False
            while self._stay_open:
                mc.waitForNextFrame()
                rigid_bodies = mc.rigidBodies
                for name, obj in rigid_bodies.items():
                    if name != self.body_name:
                        continue
                    if not found:
                        print(f"[INFO] Found and tracking rigid body: {name}")
                        found = True
                    pos = obj.position
                    quat = obj.rotation
                    callback = self.on_pose
                    orientation_result = None
                    if callback is not None:
                        callback(pos[0], pos[1], pos[2], quat)
                        callback_owner = getattr(callback, '__self__', None)
                        snapshot = getattr(callback_owner, 'snapshot', None)
                        if snapshot is not None:
                            orientation_result = snapshot()
                    self.state.update(
                        (pos[0], pos[1], pos[2]), quat, orientation_result
                    )
                    obj = None
                    pos = None
                    quat = None
                obj = None
                pos = None
                quat = None
                rigid_bodies = None
        except Exception as exc:
            if self._stay_open:
                self.error = exc
        finally:
            obj = None
            pos = None
            quat = None
            rigid_bodies = None
            self._release_connection(self._detach_connection(expected=mc))
            mc = None


class FilteredExtposeSender:
    def __init__(
        self,
        cf,
        body_to_cf=None,
        yaw_jump_deg=DEFAULT_YAW_JUMP_DEG,
        jump_move_m=DEFAULT_YAW_JUMP_MOVE_M,
        orientation_jump_deg=DEFAULT_ORIENTATION_JUMP_DEG,
    ):
        self.cf = cf
        self.body_to_cf = body_to_cf
        self.yaw_jump_deg = yaw_jump_deg
        self.jump_move_m = jump_move_m
        self.orientation_jump_deg = orientation_jump_deg
        self._lock = Lock()
        self.last_position = None
        self.last_yaw = None
        self.last_quat = None
        self.accepted = 0
        self.fallback = 0
        self.rejected = 0
        self.packet_sequence = 0
        self.last_status = 'not-streamed'
        self.last_rejection_reason = ''
        self.last_corrected_euler = None

    def set_body_to_cf(self, body_to_cf):
        with self._lock:
            self.body_to_cf = body_to_cf
        self.reset_orientation_baseline()

    def reset_orientation_baseline(self):
        with self._lock:
            self.last_position = None
            self.last_yaw = None
            self.last_quat = None

    def has_orientation_baseline(self):
        with self._lock:
            return self.last_yaw is not None

    def _record_result(self, status, reason=''):
        self.packet_sequence += 1
        self.last_status = status
        self.last_rejection_reason = reason
        if status == 'accepted':
            self.accepted += 1
        else:
            self.fallback += 1
            self.rejected += 1

    def snapshot(self):
        with self._lock:
            return {
                'orientation_packet_sequence': self.packet_sequence,
                'orientation_packet_status': self.last_status,
                'orientation_rejection_reason': self.last_rejection_reason,
                'orientation_accepted_count': self.accepted,
                'extpos_fallback_count': self.fallback,
                'orientation_rejected_count': self.rejected,
                'corrected_mocap_roll_deg': (
                    self.last_corrected_euler[0]
                    if self.last_corrected_euler is not None else ''
                ),
                'corrected_mocap_pitch_deg': (
                    self.last_corrected_euler[1]
                    if self.last_corrected_euler is not None else ''
                ),
                'corrected_mocap_yaw_deg': (
                    self.last_corrected_euler[2]
                    if self.last_corrected_euler is not None else ''
                ),
            }

    def send(self, x, y, z, quat):
        position = (x, y, z)
        quat = normalized_quat(quat)
        with self._lock:
            if quat is not None and self.body_to_cf is not None:
                quat = normalized_quat(multiply_quat(quat, self.body_to_cf))
            if quat is None:
                self.last_corrected_euler = None
                self.cf.extpos.send_extpos(x, y, z)
                self._record_result('rejected', 'invalid quaternion')
                return False
            self.last_corrected_euler = euler_from_quat_deg(quat)
            yaw = self.last_corrected_euler[2]
            orientation_jump = (
                quaternion_angle_deg(quat, self.last_quat)
                if self.last_quat is not None else 0.0
            )
            jump = (
                abs(angle_error_deg(yaw, self.last_yaw))
                if self.last_yaw is not None else 0.0
            )
            moved = (
                distance_3d(position, self.last_position)
                if self.last_position is not None else math.inf
            )
            if (
                self.last_quat is not None
                and orientation_jump > self.orientation_jump_deg
            ):
                reason = f'quaternion jump {orientation_jump:.1f}deg'
                self.cf.extpos.send_extpos(x, y, z)
                self._record_result('rejected', reason)
                return False
            if (
                self.last_yaw is not None
                and jump > self.yaw_jump_deg
                and moved < self.jump_move_m
            ):
                reason = f'yaw jump {jump:.1f}deg, move {moved:.3f}m'
                self.cf.extpos.send_extpos(x, y, z)
                self._record_result('rejected', reason)
                return False
            self.cf.extpos.send_extpose(
                x, y, z, quat.x, quat.y, quat.z, quat.w
            )
            self.last_position = position
            self.last_yaw = yaw
            self.last_quat = quat
            self._record_result('accepted')
            return True


class CsvLogger:
    FIELDNAMES = [
        'wall_time_s',
        'elapsed_s',
        'phase',
        'phase_elapsed_s',
        'command',
        'mocap_x',
        'mocap_y',
        'mocap_z',
        'mocap_qx',
        'mocap_qy',
        'mocap_qz',
        'mocap_qw',
        'mocap_age_s',
        'mocap_frame_count',
        'orientation_packet_sequence',
        'orientation_packet_status',
        'orientation_rejection_reason',
        'orientation_accepted_count',
        'extpos_fallback_count',
        'orientation_rejected_count',
        'corrected_mocap_roll_deg',
        'corrected_mocap_pitch_deg',
        'corrected_mocap_yaw_deg',
        'estimate_x',
        'estimate_y',
        'estimate_z',
        'estimate_roll_deg',
        'estimate_pitch_deg',
        'estimate_yaw_deg',
        'estimate_age_s',
        'estimate_attitude_age_s',
        'estimate_error_m',
        'estimate_error_x_m',
        'estimate_error_y_m',
        'estimate_error_z_m',
        'battery_v',
    ]

    def __init__(self, output_path):
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output_path.open('w', newline='')
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        self._writer.writeheader()
        self._file.flush()
        self.rows = 0

    def write(self, row):
        self._writer.writerow(row)
        self.rows += 1
        if self.rows % 10 == 0:
            self._file.flush()

    def close(self):
        self._file.flush()
        self._file.close()


def setup_estimate_loggers(cf, LogConfig, estimate_state):
    position_log = LogConfig(name='EstimatorPosition', period_in_ms=LOG_PERIOD_MS)
    position_log.add_variable('pm.vbat', 'float')
    position_log.add_variable('stateEstimate.x', 'float')
    position_log.add_variable('stateEstimate.y', 'float')
    position_log.add_variable('stateEstimate.z', 'float')

    attitude_log = LogConfig(name='EstimatorAttitude', period_in_ms=LOG_PERIOD_MS)
    attitude_log.add_variable('stateEstimate.roll', 'float')
    attitude_log.add_variable('stateEstimate.pitch', 'float')
    attitude_log.add_variable('stateEstimate.yaw', 'float')

    def on_position(timestamp, data, logconf):
        del timestamp, logconf
        estimate_state.update_position(
            data['stateEstimate.x'],
            data['stateEstimate.y'],
            data['stateEstimate.z'],
            data['pm.vbat'],
        )

    def on_attitude(timestamp, data, logconf):
        del timestamp, logconf
        estimate_state.update_attitude(
            data['stateEstimate.roll'],
            data['stateEstimate.pitch'],
            data['stateEstimate.yaw'],
        )

    def on_error(logconf, msg):
        print(f"[WARN] Logger error from {logconf.name}: {msg}")

    position_log.data_received_cb.add_callback(on_position)
    attitude_log.data_received_cb.add_callback(on_attitude)
    for logconf in (position_log, attitude_log):
        cf.log.add_config(logconf)
        logconf.error_cb.add_callback(on_error)
        logconf.start()
    return [position_log, attitude_log]


def send_extpose_or_extpos(cf, pose_mode, x, y, z, quat, body_to_cf=None):
    if pose_mode == 'extpose':
        quat = normalized_quat(quat)
        if quat is None:
            raise ValueError('Mocap quaternion is invalid')
        if body_to_cf is not None:
            quat = normalized_quat(multiply_quat(quat, body_to_cf))
        cf.extpos.send_extpose(x, y, z, quat.x, quat.y, quat.z, quat.w)
    else:
        cf.extpos.send_extpos(x, y, z)


def distance_3d(left, right):
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def wait_for_mocap(mocap_state, mocap_reader, timeout):
    print("[INFO] Waiting for fresh mocap pose...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        position, quat, last_update, frames = mocap_state.snapshot()
        if position is not None and time.time() - last_update <= POSE_STALE_TIMEOUT:
            print(
                "[MOCAP] Fresh pose: "
                f"pos=({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) "
                f"quat=({quat.x:.3f}, {quat.y:.3f}, {quat.z:.3f}, {quat.w:.3f}) "
                f"frames={frames}"
            )
            return
        time.sleep(0.05)
    raise RuntimeError("No fresh mocap pose received before timeout")


def wait_for_estimate(estimate_state, timeout):
    print("[INFO] Waiting for stateEstimate log data...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        position, attitude, battery, position_time, attitude_time = estimate_state.snapshot()
        position_fresh = position is not None and time.time() - position_time <= ESTIMATE_STALE_TIMEOUT
        attitude_fresh = attitude is not None and time.time() - attitude_time <= ESTIMATE_STALE_TIMEOUT
        if position_fresh and attitude_fresh:
            print(
                "[ESTIMATE] Fresh estimate: "
                f"pos=({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) "
                f"battery={battery:.2f}V"
            )
            return
        time.sleep(0.05)
    raise RuntimeError("No fresh stateEstimate data received before timeout")


def normalized_quat(quat):
    values = (quat.x, quat.y, quat.z, quat.w)
    if not all(math.isfinite(value) for value in values):
        return None
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1.0e-9:
        return None
    return Quat(*(value / norm for value in values))


def multiply_quat(left, right):
    return Quat(
        left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
        left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
        left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w,
        left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
    )


def conjugate_quat(quat):
    return Quat(-quat.x, -quat.y, -quat.z, quat.w)


def yaw_quat(degrees):
    half = math.radians(degrees) / 2.0
    return Quat(0.0, 0.0, math.sin(half), math.cos(half))


def euler_from_quat_deg(quat):
    roll = math.degrees(math.atan2(
        2.0 * (quat.w * quat.x + quat.y * quat.z),
        1.0 - 2.0 * (quat.x * quat.x + quat.y * quat.y),
    ))
    pitch_term = 2.0 * (quat.w * quat.y - quat.z * quat.x)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, pitch_term))))
    yaw = math.degrees(math.atan2(
        2.0 * (quat.w * quat.z + quat.x * quat.y),
        1.0 - 2.0 * (quat.y * quat.y + quat.z * quat.z),
    ))
    return roll, pitch, yaw


def angle_error_deg(actual, expected):
    return (actual - expected + 180.0) % 360.0 - 180.0


def percentile(values, percentile_value):
    values = sorted(numeric_values(values))
    if not values:
        return math.nan
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * percentile_value / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[lower]
    weight = rank - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def average_quaternions(quats):
    normalized = [normalized_quat(quat) for quat in quats]
    normalized = [quat for quat in normalized if quat is not None]
    if not normalized:
        raise ValueError('No valid mocap quaternions in calibration sample')
    reference = normalized[0]
    aligned = []
    for quat in normalized:
        dot = sum(a * b for a, b in zip(
            (reference.x, reference.y, reference.z, reference.w),
            (quat.x, quat.y, quat.z, quat.w),
        ))
        aligned.append(quat if dot >= 0.0 else Quat(-quat.x, -quat.y, -quat.z, -quat.w))
    return normalized_quat(Quat(
        statistics.fmean(quat.x for quat in aligned),
        statistics.fmean(quat.y for quat in aligned),
        statistics.fmean(quat.z for quat in aligned),
        statistics.fmean(quat.w for quat in aligned),
    ))


def quaternion_angle_deg(left, right):
    dot = abs(sum(a * b for a, b in zip(
        (left.x, left.y, left.z, left.w),
        (right.x, right.y, right.z, right.w),
    )))
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, dot))))


def robust_average_quaternions(quats):
    quats = [normalized_quat(quat) for quat in quats]
    quats = [quat for quat in quats if quat is not None]
    if not quats:
        raise ValueError('No valid mocap quaternions in calibration sample')
    medoid = min(
        quats,
        key=lambda candidate: statistics.median(
            quaternion_angle_deg(candidate, other) for other in quats
        ),
    )
    distances = [quaternion_angle_deg(medoid, quat) for quat in quats]
    distance_median = statistics.median(distances)
    mad = statistics.median(abs(value - distance_median) for value in distances)
    inlier_limit = distance_median + max(0.5, 3.0 * 1.4826 * mad)
    inliers = [
        quat for quat, distance in zip(quats, distances)
        if distance <= inlier_limit
    ]
    return average_quaternions(inliers)


def calibration_quaternions(rows, pose_stale_timeout=POSE_STALE_TIMEOUT):
    quats = []
    for row in rows:
        if row.get('orientation_packet_status', 'accepted') != 'accepted':
            continue
        age = row.get('mocap_age_s', math.inf)
        if not isinstance(age, Real) or age > pose_stale_timeout:
            continue
        values = tuple(row[name] for name in ('mocap_qx', 'mocap_qy', 'mocap_qz', 'mocap_qw'))
        if all(isinstance(value, Real) for value in values):
            quat = normalized_quat(Quat(*map(float, values)))
            if quat is not None:
                quats.append(quat)
    return quats


def compute_body_to_cf_quat(
    rows,
    nose_front_yaw_deg,
    pose_stale_timeout=POSE_STALE_TIMEOUT,
    min_samples=1,
):
    samples = calibration_quaternions(rows, pose_stale_timeout)
    if len(samples) < min_samples:
        raise RuntimeError(
            f'Only {len(samples)} fresh orientation samples; need at least '
            f'{min_samples}'
        )
    average_body = robust_average_quaternions(samples)
    expected_cf = yaw_quat(nose_front_yaw_deg)
    body_to_cf = normalized_quat(multiply_quat(conjugate_quat(average_body), expected_cf))
    spread = percentile(
        [quaternion_angle_deg(average_body, sample) for sample in samples],
        ROBUST_ORIENTATION_PERCENTILE,
    )
    return body_to_cf, average_body, spread


def verify_calibration(rows, body_to_cf, args, expected_yaw_deg=None):
    if expected_yaw_deg is None:
        expected_yaw_deg = args.nose_front_yaw_deg
    samples = calibration_quaternions(rows, args.pose_stale_timeout)
    if len(samples) < args.min_orientation_samples:
        raise RuntimeError(
            f'Only {len(samples)} fresh verification orientation samples; '
            f'need at least {args.min_orientation_samples}'
        )
    corrected = [normalized_quat(multiply_quat(sample, body_to_cf)) for sample in samples]
    eulers = [euler_from_quat_deg(quat) for quat in corrected]
    average_corrected = robust_average_quaternions(corrected)
    spread = percentile(
        [quaternion_angle_deg(average_corrected, quat) for quat in corrected],
        ROBUST_ORIENTATION_PERCENTILE,
    )
    roll_error = percentile(
        [abs(value[0]) for value in eulers], ROBUST_ORIENTATION_PERCENTILE
    )
    pitch_error = percentile(
        [abs(value[1]) for value in eulers], ROBUST_ORIENTATION_PERCENTILE
    )
    yaw_error = percentile(
        [abs(angle_error_deg(value[2], expected_yaw_deg)) for value in eulers],
        ROBUST_ORIENTATION_PERCENTILE,
    )
    fresh_estimator_rows = [
        row for row in rows
        if isinstance(row.get('estimate_attitude_age_s'), Real)
        and row['estimate_attitude_age_s'] <= ESTIMATE_STALE_TIMEOUT
    ]
    if len(fresh_estimator_rows) < args.min_orientation_samples:
        raise RuntimeError(
            f'Only {len(fresh_estimator_rows)} fresh estimator attitude samples; '
            f'need at least {args.min_orientation_samples}'
        )
    estimate_roll = median([row['estimate_roll_deg'] for row in fresh_estimator_rows])
    estimate_pitch = median([row['estimate_pitch_deg'] for row in fresh_estimator_rows])
    estimate_yaw = median([row['estimate_yaw_deg'] for row in fresh_estimator_rows])
    estimator_errors = (
        abs(estimate_roll),
        abs(estimate_pitch),
        abs(angle_error_deg(estimate_yaw, expected_yaw_deg)),
    )
    print(
        f'[VERIFY] corrected p90 roll/pitch/yaw error: '
        f'{roll_error:.2f}/{pitch_error:.2f}/{yaw_error:.2f} deg'
    )
    print(f'[VERIFY] corrected held-sample spread: {spread:.2f} deg')
    print(
        f'[VERIFY] estimator median roll/pitch/yaw: '
        f'{estimate_roll:.2f}/{estimate_pitch:.2f}/{estimate_yaw:.2f} deg'
    )
    if max(roll_error, pitch_error) > args.max_level_error_deg:
        raise RuntimeError('Corrected mocap roll/pitch exceeds level verification limit')
    if yaw_error > args.max_yaw_error_deg:
        raise RuntimeError('Corrected mocap yaw exceeds expected-orientation limit')
    if spread > args.max_sample_spread_deg:
        raise RuntimeError('Verification orientation spread exceeds held-pose limit')
    if any(math.isnan(value) for value in estimator_errors):
        raise RuntimeError('Estimator attitude telemetry unavailable during verification')
    if max(estimator_errors[:2]) > args.max_level_error_deg or estimator_errors[2] > args.max_yaw_error_deg:
        raise RuntimeError('Estimator attitude failed calibrated frame verification')


def verify_rotation_calibration(rows, body_to_cf, args, rotation_deg):
    expected_yaw = args.nose_front_yaw_deg + rotation_deg
    verify_calibration(rows, body_to_cf, args, expected_yaw)


def shutdown_mocap_reader(reader, timeout=2.0):
    reader.on_pose = None
    reader.close()
    if reader.ident is None:
        return
    reader.join(timeout=timeout)
    if reader.is_alive():
        raise RuntimeError('Mocap reader did not stop cleanly')


def estimate_error(mocap_position, estimate_position):
    if mocap_position is None or estimate_position is None:
        return '', '', '', ''
    ex = estimate_position[0] - mocap_position[0]
    ey = estimate_position[1] - mocap_position[1]
    ez = estimate_position[2] - mocap_position[2]
    return math.sqrt(ex * ex + ey * ey + ez * ez), ex, ey, ez


def make_row(started_at, phase, phase_started_at, command, mocap_state, estimate_state, sender=None):
    del sender
    now = time.time()
    mocap_position, quat, mocap_time, frame_count, orientation_result = (
        mocap_state.snapshot_with_orientation()
    )
    estimate_position, estimate_attitude, battery, estimate_time, attitude_time = estimate_state.snapshot()
    error, error_x, error_y, error_z = estimate_error(mocap_position, estimate_position)

    row = {
        'wall_time_s': now,
        'elapsed_s': now - started_at,
        'phase': phase,
        'phase_elapsed_s': now - phase_started_at,
        'command': command,
        'mocap_x': '',
        'mocap_y': '',
        'mocap_z': '',
        'mocap_qx': '',
        'mocap_qy': '',
        'mocap_qz': '',
        'mocap_qw': '',
        'mocap_age_s': '',
        'mocap_frame_count': frame_count,
        'orientation_packet_sequence': '',
        'orientation_packet_status': 'not-streamed',
        'orientation_rejection_reason': '',
        'orientation_accepted_count': 0,
        'extpos_fallback_count': 0,
        'orientation_rejected_count': 0,
        'corrected_mocap_roll_deg': '',
        'corrected_mocap_pitch_deg': '',
        'corrected_mocap_yaw_deg': '',
        'estimate_x': '',
        'estimate_y': '',
        'estimate_z': '',
        'estimate_roll_deg': '',
        'estimate_pitch_deg': '',
        'estimate_yaw_deg': '',
        'estimate_age_s': '',
        'estimate_attitude_age_s': '',
        'estimate_error_m': error,
        'estimate_error_x_m': error_x,
        'estimate_error_y_m': error_y,
        'estimate_error_z_m': error_z,
        'battery_v': battery,
    }
    row.update(orientation_result)
    if mocap_position is not None and quat is not None:
        row.update({
            'mocap_x': mocap_position[0],
            'mocap_y': mocap_position[1],
            'mocap_z': mocap_position[2],
            'mocap_qx': quat.x,
            'mocap_qy': quat.y,
            'mocap_qz': quat.z,
            'mocap_qw': quat.w,
            'mocap_age_s': now - mocap_time,
        })
    if estimate_position is not None:
        row.update({
            'estimate_x': estimate_position[0],
            'estimate_y': estimate_position[1],
            'estimate_z': estimate_position[2],
            'estimate_roll_deg': estimate_attitude[0] if estimate_attitude else '',
            'estimate_pitch_deg': estimate_attitude[1] if estimate_attitude else '',
            'estimate_yaw_deg': estimate_attitude[2] if estimate_attitude else '',
            'estimate_age_s': now - estimate_time,
            'estimate_attitude_age_s': now - attitude_time if attitude_time else '',
        })
    return row


def numeric_values(values):
    converted = []
    for value in values:
        if not isinstance(value, Real):
            continue
        value = float(value)
        if not math.isnan(value):
            converted.append(value)
    return converted


def median(values):
    values = numeric_values(values)
    if not values:
        return math.nan
    return statistics.median(values)


def format_float(value):
    if isinstance(value, float) and not math.isnan(value):
        return f"{value:.3f}"
    return "n/a"


def print_phase_summary(phase, rows, pose_stale_timeout, packet_counts=None):
    errors = numeric_values([row['estimate_error_m'] for row in rows])
    fresh_rows = [
        row for row in rows
        if isinstance(row['mocap_age_s'], Real) and row['mocap_age_s'] <= pose_stale_timeout
    ]
    mx = median([row['mocap_x'] for row in rows])
    my = median([row['mocap_y'] for row in rows])
    mz = median([row['mocap_z'] for row in rows])
    ex = median([row['estimate_x'] for row in rows])
    ey = median([row['estimate_y'] for row in rows])
    ez = median([row['estimate_z'] for row in rows])
    err = median(errors)
    print(
        f"[PHASE] {phase}: "
        f"mocap=({format_float(mx)}, {format_float(my)}, {format_float(mz)}) "
        f"estimate=({format_float(ex)}, {format_float(ey)}, {format_float(ez)}) "
        f"median_error={format_float(err)}m "
        f"fresh_mocap={len(fresh_rows)}/{len(rows)}"
    )
    if packet_counts is not None:
        total = packet_counts['accepted'] + packet_counts['rejected']
        rejection_ratio = packet_counts['rejected'] / total if total else math.nan
        print(
            f"[STREAM] {phase}: accepted={packet_counts['accepted']} "
            f"fallback={packet_counts['fallback']} "
            f"rejected={packet_counts['rejected']} "
            f"rejection_rate={rejection_ratio:.2%}"
        )
    if math.isnan(mx) or math.isnan(ex):
        print(
            "[WARN] This phase did not contain complete mocap/estimator rows. "
            "Check that mocap is still tracking and the Crazyflie link is alive."
        )
    elif not fresh_rows:
        print(
            "[WARN] Mocap was stale for this whole phase. The estimator values for "
            "this phase are not trustworthy for frame validation."
        )


def validate_orientation_rejection_rate(args, packet_counts):
    total = packet_counts['accepted'] + packet_counts['rejected']
    if total < args.min_orientation_samples:
        raise RuntimeError(
            f'Only {total} streamed orientation packets; need at least '
            f'{args.min_orientation_samples}'
        )
    rejection_ratio = packet_counts['rejected'] / total
    if rejection_ratio > args.max_orientation_rejection_ratio:
        raise RuntimeError(
            f'Orientation rejection rate {rejection_ratio:.2%} exceeds '
            f'{args.max_orientation_rejection_ratio:.2%}'
        )


def make_output_path(output):
    if output:
        path = Path(output)
    else:
        timestamp = time.strftime('%Y%m%d-%H%M%S')
        path = Path(DEFAULT_OUTPUT_DIR) / f"mocap-estimator-world-frame-{timestamp}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def require_position_convergence(
    args,
    mocap_state,
    estimate_state,
    mocap_reader=None,
    clock=time.monotonic,
    sleep=time.sleep,
):
    print(
        f'[VERIFY] Requiring estimator/mocap position error below '
        f'{args.position_convergence_error_m:.3f}m continuously for '
        f'{args.position_convergence_duration:.1f}s'
    )
    deadline = clock() + args.position_convergence_timeout
    stable_since = None
    while clock() < deadline:
        if mocap_reader is not None and mocap_reader.error is not None:
            raise RuntimeError(f'Mocap reader failed: {mocap_reader.error}')
        now = time.time()
        mocap_position, _, mocap_time, _ = mocap_state.snapshot()
        estimate_position, _, _, estimate_time, _ = estimate_state.snapshot()
        fresh = (
            mocap_position is not None
            and estimate_position is not None
            and now - mocap_time <= args.pose_stale_timeout
            and now - estimate_time <= ESTIMATE_STALE_TIMEOUT
        )
        error = (
            distance_3d(mocap_position, estimate_position)
            if fresh else math.inf
        )
        if error < args.position_convergence_error_m:
            if stable_since is None:
                stable_since = clock()
            if clock() - stable_since >= args.position_convergence_duration:
                print(f'[VERIFY] Position converged; current error={error:.3f}m')
                return
        else:
            stable_since = None
        sleep(0.05)
    raise RuntimeError(
        'Estimator/mocap position did not converge continuously before verification'
    )


def wait_for_orientation_baseline(
    sender,
    mocap_reader=None,
    timeout=MOCAP_TIMEOUT,
    clock=time.monotonic,
    sleep=time.sleep,
):
    deadline = clock() + timeout
    while clock() < deadline:
        if mocap_reader is not None and mocap_reader.error is not None:
            raise RuntimeError(f'Mocap reader failed: {mocap_reader.error}')
        if sender.has_orientation_baseline():
            print('[STREAM] First valid post-reset orientation accepted')
            return
        sleep(0.01)
    raise RuntimeError('No valid orientation accepted after baseline reset')


def require_estimator_yaw_convergence(
    args,
    estimate_state,
    expected_yaw_deg,
    mocap_reader=None,
    clock=time.monotonic,
    sleep=time.sleep,
):
    print(
        f'[VERIFY] Requiring estimator yaw within '
        f'{args.yaw_convergence_error_deg:.1f}deg of '
        f'{expected_yaw_deg:.1f}deg continuously for '
        f'{args.yaw_convergence_duration:.1f}s'
    )
    deadline = clock() + args.yaw_convergence_timeout
    stable_since = None
    while clock() < deadline:
        if mocap_reader is not None and mocap_reader.error is not None:
            raise RuntimeError(f'Mocap reader failed: {mocap_reader.error}')
        now = time.time()
        _, attitude, _, _, attitude_time = estimate_state.snapshot()
        yaw = attitude[2] if attitude is not None else math.nan
        fresh = (
            math.isfinite(yaw)
            and attitude_time
            and now - attitude_time <= ESTIMATE_STALE_TIMEOUT
        )
        yaw_error = (
            abs(angle_error_deg(yaw, expected_yaw_deg))
            if fresh else math.inf
        )
        if yaw_error <= args.yaw_convergence_error_deg:
            if stable_since is None:
                stable_since = clock()
            if clock() - stable_since >= args.yaw_convergence_duration:
                print(
                    f'[VERIFY] Estimator yaw converged; '
                    f'current error={yaw_error:.2f}deg'
                )
                return
        else:
            stable_since = None
        sleep(0.05)
    raise RuntimeError(
        f'Estimator yaw did not converge to {expected_yaw_deg:.1f}deg '
        'continuously before verification'
    )


def run_phase(
    args, logger, started_at, phase, description, mocap_state, estimate_state,
    sender=None, require_convergence=False, mocap_reader=None,
    reset_orientation_baseline=False, expected_yaw_deg=None,
):
    print("")
    print("=" * 72)
    print(f"[MOVE] Place the drone at: {description}")
    print("[MOVE] Keep the nose/front pointed the same direction as the start.")
    input("[MOVE] Once it is still, press ENTER to record this phase...")
    if reset_orientation_baseline:
        if sender is None:
            raise RuntimeError('Orientation baseline reset requires an extpose sender')
        sender.reset_orientation_baseline()
        print('[STREAM] Orientation jump-filter baseline reset')
        wait_for_orientation_baseline(sender, mocap_reader)
    if require_convergence:
        require_position_convergence(
            args, mocap_state, estimate_state, mocap_reader
        )
    if expected_yaw_deg is not None:
        require_estimator_yaw_convergence(
            args, estimate_state, expected_yaw_deg, mocap_reader
        )
    print(f"[RECORD] {phase}: holding for {args.hold_duration:.1f}s")

    phase_started_at = time.time()
    stream_start = sender.snapshot() if sender is not None else None
    rows = []
    next_sample = phase_started_at
    last_stale_warning_second = None
    while time.time() - phase_started_at < args.hold_duration:
        now = time.time()
        if now < next_sample:
            time.sleep(min(0.01, next_sample - now))
            continue
        row = make_row(
            started_at,
            phase,
            phase_started_at,
            'hold-still',
            mocap_state,
            estimate_state,
            sender,
        )
        logger.write(row)
        rows.append(row)
        next_sample += 1.0 / args.rate_hz

        mocap_age = row['mocap_age_s']
        estimate_age = row['estimate_age_s']
        if isinstance(mocap_age, Real) and mocap_age > args.pose_stale_timeout:
            stale_second = int(mocap_age)
            if stale_second != last_stale_warning_second:
                print(f"[WARN] Mocap age is stale: {mocap_age:.2f}s")
                last_stale_warning_second = stale_second
        if isinstance(estimate_age, Real) and estimate_age > ESTIMATE_STALE_TIMEOUT:
            print(f"[WARN] Estimate age is stale: {estimate_age:.2f}s")

    packet_counts = None
    if sender is not None:
        stream_end = sender.snapshot()
        packet_counts = {
            'accepted': stream_end['orientation_accepted_count'] - stream_start['orientation_accepted_count'],
            'fallback': stream_end['extpos_fallback_count'] - stream_start['extpos_fallback_count'],
            'rejected': stream_end['orientation_rejected_count'] - stream_start['orientation_rejected_count'],
        }
    print_phase_summary(phase, rows, args.pose_stale_timeout, packet_counts)
    if packet_counts is not None:
        validate_orientation_rejection_rate(args, packet_counts)
    return rows


def run_translation_phases(
    args, logger, started_at, mocap_state, estimate_state, sender, mocap_reader
):
    for phase, description in DEFAULT_PHASES:
        run_phase(
            args, logger, started_at, phase, description,
            mocap_state, estimate_state, sender,
            require_convergence=True,
            mocap_reader=mocap_reader,
            reset_orientation_baseline=True,
            expected_yaw_deg=args.nose_front_yaw_deg,
        )


def run(args):
    runtime = load_runtime_modules()
    runtime['cflib_crtp'].init_drivers()

    output_path = make_output_path(args.output)
    mocap_state = MocapState()
    estimate_state = EstimateState()
    mocap_reader = MocapReader(runtime['motioncapture'], args.host, args.body, mocap_state)
    logger = CsvLogger(output_path)
    estimate_logconfs = []

    print("=" * 72)
    print("MOCAP ESTIMATOR WORLD-FRAME CALIBRATOR")
    print("=" * 72)
    print(f"URI: {args.uri}")
    print(f"Rigid body: {args.body}@{args.host}")
    print(f"Pose stream: {args.pose_mode}")
    print(f"Output: {output_path}")
    print("This is no-flight: it never arms and never commands motors.")
    print("=" * 72)

    try:
        input("Press ENTER to connect mocap and Crazyflie, or Ctrl+C to abort...")
        mocap_reader.start()
        wait_for_mocap(mocap_state, mocap_reader, MOCAP_TIMEOUT)

        with runtime['SyncCrazyflie'](args.uri, cf=runtime['Crazyflie'](rw_cache='./cache')) as scf:
            cf = scf.cf
            print("[INFO] Crazyflie connected.")
            estimate_logconfs = setup_estimate_loggers(cf, runtime['LogConfig'], estimate_state)
            time.sleep(0.8)
            wait_for_estimate(estimate_state, MOCAP_TIMEOUT)

            sender = FilteredExtposeSender(
                cf,
                yaw_jump_deg=args.yaw_jump_deg,
                jump_move_m=args.yaw_jump_move_m,
                orientation_jump_deg=args.orientation_jump_deg,
            )
            mocap_reader.on_pose = sender.send
            print("[INFO] Configuring Kalman estimator for external pose...")
            if args.pose_mode == 'extpose':
                cf.param.set_value('locSrv.extQuatStdDev', args.orientation_std_dev)
            cf.param.set_value('stabilizer.estimator', '2')
            time.sleep(0.5)

            print("[INFO] Resetting estimator while external pose is streaming...")
            runtime['reset_estimator'](cf)
            time.sleep(args.settle_duration)

            started_at = time.time()
            if args.pose_mode != 'extpose':
                raise RuntimeError('Automatic body-frame calibration requires --pose-mode extpose')
            calibration_rows = run_phase(
                args, logger, started_at, 'level_nose_front_calibration',
                'center/start, physically level, with the Crazyflie nose pointing front',
                mocap_state, estimate_state, sender,
                reset_orientation_baseline=True,
            )
            body_to_cf, average_body, spread = compute_body_to_cf_quat(
                calibration_rows,
                args.nose_front_yaw_deg,
                args.pose_stale_timeout,
                args.min_orientation_samples,
            )
            if spread > args.max_sample_spread_deg:
                raise RuntimeError(
                    f'Calibration orientation spread {spread:.2f}deg exceeds '
                    f'{args.max_sample_spread_deg:.2f}deg'
                )
            sender.set_body_to_cf(body_to_cf)
            print(
                '[CALIBRATION] Mean raw body quaternion: '
                f'{average_body.x:.9f} {average_body.y:.9f} '
                f'{average_body.z:.9f} {average_body.w:.9f}'
            )
            print(f'[CALIBRATION] Robust p90 held-sample spread: {spread:.2f}deg')
            print(
                '[CALIBRATION] Provisional transform computed; it will not be '
                'printed for use unless all verification phases pass.'
            )
            print('[INFO] Resetting estimator with calibrated extpose stream...')
            runtime['reset_estimator'](cf)
            time.sleep(args.settle_duration)
            verification_rows = run_phase(
                args, logger, started_at, 'level_nose_front_verification',
                'the same center/start pose, physically level and nose-front',
                mocap_state, estimate_state, sender,
                require_convergence=True, mocap_reader=mocap_reader,
                reset_orientation_baseline=True,
                expected_yaw_deg=args.nose_front_yaw_deg,
            )
            verify_calibration(verification_rows, body_to_cf, args)
            left_rows = run_phase(
                args, logger, started_at, 'level_left_90_verification',
                'center/start, physically level, rotated 90 degrees left from nose-front',
                mocap_state, estimate_state, sender,
                require_convergence=True, mocap_reader=mocap_reader,
                reset_orientation_baseline=True,
                expected_yaw_deg=args.nose_front_yaw_deg + 90.0,
            )
            verify_rotation_calibration(left_rows, body_to_cf, args, 90.0)
            right_rows = run_phase(
                args, logger, started_at, 'level_right_90_verification',
                'center/start, physically level, rotated 90 degrees right from nose-front',
                mocap_state, estimate_state, sender,
                require_convergence=True, mocap_reader=mocap_reader,
                reset_orientation_baseline=True,
                expected_yaw_deg=args.nose_front_yaw_deg - 90.0,
            )
            verify_rotation_calibration(right_rows, body_to_cf, args, -90.0)
            print('[CALIBRATION] PASS: level, left 90, and right 90 orientations verified')
            print(
                '[CALIBRATION] Verified autonomy-ladder argument:\n'
                f'  --body-to-cf-quat {body_to_cf.x:.9f} {body_to_cf.y:.9f} '
                f'{body_to_cf.z:.9f} {body_to_cf.w:.9f}'
            )
            run_translation_phases(
                args, logger, started_at, mocap_state, estimate_state,
                sender, mocap_reader,
            )

    finally:
        for estimate_logconf in estimate_logconfs:
            try:
                estimate_logconf.stop()
            except Exception:
                pass
        try:
            shutdown_mocap_reader(mocap_reader)
        finally:
            logger.close()

    print("=" * 72)
    print("[DONE]")
    print(f"log: {output_path}")
    print(f"rows: {logger.rows}")
    print("=" * 72)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uri', default=DEFAULT_URI)
    parser.add_argument('--host', default=DEFAULT_HOST_NAME)
    parser.add_argument('--body', default=DEFAULT_RIGID_BODY_NAME)
    parser.add_argument('--output', default=None)
    parser.add_argument('--pose-mode', choices=('extpose', 'extpos'), default='extpose')
    parser.add_argument('--orientation-std-dev', type=float, default=8.0e-3)
    parser.add_argument('--hold-duration', type=float, default=4.0)
    parser.add_argument('--settle-duration', type=float, default=2.0)
    parser.add_argument('--rate-hz', type=float, default=20.0)
    parser.add_argument('--pose-stale-timeout', type=float, default=POSE_STALE_TIMEOUT)
    parser.add_argument('--nose-front-yaw-deg', type=float, default=DEFAULT_NOSE_FRONT_YAW_DEG)
    parser.add_argument('--max-level-error-deg', type=float, default=DEFAULT_MAX_LEVEL_ERROR_DEG)
    parser.add_argument('--max-yaw-error-deg', type=float, default=DEFAULT_MAX_YAW_ERROR_DEG)
    parser.add_argument('--max-sample-spread-deg', type=float, default=DEFAULT_MAX_SAMPLE_SPREAD_DEG)
    parser.add_argument('--yaw-jump-deg', type=float, default=DEFAULT_YAW_JUMP_DEG)
    parser.add_argument('--yaw-jump-move-m', type=float, default=DEFAULT_YAW_JUMP_MOVE_M)
    parser.add_argument('--orientation-jump-deg', type=float, default=DEFAULT_ORIENTATION_JUMP_DEG)
    parser.add_argument('--max-orientation-rejection-ratio', type=float, default=DEFAULT_MAX_ORIENTATION_REJECTION_RATIO)
    parser.add_argument('--position-convergence-error-m', type=float, default=DEFAULT_POSITION_CONVERGENCE_ERROR_M)
    parser.add_argument('--position-convergence-duration', type=float, default=DEFAULT_POSITION_CONVERGENCE_DURATION_S)
    parser.add_argument('--position-convergence-timeout', type=float, default=DEFAULT_POSITION_CONVERGENCE_TIMEOUT_S)
    parser.add_argument('--yaw-convergence-error-deg', type=float, default=DEFAULT_YAW_CONVERGENCE_ERROR_DEG)
    parser.add_argument('--yaw-convergence-duration', type=float, default=DEFAULT_YAW_CONVERGENCE_DURATION_S)
    parser.add_argument('--yaw-convergence-timeout', type=float, default=DEFAULT_YAW_CONVERGENCE_TIMEOUT_S)
    parser.add_argument(
        '--min-orientation-samples',
        type=int,
        default=DEFAULT_MIN_ORIENTATION_SAMPLES,
    )
    args = parser.parse_args(argv)

    if args.hold_duration <= 0.0:
        raise ValueError("--hold-duration must be greater than zero")
    if args.settle_duration < 0.0:
        raise ValueError("--settle-duration must be greater than or equal to zero")
    if args.rate_hz <= 0.0:
        raise ValueError("--rate-hz must be greater than zero")
    if args.pose_stale_timeout <= 0.0:
        raise ValueError("--pose-stale-timeout must be greater than zero")
    if args.max_level_error_deg <= 0.0 or args.max_yaw_error_deg <= 0.0:
        raise ValueError('orientation verification limits must be positive')
    if args.max_sample_spread_deg <= 0.0:
        raise ValueError('--max-sample-spread-deg must be positive')
    if args.yaw_jump_deg <= 0.0 or args.yaw_jump_move_m < 0.0:
        raise ValueError('yaw jump filter limits are invalid')
    if args.orientation_jump_deg <= 0.0:
        raise ValueError('--orientation-jump-deg must be positive')
    if not 0.0 <= args.max_orientation_rejection_ratio <= 1.0:
        raise ValueError('--max-orientation-rejection-ratio must be between 0 and 1')
    if args.position_convergence_error_m <= 0.0:
        raise ValueError('--position-convergence-error-m must be positive')
    if args.position_convergence_duration <= 0.0:
        raise ValueError('--position-convergence-duration must be positive')
    if args.position_convergence_timeout < args.position_convergence_duration:
        raise ValueError('--position-convergence-timeout must cover the convergence duration')
    if args.yaw_convergence_error_deg <= 0.0:
        raise ValueError('--yaw-convergence-error-deg must be positive')
    if args.yaw_convergence_duration <= 0.0:
        raise ValueError('--yaw-convergence-duration must be positive')
    if args.yaw_convergence_timeout < args.yaw_convergence_duration:
        raise ValueError('--yaw-convergence-timeout must cover the convergence duration')
    if args.min_orientation_samples <= 0:
        raise ValueError('--min-orientation-samples must be positive')
    expected_samples = math.floor(args.hold_duration * args.rate_hz)
    if expected_samples < args.min_orientation_samples:
        raise ValueError(
            '--hold-duration and --rate-hz must allow at least '
            '--min-orientation-samples samples'
        )
    return args


if __name__ == '__main__':
    run(parse_args())
