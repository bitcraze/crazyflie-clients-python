#!/usr/bin/env python3
"""Guarded Crazyflie autonomy ladder for mocap-based HLC flight.

Run validate-extpose, validate-yaw-rotation, hover, x-step, y-step,
takeoff-land-test, then figure8. Figure-8 requires --enable-figure8.
"""

import argparse
import csv
import math
import select
import sys
import termios
import time
import tty
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread

DEFAULT_URI = "radio://0/80/2M"
DEFAULT_MOCAP_HOST = "192.168.1.42:3883"
DEFAULT_RIGID_BODY = "crazyflie_21"
MOCAP_STALE_S = 0.30
ESTIMATOR_STALE_S = 0.50
YAW_JUMP_DEG = 45.0
YAW_JUMP_MOVE_M = 0.03
QUAT_NORM_TOLERANCE = 0.15
VALIDATION_MAX_REJECTION_RATIO = 0.01
VALIDATION_ROLL_PITCH_ERROR_DEG = 10.0
FILTERED_ORIENTATION_STALE_S = 0.30
MAX_CONSECUTIVE_ORIENTATION_REJECTIONS = 2
LANDING_LATERAL_LIMIT_M = 0.05
LOG_PERIOD_MS = 100
LOOP_PERIOD_S = 0.05
EMERGENCY_PACKETS = 40


def load_runtime_modules():
    import cflib.crtp
    import motioncapture
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    from cflib.utils.reset_estimator import reset_estimator
    return cflib.crtp, motioncapture, Crazyflie, LogConfig, SyncCrazyflie, reset_estimator


@dataclass(frozen=True)
class Quat:
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class Pose:
    position: tuple
    quat: Quat
    timestamp: float
    frame_count: int


class GuardTrip(RuntimeError):
    def __init__(self, reason, immediate_stop):
        super().__init__(reason)
        self.reason = reason
        self.immediate_stop = immediate_stop


class OperatorAbort(RuntimeError):
    pass


class MocapState:
    def __init__(self):
        self._lock = Lock()
        self.pose = None

    def update(self, position, quat):
        with self._lock:
            count = 1 if self.pose is None else self.pose.frame_count + 1
            self.pose = Pose(tuple(position), Quat(quat.x, quat.y, quat.z, quat.w), time.time(), count)

    def snapshot(self):
        with self._lock:
            return self.pose


class TelemetryState:
    def __init__(self):
        self._lock = Lock()
        self.values = {}
        self.times = {}
        self.counts = {}

    def update(self, group, values):
        with self._lock:
            self.values.update(values)
            self.times[group] = time.time()
            self.counts[group] = self.counts.get(group, 0) + 1

    def snapshot(self):
        with self._lock:
            return dict(self.values), dict(self.times), dict(self.counts)


class PoseStreamStats:
    def __init__(self):
        self._lock = Lock()
        self.accepted = 0
        self.fallback = 0
        self.rejected = 0
        self.errors = 0
        self.consecutive_rejected = 0
        self.last_rejection = ""

    def update(self, kind, detail=""):
        with self._lock:
            if kind == "accepted":
                self.accepted += 1
                self.consecutive_rejected = 0
            elif kind == "fallback":
                self.fallback += 1
                self.rejected += 1
                self.consecutive_rejected += 1
                self.last_rejection = detail
            else:
                self.errors += 1

    def snapshot(self):
        with self._lock:
            return {
                "extpose_accepted_count": self.accepted,
                "extpos_fallback_count": self.fallback,
                "orientation_rejected_count": self.rejected,
                "pose_stream_error_count": self.errors,
                "consecutive_orientation_rejection_count": self.consecutive_rejected,
                "last_orientation_rejection": self.last_rejection,
            }


class FilteredPoseState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.quat = None
        self.yaw_deg = None
        self.timestamp = 0.0

    def update(self, position, quat):
        with self._lock:
            self.position = tuple(position)
            self.quat = quat
            self.yaw_deg = yaw_from_quat_deg(quat)
            self.timestamp = time.time()

    def snapshot(self):
        with self._lock:
            return self.position, self.quat, self.yaw_deg, self.timestamp


class FilteredExtposeSender:
    def __init__(
        self, cf, stats, filtered_pose, body_to_cf=None,
        yaw_jump_deg=YAW_JUMP_DEG, jump_move_m=YAW_JUMP_MOVE_M,
    ):
        self.cf = cf
        self.stats = stats
        self.filtered_pose = filtered_pose
        self.body_to_cf = body_to_cf or Quat(0.0, 0.0, 0.0, 1.0)
        self.yaw_jump_deg = yaw_jump_deg
        self.jump_move_m = jump_move_m
        self._lock = Lock()
        self.last_position = None
        self.last_yaw = None

    def send(self, x, y, z, quat):
        position = (x, y, z)
        quat = normalized_quat(quat)
        if quat is not None:
            quat = normalized_quat(multiply_quat(quat, self.body_to_cf))
        if quat is None:
            try:
                self.cf.extpos.send_extpos(x, y, z)
                self.stats.update("fallback", "invalid quaternion")
                return False
            except Exception:
                self.stats.update("error")
                raise
        yaw = yaw_from_quat_deg(quat)
        with self._lock:
            jump = abs(angle_error_deg(yaw, self.last_yaw)) if self.last_yaw is not None else 0.0
            moved = distance_3d(position, self.last_position) if self.last_position is not None else float("inf")
            reject = self.last_yaw is not None and jump > self.yaw_jump_deg and moved < self.jump_move_m
            try:
                if reject:
                    self.cf.extpos.send_extpos(x, y, z)
                    self.stats.update("fallback", f"yaw jump {jump:.1f}deg, move {moved:.3f}m")
                    return False
                self.cf.extpos.send_extpose(x, y, z, quat.x, quat.y, quat.z, quat.w)
                self.last_position = position
                self.last_yaw = yaw
                self.filtered_pose.update(position, quat)
                self.stats.update("accepted")
                return True
            except Exception:
                self.stats.update("error")
                raise


