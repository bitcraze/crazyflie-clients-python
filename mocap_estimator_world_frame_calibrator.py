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

DEFAULT_PHASES = [
    ('center_start', 'center/start position'),
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

    def update(self, position, quat):
        with self._lock:
            self.position = tuple(position)
            self.quat = quat
            self.last_update = time.time()
            self.frame_count += 1

    def snapshot(self):
        with self._lock:
            return self.position, self.quat, self.last_update, self.frame_count


class EstimateState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.battery_voltage = 0.0
        self.last_update = 0.0

    def update(self, x, y, z, battery_voltage):
        with self._lock:
            self.position = (x, y, z)
            self.battery_voltage = battery_voltage
            self.last_update = time.time()

    def snapshot(self):
        with self._lock:
            return self.position, self.battery_voltage, self.last_update


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

    def close(self):
        self._stay_open = False

    def run(self):
        try:
            mc = self.motioncapture.connect('vrpn', {'hostname': self.host_name})
            print(f"[INFO] Mocap connected, looking for '{self.body_name}'")
            found = False
            while self._stay_open:
                mc.waitForNextFrame()
                for name, obj in mc.rigidBodies.items():
                    if name != self.body_name:
                        continue
                    if not found:
                        print(f"[INFO] Found and tracking rigid body: {name}")
                        found = True
                    pos = obj.position
                    quat = obj.rotation
                    self.state.update((pos[0], pos[1], pos[2]), quat)
                    if self.on_pose is not None:
                        self.on_pose(pos[0], pos[1], pos[2], quat)
        except Exception as exc:
            self.error = exc


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
        'estimate_x',
        'estimate_y',
        'estimate_z',
        'estimate_age_s',
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


def setup_estimate_logger(cf, LogConfig, estimate_state):
    logconf = LogConfig(name='EstimatorWorldFrame', period_in_ms=LOG_PERIOD_MS)
    logconf.add_variable('pm.vbat', 'float')
    logconf.add_variable('stateEstimate.x', 'float')
    logconf.add_variable('stateEstimate.y', 'float')
    logconf.add_variable('stateEstimate.z', 'float')

    def on_data(timestamp, data, logconf):
        del timestamp, logconf
        estimate_state.update(
            data['stateEstimate.x'],
            data['stateEstimate.y'],
            data['stateEstimate.z'],
            data['pm.vbat'],
        )

    def on_error(logconf, msg):
        print(f"[WARN] Logger error from {logconf.name}: {msg}")

    cf.log.add_config(logconf)
    logconf.data_received_cb.add_callback(on_data)
    logconf.error_cb.add_callback(on_error)
    logconf.start()
    return logconf


def send_extpose_or_extpos(cf, pose_mode, x, y, z, quat):
    if pose_mode == 'extpose':
        cf.extpos.send_extpose(x, y, z, quat.x, quat.y, quat.z, quat.w)
    else:
        cf.extpos.send_extpos(x, y, z)


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
        position, battery, last_update = estimate_state.snapshot()
        if position is not None and time.time() - last_update <= ESTIMATE_STALE_TIMEOUT:
            print(
                "[ESTIMATE] Fresh estimate: "
                f"pos=({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) "
                f"battery={battery:.2f}V"
            )
            return
        time.sleep(0.05)
    raise RuntimeError("No fresh stateEstimate data received before timeout")


def estimate_error(mocap_position, estimate_position):
    if mocap_position is None or estimate_position is None:
        return '', '', '', ''
    ex = estimate_position[0] - mocap_position[0]
    ey = estimate_position[1] - mocap_position[1]
    ez = estimate_position[2] - mocap_position[2]
    return math.sqrt(ex * ex + ey * ey + ez * ez), ex, ey, ez


def make_row(started_at, phase, phase_started_at, command, mocap_state, estimate_state):
    now = time.time()
    mocap_position, quat, mocap_time, frame_count = mocap_state.snapshot()
    estimate_position, battery, estimate_time = estimate_state.snapshot()
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
        'estimate_x': '',
        'estimate_y': '',
        'estimate_z': '',
        'estimate_age_s': '',
        'estimate_error_m': error,
        'estimate_error_x_m': error_x,
        'estimate_error_y_m': error_y,
        'estimate_error_z_m': error_z,
        'battery_v': battery,
    }
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
            'estimate_age_s': now - estimate_time,
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


def print_phase_summary(phase, rows, pose_stale_timeout):
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


def make_output_path(output):
    if output:
        path = Path(output)
    else:
        timestamp = time.strftime('%Y%m%d-%H%M%S')
        path = Path(DEFAULT_OUTPUT_DIR) / f"mocap-estimator-world-frame-{timestamp}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run_phase(args, logger, started_at, phase, description, mocap_state, estimate_state):
    print("")
    print("=" * 72)
    print(f"[MOVE] Place the drone at: {description}")
    print("[MOVE] Keep the nose/front pointed the same direction as the start.")
    input("[MOVE] Once it is still, press ENTER to record this phase...")
    print(f"[RECORD] {phase}: holding for {args.hold_duration:.1f}s")

    phase_started_at = time.time()
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

    print_phase_summary(phase, rows, args.pose_stale_timeout)


def run(args):
    runtime = load_runtime_modules()
    runtime['cflib_crtp'].init_drivers()

    output_path = make_output_path(args.output)
    mocap_state = MocapState()
    estimate_state = EstimateState()
    mocap_reader = MocapReader(runtime['motioncapture'], args.host, args.body, mocap_state)
    logger = CsvLogger(output_path)
    estimate_logconf = None

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
            estimate_logconf = setup_estimate_logger(cf, runtime['LogConfig'], estimate_state)
            time.sleep(0.8)
            wait_for_estimate(estimate_state, MOCAP_TIMEOUT)

            mocap_reader.on_pose = lambda x, y, z, quat: send_extpose_or_extpos(
                cf,
                args.pose_mode,
                x,
                y,
                z,
                quat,
            )
            print("[INFO] Configuring Kalman estimator for external pose...")
            if args.pose_mode == 'extpose':
                cf.param.set_value('locSrv.extQuatStdDev', args.orientation_std_dev)
            cf.param.set_value('stabilizer.estimator', '2')
            time.sleep(0.5)

            print("[INFO] Resetting estimator while external pose is streaming...")
            runtime['reset_estimator'](cf)
            time.sleep(args.settle_duration)

            started_at = time.time()
            for phase, description in DEFAULT_PHASES:
                run_phase(args, logger, started_at, phase, description, mocap_state, estimate_state)

    finally:
        if estimate_logconf is not None:
            estimate_logconf.stop()
        mocap_reader.close()
        logger.close()

    print("=" * 72)
    print("[DONE]")
    print(f"log: {output_path}")
    print(f"rows: {logger.rows}")
    print("=" * 72)


def parse_args():
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
    args = parser.parse_args()

    if args.hold_duration <= 0.0:
        raise ValueError("--hold-duration must be greater than zero")
    if args.settle_duration < 0.0:
        raise ValueError("--settle-duration must be greater than or equal to zero")
    if args.rate_hz <= 0.0:
        raise ValueError("--rate-hz must be greater than zero")
    if args.pose_stale_timeout <= 0.0:
        raise ValueError("--pose-stale-timeout must be greater than zero")
    return args


if __name__ == '__main__':
    run(parse_args())