class MocapReader(Thread):
    def __init__(self, motioncapture, host, body_name, state):
        super().__init__(daemon=True)
        self.motioncapture = motioncapture
        self.host = host
        self.body_name = body_name
        self.state = state
        self.on_pose = None
        self.error = None
        self.running = True

    def close(self):
        self.running = False

    def run(self):
        mc = None
        try:
            mc = self.motioncapture.connect("vrpn", {"hostname": self.host})
            print(f"[INFO] Mocap connected; looking for '{self.body_name}'")
            announced = False
            while self.running:
                mc.waitForNextFrame()
                body = mc.rigidBodies.get(self.body_name)
                if body is None:
                    continue
                if not announced:
                    print(f"[INFO] Tracking rigid body: {self.body_name}")
                    announced = True
                position = tuple(body.position)
                self.state.update(position, body.rotation)
                callback = self.on_pose
                if callback is not None:
                    callback(position[0], position[1], position[2], body.rotation)
        except Exception as exc:
            self.error = exc
            print(f"[WARN] Mocap reader stopped: {exc}")
        finally:
            mc = None


class TerminalStopReader:
    def __init__(self):
        self.enabled = sys.stdin.isatty()
        self.old = None

    def __enter__(self):
        if self.enabled:
            self.old = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.enabled and self.old is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old)

    def abort_requested(self):
        if not self.enabled:
            return False
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(readable and sys.stdin.read(1) in ("q", "Q", " ", "\x1b"))


class CsvLogger:
    FIELDS = [
        "wall_time_s", "elapsed_s", "mode", "phase",
        "target_raw_x", "target_raw_y", "target_raw_z",
        "target_local_x", "target_local_y", "target_local_z",
        "mocap_raw_x", "mocap_raw_y", "mocap_raw_z",
        "mocap_local_x", "mocap_local_y", "mocap_local_z",
        "mocap_qx", "mocap_qy", "mocap_qz", "mocap_qw", "mocap_yaw_deg",
        "filtered_yaw_deg", "filtered_roll_deg", "filtered_pitch_deg",
        "roll_frame_error_deg", "pitch_frame_error_deg",
        "mocap_age_s", "mocap_frame_count",
        "stateEstimate.x", "stateEstimate.y", "stateEstimate.z", "stateEstimate.yaw",
        "stateEstimate.roll", "stateEstimate.pitch",
        "stabilizer.roll", "stabilizer.pitch", "stabilizer.yaw",
        "gyro.x", "gyro.y", "gyro.z", "motor.m1", "motor.m2", "motor.m3", "motor.m4", "pm.vbat",
        "estimator_age_s", "estimator_mocap_error_m", "yaw_error_deg",
        "lateral_radius_from_start_m", "lateral_target_error_m",
        "height_above_start_m", "height_target_error_m",
        "correction_world_x", "correction_world_y",
        "attitude_accel_world_x", "attitude_accel_world_y",
        "correction_alignment", "correction_direction_sane",
        "hlc_command_issued", "guard_status",
        "extpose_accepted_count", "extpos_fallback_count", "orientation_rejected_count",
        "pose_stream_error_count", "consecutive_orientation_rejection_count",
        "last_accepted_orientation_age_s", "last_orientation_rejection", "stop_reason",
    ]

    def __init__(self, path, mode):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("w", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=self.FIELDS)
        self.writer.writeheader()
        self.mode = mode
        self.started = time.time()

    def write(self, row):
        now = time.time()
        full = {"wall_time_s": now, "elapsed_s": now - self.started, "mode": self.mode}
        full.update(row)
        self.writer.writerow(full)
        self.file.flush()

    def close(self):
        self.file.close()


def is_finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def distance_3d(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def angle_error_deg(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def normalized_quat(quat):
    values = (quat.x, quat.y, quat.z, quat.w)
    if not all(is_finite(value) for value in values):
        return None
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1.0e-6 or abs(norm - 1.0) > QUAT_NORM_TOLERANCE:
        return None
    return Quat(*(value / norm for value in values))


def multiply_quat(left, right):
    return Quat(
        left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
        left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
        left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w,
        left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
    )


def body_to_cf_quat(args):
    values = getattr(args, "body_to_cf_quat", None)
    if values is None:
        raise GuardTrip("--body-to-cf-quat calibration is required", True)
    quat = normalized_quat(Quat(*values))
    if quat is None:
        raise GuardTrip("--body-to-cf-quat is not a valid unit quaternion", True)
    return quat


def filtered_cf_euler(args, filtered_pose):
    del args
    _, quat, _, timestamp = filtered_pose.snapshot()
    if quat is None:
        return None, None, None, timestamp
    roll, pitch, yaw = euler_from_quat_deg(quat)
    return roll, pitch, yaw, timestamp


def euler_from_quat_deg(quat):
    roll = math.degrees(math.atan2(
        2.0 * (quat.w * quat.x + quat.y * quat.z),
        1.0 - 2.0 * (quat.x * quat.x + quat.y * quat.y),
    ))
    pitch_term = 2.0 * (quat.w * quat.y - quat.z * quat.x)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, pitch_term))))
    yaw = yaw_from_quat_deg(quat)
    return roll, pitch, yaw


def yaw_from_quat_deg(quat):
    siny = 2.0 * (quat.w * quat.z + quat.x * quat.y)
    cosy = 1.0 - 2.0 * (quat.y * quat.y + quat.z * quat.z)
    return math.degrees(math.atan2(siny, cosy))


def local_position(raw, start):
    return tuple(raw[i] - start[i] for i in range(3))


def raw_target(start, local):
    return tuple(start[i] + local[i] for i in range(3))


def figure8_local_target(radius_x, radius_y, period_s, elapsed_s, height):
    phase = 2.0 * math.pi * elapsed_s / period_s
    return radius_x * math.sin(phase), radius_y * math.sin(phase) * math.cos(phase), height


def pose_age(pose):
    return float("inf") if pose is None else time.time() - pose.timestamp


def packet_age(times, group):
    return float("inf") if not times.get(group) else time.time() - times[group]


def make_log_config(LogConfig, name, variables, state):
    config = LogConfig(name=name, period_in_ms=LOG_PERIOD_MS)
    for variable, var_type in variables:
        config.add_variable(variable, var_type)
    config.data_received_cb.add_callback(lambda timestamp, data, logconf: state.update(logconf.name, data))
    config.error_cb.add_callback(lambda logconf, message: print(f"[WARN] Logger {logconf.name}: {message}"))
    return config


def setup_telemetry(cf, LogConfig, state):
    groups = [
        ("estimate", [("stateEstimate.x", "float"), ("stateEstimate.y", "float"), ("stateEstimate.z", "float"), ("stateEstimate.yaw", "float")]),
        ("estimate_rp", [("stateEstimate.roll", "float"), ("stateEstimate.pitch", "float")]),
        ("stabilizer", [("stabilizer.roll", "float"), ("stabilizer.pitch", "float"), ("stabilizer.yaw", "float")]),
        ("gyro", [("gyro.x", "float"), ("gyro.y", "float"), ("gyro.z", "float")]),
        ("motor", [("motor.m1", "uint16_t"), ("motor.m2", "uint16_t"), ("motor.m3", "uint16_t"), ("motor.m4", "uint16_t")]),
        ("power", [("pm.vbat", "float")]),
    ]
    started = []
    for name, variables in groups:
        try:
            config = make_log_config(LogConfig, name, variables, state)
            cf.log.add_config(config)
            config.start()
            started.append(config)
        except Exception as exc:
            print(f"[WARN] Optional telemetry group {name} unavailable: {exc}")
    return started


def wait_for_pose(state, reader):
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if reader.error:
            raise RuntimeError(f"Mocap reader failed: {reader.error}")
        pose = state.snapshot()
        if pose_age(pose) <= MOCAP_STALE_S:
            return pose
        time.sleep(0.05)
    raise RuntimeError("No fresh mocap pose before timeout")


def require_stable_pose(state, reader):
    print("[INFO] Requiring stable pose for 2.0s")
    samples = []
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if reader.error:
            raise RuntimeError(f"Mocap reader failed: {reader.error}")
        pose = state.snapshot()
        if pose_age(pose) > MOCAP_STALE_S:
            raise RuntimeError("Mocap stale during stability check")
        samples.append(pose.position)
        time.sleep(0.05)
    ranges = [max(p[i] for p in samples) - min(p[i] for p in samples) for i in range(3)]
    print(f"[INFO] Pose ranges dx/dy/dz={ranges[0]:.3f}/{ranges[1]:.3f}/{ranges[2]:.3f}m")
    if any(value > 0.02 for value in ranges):
        raise RuntimeError("Pose moved more than 0.02m during stability check")


def estimator_sample(state):
    values, times, counts = state.snapshot()
    estimate = tuple(values.get(name) for name in ("stateEstimate.x", "stateEstimate.y", "stateEstimate.z"))
    return values, times, counts, estimate if all(is_finite(v) for v in estimate) else None


def require_battery(args, state):
    values, _, _ = state.snapshot()
    battery = values.get("pm.vbat")
    if not is_finite(battery):
        raise RuntimeError("Battery telemetry unavailable")
    print(f"[INFO] Battery: {battery:.2f} V")
    if battery < 3.70:
        print("[WARN] Battery below 3.70 V")
    if not args.mode.startswith("validate-") and battery < 3.60:
        raise RuntimeError("Battery below 3.60 V; flight refused")


def correction_diagnostics(values, pose, target):
    correction_x = target[0] - pose.position[0]
    correction_y = target[1] - pose.position[1]
    roll, pitch, yaw = (values.get("stabilizer.roll"), values.get("stabilizer.pitch"), values.get("stateEstimate.yaw"))
    if not all(is_finite(v) for v in (roll, pitch, yaw)):
        return correction_x, correction_y, "", "", "", ""
    body_x, body_y = -math.radians(pitch), -math.radians(roll)
    yaw_rad = math.radians(yaw)
    accel_x = math.cos(yaw_rad) * body_x - math.sin(yaw_rad) * body_y
    accel_y = math.sin(yaw_rad) * body_x + math.cos(yaw_rad) * body_y
    alignment = correction_x * accel_x + correction_y * accel_y
    sane = "" if math.hypot(correction_x, correction_y) < 0.005 or math.hypot(accel_x, accel_y) < math.radians(0.5) else int(alignment > 0)
    return correction_x, correction_y, accel_x, accel_y, alignment, sane


def log_sample(logger, args, mocap, telemetry, stream_stats, filtered_pose, start, target_local, phase, command, guard, reason=""):
    pose = mocap.snapshot()
    values, times, _, estimate = estimator_sample(telemetry)
    target = raw_target(start, target_local)
    if pose is None:
        position = local = ("", "", "")
        quat = Quat(float("nan"), float("nan"), float("nan"), float("nan"))
        yaw = float("nan")
        age, frames = float("inf"), 0
    else:
        position, local, quat = pose.position, local_position(pose.position, start), pose.quat
        yaw, age, frames = yaw_from_quat_deg(quat), pose_age(pose), pose.frame_count
    estimate_error = distance_3d(position, estimate) if pose and estimate else ""
    filtered_roll, filtered_pitch, filtered_yaw, filtered_timestamp = filtered_cf_euler(
        args, filtered_pose
    )
    filtered_roll = filtered_roll if filtered_roll is not None else ""
    filtered_pitch = filtered_pitch if filtered_pitch is not None else ""
    estimate_yaw = values.get("stateEstimate.yaw")
    yaw_error = abs(angle_error_deg(estimate_yaw, filtered_yaw)) if is_finite(estimate_yaw) and is_finite(filtered_yaw) else ""
    estimate_roll = values.get("stateEstimate.roll")
    estimate_pitch = values.get("stateEstimate.pitch")
    roll_error = abs(angle_error_deg(estimate_roll, filtered_roll)) if is_finite(estimate_roll) and is_finite(filtered_roll) else ""
    pitch_error = abs(angle_error_deg(estimate_pitch, filtered_pitch)) if is_finite(estimate_pitch) and is_finite(filtered_pitch) else ""
    corrections = correction_diagnostics(values, pose, target) if pose else ("",) * 6
    row = {
        "phase": phase,
        "target_raw_x": target[0], "target_raw_y": target[1], "target_raw_z": target[2],
        "target_local_x": target_local[0], "target_local_y": target_local[1], "target_local_z": target_local[2],
        "mocap_raw_x": position[0], "mocap_raw_y": position[1], "mocap_raw_z": position[2],
        "mocap_local_x": local[0], "mocap_local_y": local[1], "mocap_local_z": local[2],
        "mocap_qx": quat.x, "mocap_qy": quat.y, "mocap_qz": quat.z, "mocap_qw": quat.w,
        "mocap_yaw_deg": yaw, "filtered_yaw_deg": filtered_yaw if filtered_yaw is not None else "",
        "filtered_roll_deg": filtered_roll, "filtered_pitch_deg": filtered_pitch,
        "roll_frame_error_deg": roll_error, "pitch_frame_error_deg": pitch_error,
        "mocap_age_s": age, "mocap_frame_count": frames,
        "last_accepted_orientation_age_s": (
            time.time() - filtered_timestamp if filtered_timestamp else ""
        ),
        "estimator_age_s": packet_age(times, "estimate"), "estimator_mocap_error_m": estimate_error,
        "yaw_error_deg": yaw_error,
        "lateral_radius_from_start_m": math.hypot(local[0], local[1]) if pose else "",
        "lateral_target_error_m": math.hypot(position[0] - target[0], position[1] - target[1]) if pose else "",
        "height_above_start_m": local[2] if pose else "",
        "height_target_error_m": position[2] - target[2] if pose else "",
        "correction_world_x": corrections[0], "correction_world_y": corrections[1],
        "attitude_accel_world_x": corrections[2], "attitude_accel_world_y": corrections[3],
        "correction_alignment": corrections[4], "correction_direction_sane": corrections[5],
        "hlc_command_issued": command, "guard_status": guard, "stop_reason": reason,
    }
    for name in ("stateEstimate.x", "stateEstimate.y", "stateEstimate.z", "stateEstimate.yaw", "stateEstimate.roll", "stateEstimate.pitch", "stabilizer.roll", "stabilizer.pitch", "stabilizer.yaw", "gyro.x", "gyro.y", "gyro.z", "motor.m1", "motor.m2", "motor.m3", "motor.m4", "pm.vbat"):
        row[name] = values.get(name, "")
    row.update(stream_stats.snapshot())
    logger.write(row)


def require_estimator_agreement(args, mocap, telemetry, logger, stats, filtered_pose, start):
    tolerance = 0.05 if args.mode.startswith("validate-") else 0.08
    require_yaw = args.mode != "validate-extpose"
    deadline = time.time() + 2.0
    good = 0
    while time.time() < deadline:
        pose = mocap.snapshot()
        values, times, _, estimate = estimator_sample(telemetry)
        if pose_age(pose) > MOCAP_STALE_S:
            raise RuntimeError("Mocap stale during estimator precheck")
        if estimate is None or packet_age(times, "estimate") > ESTIMATOR_STALE_S:
            time.sleep(0.05)
            continue
        error = distance_3d(pose.position, estimate)
        _, _, filtered_yaw, _ = filtered_cf_euler(args, filtered_pose)
        yaw_error = abs(angle_error_deg(values.get("stateEstimate.yaw", float("nan")), filtered_yaw)) if filtered_yaw is not None else float("nan")
        log_sample(logger, args, mocap, telemetry, stats, filtered_pose, start, (0, 0, 0), "preflight", "none", "precheck")
        if error > tolerance:
            raise RuntimeError(f"Estimator/mocap error {error:.3f}m exceeds {tolerance:.2f}m")
        if require_yaw and (not is_finite(yaw_error) or yaw_error > 10.0):
            raise RuntimeError(f"Estimator/mocap yaw error {yaw_error:.1f}deg exceeds 10deg")
        validate_roll_pitch_frame(args, values, filtered_pose)
        validate_stream_health(args, stats, filtered_pose)
        good += 1
        time.sleep(0.05)
    if good < 10:
        raise RuntimeError("Too few fresh estimator samples")


def check_guards(args, mocap, telemetry, stats, filtered_pose, start, target_local, phase):
    pose = mocap.snapshot()
    if pose_age(pose) > MOCAP_STALE_S:
        raise GuardTrip("mocap stale > 0.30s", True)
    values, times, _, estimate = estimator_sample(telemetry)
    if estimate is None or packet_age(times, "estimate") > ESTIMATOR_STALE_S:
        raise GuardTrip("estimator stale > 0.50s", False)
    if any(abs(value) >= 100.0 for value in estimate):
        raise GuardTrip("estimator position nonsensical", True)
    error = distance_3d(pose.position, estimate)
    if error > 0.10:
        raise GuardTrip(f"estimator/mocap error {error:.3f}m > 0.10m", True)
    validate_stream_health(args, stats, filtered_pose)
    validate_roll_pitch_frame(args, values, filtered_pose)
    _, _, filtered_yaw, _ = filtered_cf_euler(args, filtered_pose)
    yaw_error = abs(angle_error_deg(values.get("stateEstimate.yaw", float("nan")), filtered_yaw)) if filtered_yaw is not None else float("nan")
    if not is_finite(yaw_error) or yaw_error > 20.0:
        raise GuardTrip(f"yaw error {yaw_error:.1f}deg > 20deg", True)
    local = local_position(pose.position, start)
    if local[2] > target_local[2] + 0.08:
        raise GuardTrip("height above commanded height + 0.08m", False)
    radius = math.hypot(local[0], local[1])
    if radius > 0.12:
        raise GuardTrip(f"lateral radius {radius:.3f}m > 0.12m", True)
    target = raw_target(start, target_local)
    lateral_error = math.hypot(pose.position[0] - target[0], pose.position[1] - target[1])
    if phase in ("land", "controlled-land") and lateral_error > args.max_landing_lateral_error:
        raise GuardTrip(
            f"landing lateral error {lateral_error:.3f}m > "
            f"{args.max_landing_lateral_error:.3f}m", True
        )
    if phase == "takeoff":
        limit = 0.06 if local[2] < 0.02 else 0.035
        if lateral_error > limit:
            raise GuardTrip(f"takeoff lateral error {lateral_error:.3f}m > {limit:.3f}m", True)
    elif phase == "hover" and lateral_error > 0.04:
        raise GuardTrip(f"hover lateral error {lateral_error:.3f}m > 0.04m", True)


def validate_stream_health(args, stats, filtered_pose=None):
    snapshot = stats.snapshot()
    if snapshot["pose_stream_error_count"]:
        raise GuardTrip("pose stream transmission error", True)
    consecutive = snapshot["consecutive_orientation_rejection_count"]
    if consecutive > args.max_consecutive_orientation_rejections:
        raise GuardTrip(
            f"consecutive orientation rejections {consecutive} exceed "
            f"{args.max_consecutive_orientation_rejections}", True
        )
    total = snapshot["extpose_accepted_count"] + snapshot["orientation_rejected_count"]
    ratio = snapshot["orientation_rejected_count"] / total if total else 0.0
    if total >= args.orientation_rejection_min_samples and ratio > args.max_orientation_rejection_ratio:
        raise GuardTrip(
            f"orientation rejection ratio {ratio:.1%} exceeds "
            f"{args.max_orientation_rejection_ratio:.1%}", True
        )
    if filtered_pose is not None:
        _, _, _, timestamp = filtered_pose.snapshot()
        age = time.time() - timestamp if timestamp else float("inf")
        if age > args.max_filtered_orientation_age:
            raise GuardTrip(
                f"last accepted orientation age {age:.3f}s exceeds "
                f"{args.max_filtered_orientation_age:.3f}s", True
            )


def validate_roll_pitch_frame(args, values, filtered_pose):
    filtered_roll, filtered_pitch, _, _ = filtered_cf_euler(args, filtered_pose)
    if filtered_roll is None:
        raise GuardTrip("no accepted filtered orientation", True)
    estimate_roll = values.get("stateEstimate.roll")
    estimate_pitch = values.get("stateEstimate.pitch")
    if not all(is_finite(value) for value in (estimate_roll, estimate_pitch)):
        raise GuardTrip("roll/pitch estimator telemetry unavailable", True)
    roll_error = abs(angle_error_deg(estimate_roll, filtered_roll))
    pitch_error = abs(angle_error_deg(estimate_pitch, filtered_pitch))
    if max(roll_error, pitch_error) > VALIDATION_ROLL_PITCH_ERROR_DEG:
        raise GuardTrip(
            f"roll/pitch frame error {roll_error:.1f}/{pitch_error:.1f}deg exceeds "
            f"{VALIDATION_ROLL_PITCH_ERROR_DEG:.0f}deg", True
        )
    return roll_error, pitch_error


def monitor(args, logger, key_reader, mocap, telemetry, stats, filtered_pose, start, target_local, phase, command, duration, flight=True):
    deadline = time.time() + duration
    while time.time() < deadline:
        if key_reader.abort_requested():
            raise OperatorAbort("operator abort")
        if flight:
            check_guards(
                args, mocap, telemetry, stats, filtered_pose, start, target_local, phase
            )
        else:
            pose = mocap.snapshot()
            values, times, _, estimate = estimator_sample(telemetry)
            if pose_age(pose) > MOCAP_STALE_S:
                raise GuardTrip("mocap stale > 0.30s", True)
            if estimate is None or packet_age(times, "estimate") > ESTIMATOR_STALE_S:
                raise GuardTrip("estimator stale > 0.50s", True)
            if distance_3d(pose.position, estimate) > 0.05:
                raise GuardTrip("validation estimator/mocap error > 0.05m", True)
            validate_stream_health(args, stats, filtered_pose)
            validate_roll_pitch_frame(args, values, filtered_pose)
            if args.mode == "validate-yaw-rotation":
                _, _, filtered_yaw, _ = filtered_cf_euler(args, filtered_pose)
                yaw_error = (
                    abs(angle_error_deg(
                        values.get("stateEstimate.yaw", float("nan")),
                        filtered_yaw,
                    ))
                    if filtered_yaw is not None else float("nan")
                )
                if not is_finite(yaw_error) or yaw_error > 10.0:
                    raise GuardTrip(
                        f"validation yaw error {yaw_error:.1f}deg > 10deg", True
                    )
        log_sample(
            logger, args, mocap, telemetry, stats, filtered_pose, start,
            target_local, phase, command, "ok",
        )
        time.sleep(LOOP_PERIOD_S)


def arm(cf):
    cf.supervisor.send_arming_request(True)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            if cf.supervisor.is_armed:
                print("[INFO] Supervisor reports armed")
                return
        except Exception:
            break
        time.sleep(0.1)
    raise RuntimeError("Crazyflie did not report armed")


def disarm(cf):
    try:
        cf.supervisor.send_arming_request(False)
    except Exception:
        try:
            cf.platform.send_arming_request(False)
        except Exception:
            pass


def emergency_stop(cf):
    print("[SAFETY] Immediate HLC stop, zero thrust, and disarm")
    try:
        cf.high_level_commander.stop()
    except Exception:
        pass
    for _ in range(EMERGENCY_PACKETS):
        try:
            cf.commander.send_stop_setpoint()
            cf.commander.send_setpoint(0.0, 0.0, 0.0, 0)
        except Exception:
            pass
        time.sleep(0.01)
    disarm(cf)


def controlled_land(cf, args, logger, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad):
    print("[SAFETY] Attempting controlled HLC landing with live guards")
    try:
        cf.high_level_commander.land(
            start[2], args.land_duration, yaw=command_yaw_rad
        )
        with TerminalStopReader() as keys:
            monitor(
                args, logger, keys, mocap, telemetry, stats, filtered_pose, start,
                (0, 0, 0), "controlled-land", "land", args.land_duration + 0.25,
            )
    except Exception as exc:
        print(f"[WARN] Controlled landing monitor stopped: {exc}")
    finally:
        emergency_stop(cf)


def takeoff_hover(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad):
    local = (0.0, 0.0, args.height)
    target = raw_target(start, local)
    cf.high_level_commander.takeoff(
        target[2], args.takeoff_duration, yaw=command_yaw_rad
    )
    monitor(args, logger, keys, mocap, telemetry, stats, filtered_pose, start, local, "takeoff", "takeoff", args.takeoff_duration + 0.25)
    reached = mocap.snapshot().position[2] - start[2]
    if reached < 0.70 * args.height:
        raise GuardTrip(f"takeoff reached only {reached:.3f}m", False)
    monitor(args, logger, keys, mocap, telemetry, stats, filtered_pose, start, local, "hover", "hold", args.hover_duration)


def go_to(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, local, phase, command_yaw_rad, duration=None):
    duration = args.step_duration if duration is None else duration
    target = raw_target(start, local)
    cf.high_level_commander.go_to(
        target[0], target[1], target[2], command_yaw_rad, duration,
        relative=False,
    )
    monitor(args, logger, keys, mocap, telemetry, stats, filtered_pose, start, local, phase, "go_to", duration + 0.05)


def normal_land(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad):
    cf.high_level_commander.land(
        start[2], args.land_duration, yaw=command_yaw_rad
    )
    monitor(args, logger, keys, mocap, telemetry, stats, filtered_pose, start, (0, 0, 0), "land", "land", args.land_duration + 0.25)
    emergency_stop(cf)


def takeoff_only(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad):
    local = (0.0, 0.0, args.height)
    target = raw_target(start, local)
    cf.high_level_commander.takeoff(
        target[2], args.takeoff_duration, yaw=command_yaw_rad
    )
    monitor(args, logger, keys, mocap, telemetry, stats, filtered_pose, start, local, "takeoff", "takeoff", args.takeoff_duration + 0.25)
    reached = mocap.snapshot().position[2] - start[2]
    if reached < 0.70 * args.height:
        raise GuardTrip(f"takeoff reached only {reached:.3f}m", False)


def run_flight(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad):
    if args.mode == "takeoff-land-test":
        takeoff_only(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad)
        normal_land(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad)
        return
    takeoff_hover(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad)
    if args.mode in ("x-step", "y-step"):
        axis = 0 if args.mode == "x-step" else 1
        for offset in (args.step, 0.0, -args.step, 0.0):
            local = [0.0, 0.0, args.height]
            local[axis] = offset
            go_to(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, tuple(local), args.mode, command_yaw_rad)
    elif args.mode == "figure8":
        count = max(12, math.ceil(args.figure8_period / args.figure8_point_duration))
        for index in range(1, count + 1):
            local = figure8_local_target(args.figure8_radius_x, args.figure8_radius_y, args.figure8_period, index * args.figure8_period / count, args.height)
            go_to(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, local, "figure8", command_yaw_rad, args.figure8_point_duration)
    normal_land(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad)


def validate_args(args):
    if args.mode == "figure8" and not args.enable_figure8:
        raise ValueError("figure8 is disabled; pass --enable-figure8 only after earlier stages pass")
    if args.height <= 0 or args.takeoff_duration <= 0 or args.land_duration <= 0:
        raise ValueError("height and flight durations must be positive")
    if args.step <= 0:
        raise ValueError("--step must be positive")
    if args.height + 0.08 > args.max_local_height:
        raise ValueError("--max-local-height must include height plus the 0.08m guard")
    if not 0.0 <= args.max_orientation_rejection_ratio <= 1.0:
        raise ValueError("--max-orientation-rejection-ratio must be between 0 and 1")
    if args.orientation_rejection_min_samples <= 0:
        raise ValueError("--orientation-rejection-min-samples must be positive")
    if args.max_consecutive_orientation_rejections < 0:
        raise ValueError("--max-consecutive-orientation-rejections must be non-negative")
    if args.max_filtered_orientation_age <= 0:
        raise ValueError("--max-filtered-orientation-age must be positive")
    if not 0 < args.max_landing_lateral_error <= 0.05:
        raise ValueError("--max-landing-lateral-error must be in (0, 0.05]")
    if args.body_to_cf_quat is None:
        raise ValueError(
            "--body-to-cf-quat x y z w is required; calibrate the rigid-body "
            "frame before validation or flight"
        )
    if normalized_quat(Quat(*args.body_to_cf_quat)) is None:
        raise ValueError("--body-to-cf-quat must be a finite near-unit quaternion")
    if min(args.figure8_radius_x, args.figure8_radius_y, args.figure8_period, args.figure8_point_duration) <= 0:
        raise ValueError("figure8 dimensions and timing must be positive")


def run(args):
    validate_args(args)
    crtp, motioncapture, Crazyflie, LogConfig, SyncCrazyflie, reset_estimator = load_runtime_modules()
    path = Path(args.output) if args.output else Path(args.output_dir) / f"mocap-autonomy-{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    logger = CsvLogger(path, args.mode)
    mocap, telemetry, stats, filtered_pose = MocapState(), TelemetryState(), PoseStreamStats(), FilteredPoseState()
    reader = MocapReader(motioncapture, args.mocap_host, args.rigid_body, mocap)
    configs, cf, start = [], None, None
    command_yaw_rad = 0.0
    armed = success = False
    stop_reason = ""
    print("=" * 72)
    print(f"GUARDED MOCAP AUTONOMY LADDER: {args.mode}")
    print(f"Mocap: {args.rigid_body}@{args.mocap_host}; URI: {args.uri}; log: {path}")
    print("Raw mocap is streamed unchanged. Targets are start pose + local offsets.")
    print("=" * 72)
    try:
        input("Press ENTER to connect mocap, or Ctrl+C to abort...")
        reader.start()
        wait_for_pose(mocap, reader)
        require_stable_pose(mocap, reader)
        start = mocap.snapshot().position
        print(f"[INFO] Local origin raw=({start[0]:.3f}, {start[1]:.3f}, {start[2]:.3f})")
        input("Press ENTER to connect Crazyflie, or Ctrl+C to abort...")
        crtp.init_drivers()
        with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
            cf = scf.cf
            configs = setup_telemetry(cf, LogConfig, telemetry)
            reader.on_pose = FilteredExtposeSender(
                cf, stats, filtered_pose, body_to_cf_quat(args)
            ).send
            cf.param.set_value("locSrv.extQuatStdDev", args.orientation_std_dev)
            cf.param.set_value("stabilizer.estimator", "2")
            cf.param.set_value("commander.enHighLevel", "1")
            time.sleep(0.5)
            reset_estimator(cf)
            time.sleep(1.0)
            require_battery(args, telemetry)
            require_estimator_agreement(args, mocap, telemetry, logger, stats, filtered_pose, start)
            _, _, command_yaw_deg, _ = filtered_cf_euler(args, filtered_pose)
            if command_yaw_deg is None:
                raise RuntimeError("No validated yaw available for HLC commands")
            command_yaw_rad = math.radians(command_yaw_deg)
            print(f"[INFO] Preserving validated yaw target: {command_yaw_deg:.1f}deg")
            if args.mode.startswith("validate-"):
                print(f"[VALIDATE] Props off; move the drone as requested for {args.duration:.1f}s")
                with TerminalStopReader() as keys:
                    monitor(args, logger, keys, mocap, telemetry, stats, filtered_pose, start, (0, 0, 0), args.mode, "none", args.duration, flight=False)
                success = True
            else:
                input("Press ENTER to ARM and run this flight stage, or Ctrl+C to abort...")
                arm(cf)
                armed = True
                with TerminalStopReader() as keys:
                    run_flight(cf, args, logger, keys, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad)
                armed = False
                success = True
    except (OperatorAbort, KeyboardInterrupt) as exc:
        stop_reason = "operator abort" if isinstance(exc, OperatorAbort) else "Ctrl+C"
        if cf is not None:
            emergency_stop(cf)
        armed = False
    except GuardTrip as exc:
        stop_reason = exc.reason
        print(f"[SAFETY] Guard tripped: {exc.reason}")
        if cf is not None and armed:
            emergency_stop(cf) if exc.immediate_stop else controlled_land(
                cf, args, logger, mocap, telemetry, stats, filtered_pose, start, command_yaw_rad
            )
        armed = False
    except Exception as exc:
        stop_reason = str(exc)
        print(f"[ERROR] {exc}")
        if cf is not None and armed:
            emergency_stop(cf)
        armed = False
    finally:
        if cf is not None and armed:
            emergency_stop(cf)
        if start is not None:
            log_sample(logger, args, mocap, telemetry, stats, filtered_pose, start, (0, 0, 0), "shutdown", "stop/disarm", "complete" if success else "failed", stop_reason)
        reader.on_pose = None
        for config in configs:
            try:
                config.stop()
            except Exception:
                pass
        reader.close()
        reader.join(timeout=1.0)
        logger.close()
        counts = stats.snapshot()
        print(f"[DONE] success={success} reason={stop_reason or 'none'} extpose={counts['extpose_accepted_count']} fallback={counts['extpos_fallback_count']} log={path}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("validate-extpose", "validate-yaw-rotation", "hover", "x-step", "y-step", "takeoff-land-test", "figure8"))
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--mocap-host", default=DEFAULT_MOCAP_HOST)
    parser.add_argument("--rigid-body", default=DEFAULT_RIGID_BODY)
    parser.add_argument("--output-dir", default="flight_logs")
    parser.add_argument("--output")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--height", type=float, default=0.05)
    parser.add_argument("--takeoff-duration", type=float, default=5.0)
    parser.add_argument("--hover-duration", type=float, default=1.0)
    parser.add_argument("--land-duration", type=float, default=6.0)
    parser.add_argument("--step", type=float, default=0.03)
    parser.add_argument("--step-duration", type=float, default=3.0)
    parser.add_argument("--orientation-std-dev", type=float, default=8.0e-3)
    parser.add_argument("--max-orientation-rejection-ratio", type=float, default=VALIDATION_MAX_REJECTION_RATIO)
    parser.add_argument("--orientation-rejection-min-samples", type=int, default=20)
    parser.add_argument(
        "--max-consecutive-orientation-rejections", type=int,
        default=MAX_CONSECUTIVE_ORIENTATION_REJECTIONS,
    )
    parser.add_argument(
        "--max-filtered-orientation-age", type=float,
        default=FILTERED_ORIENTATION_STALE_S,
    )
    parser.add_argument(
        "--max-landing-lateral-error", type=float,
        default=LANDING_LATERAL_LIMIT_M,
    )
    parser.add_argument(
        "--body-to-cf-quat", type=float, nargs=4, metavar=("X", "Y", "Z", "W"),
        help="calibrated q_body_to_cf; q_world_cf = q_world_body * q_body_to_cf",
    )
    parser.add_argument("--max-local-height", type=float, default=0.20)
    parser.add_argument("--figure8-radius-x", type=float, default=0.03)
    parser.add_argument("--figure8-radius-y", type=float, default=0.02)
    parser.add_argument("--figure8-period", type=float, default=35.0)
    parser.add_argument("--figure8-point-duration", type=float, default=1.0)
    parser.add_argument("--enable-figure8", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
