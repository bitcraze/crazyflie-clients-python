#!/usr/bin/env python3
"""
Guide and log a manual Logitech controller flight with OptiTrack/VRPN pose.

This script does not connect to or command the Crazyflie. That keeps it usable
while cfclient owns the Crazyradio link for GUI-assisted manual flight.
"""
import argparse
import csv
import fcntl
import os
import select
import struct
import time
from pathlib import Path
from threading import Lock
from threading import Thread


DEFAULT_CONTROLLER_DEVICE = '/dev/input/js1'
DEFAULT_HOST_NAME = '192.168.1.42:3883'
DEFAULT_RIGID_BODY_NAME = 'crazyflie_21'
DEFAULT_OUTPUT_DIR = 'flight_logs'
DEFAULT_GUIDED_PHASES = [
    (
        'floor_baseline',
        'Keep the drone on the floor, props idle, controller centered.',
    ),
    (
        'gentle_takeoff',
        'Increase thrust only until the drone lifts off into a low hover.',
    ),
    (
        'low_hover',
        'Hold a low hover with minimal pitch, roll, and yaw input.',
    ),
    (
        'pitch_forward_back',
        'Use small pitch inputs: forward, release, backward, release.',
    ),
    (
        'roll_right_left',
        'Use small roll inputs: right, release, left, release.',
    ),
    (
        'yaw_right_left',
        'Use small yaw inputs: right, release, left, release.',
    ),
    (
        'final_hover',
        'Return to a quiet low hover with sticks centered except thrust.',
    ),
    (
        'landing',
        'Land gently, then leave the drone still on the floor.',
    ),
]
DEFAULT_WORLD_FRAME_CALIBRATION_PHASES = [
    (
        'center_start',
        'Place the drone at the center/start position, nose/front in the stated direction, then keep it still.',
    ),
    (
        'front',
        'Place the drone toward the front of the cage, then keep it still.',
    ),
    (
        'center_after_front',
        'Return the drone to the center/start position, then keep it still.',
    ),
    (
        'back',
        'Place the drone toward the back of the cage, then keep it still.',
    ),
    (
        'center_after_back',
        'Return the drone to the center/start position, then keep it still.',
    ),
    (
        'left',
        'Place the drone toward the left side of the cage, then keep it still.',
    ),
    (
        'center_after_left',
        'Return the drone to the center/start position, then keep it still.',
    ),
    (
        'right',
        'Place the drone toward the right side of the cage, then keep it still.',
    ),
    (
        'center_after_right',
        'Return the drone to the center/start position, then keep it still.',
    ),
    (
        'up',
        'Lift the drone straight up to the intended hover height, then keep it still.',
    ),
    (
        'center_end',
        'Return the drone to the center/start position, then keep it still.',
    ),
]


DEFAULT_MOCAP_COVERAGE_PHASES = [
    (
        'center_floor',
        'Place the drone at cage center on the floor, nose/front fixed, then keep it still.',
    ),
    (
        'front_floor',
        'Place the drone near the front of the cage on the floor, then keep it still.',
    ),
    (
        'back_floor',
        'Place the drone near the back of the cage on the floor, then keep it still.',
    ),
    (
        'left_center_floor',
        'Place the drone at the left side center on the floor, then keep it still.',
    ),
    (
        'left_front_floor',
        'Place the drone at the left-front part of the cage on the floor, then keep it still.',
    ),
    (
        'left_back_floor',
        'Place the drone at the left-back part of the cage on the floor, then keep it still.',
    ),
    (
        'right_center_floor',
        'Place the drone at the right side center on the floor, then keep it still.',
    ),
    (
        'center_hover_height',
        'Lift the drone at cage center to intended hover height, then keep it still.',
    ),
    (
        'left_center_hover_height',
        'Lift the drone at the left side center to intended hover height, then keep it still.',
    ),
    (
        'left_front_hover_height',
        'Lift the drone at the left-front part of the cage to intended hover height, then keep it still.',
    ),
    (
        'left_back_hover_height',
        'Lift the drone at the left-back part of the cage to intended hover height, then keep it still.',
    ),
    (
        'center_end',
        'Return the drone to cage center on the floor, then keep it still.',
    ),
]

ROLL_AXIS = 0
PITCH_AXIS = 1
YAW_AXIS = 2
THRUST_AXIS = 3

MAX_ROLL_DEG = 30.0
MAX_PITCH_DEG = 30.0
MAX_YAWRATE_DEG_PER_S = 200.0
# Log the full Crazyflie raw thrust range instead of capping controller input.
MAX_THRUST = 65535
MIN_THRUST = 0
DEADZONE = 0.1

FLOOR_Z = 0.037

JS_EVENT_FMT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FMT)
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80


class ControllerState:
    def __init__(self):
        self._lock = Lock()
        self.axes = {}
        self.buttons = {}
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.thrust = 0.0
        self.thrust_axis_seen = False
        self.event_count = 0
        self.last_event_time = 0.0

    def update_axis(self, number, normalized):
        with self._lock:
            self.axes[number] = normalized
            if number == ROLL_AXIS:
                self.roll = apply_deadzone(normalized)
            elif number == PITCH_AXIS:
                self.pitch = apply_deadzone(-normalized)
            elif number == YAW_AXIS:
                self.yaw = apply_deadzone(normalized)
            elif number == THRUST_AXIS:
                self.thrust = (-normalized + 1.0) / 2.0
                self.thrust_axis_seen = True
            self.event_count += 1
            self.last_event_time = time.time()

    def update_button(self, number, value):
        with self._lock:
            self.buttons[number] = value
            self.event_count += 1
            self.last_event_time = time.time()

    def snapshot(self):
        with self._lock:
            roll_deg = self.roll * MAX_ROLL_DEG
            pitch_deg = self.pitch * MAX_PITCH_DEG
            yawrate = self.yaw * MAX_YAWRATE_DEG_PER_S
            thrust_raw = MIN_THRUST + self.thrust * (MAX_THRUST - MIN_THRUST)
            return {
                'roll_norm': self.roll,
                'pitch_norm': self.pitch,
                'yaw_norm': self.yaw,
                'thrust_norm': self.thrust,
                'roll_deg': roll_deg,
                'pitch_deg': pitch_deg,
                'yawrate_deg_s': yawrate,
                'thrust_raw': int(thrust_raw),
                'thrust_axis_seen': int(self.thrust_axis_seen),
                'button_5': self.buttons.get(5, 0),
                'button_9': self.buttons.get(9, 0),
                'event_count': self.event_count,
                'last_event_age_s': time.time() - self.last_event_time
                if self.last_event_time else '',
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


class GuidedPhaseController(Thread):
    def __init__(self, phases):
        Thread.__init__(self)
        self.daemon = True
        self.phases = phases
        self._lock = Lock()
        self._phase_index = -1
        self._phase_name = 'preflight_wait'
        self._phase_started_at = time.time()
        self.done = False

    def run(self):
        print("\n[GUIDE] Guided manual flight plan:")
        for index, (name, description) in enumerate(self.phases, start=1):
            print(f"[GUIDE] {index}. {name}: {description}")

        try:
            for index, (name, description) in enumerate(self.phases, start=1):
                input(f"\n[GUIDE] Press Enter to start {index}/{len(self.phases)}: {name} ")
                with self._lock:
                    self._phase_index = index
                    self._phase_name = name
                    self._phase_started_at = time.time()
                print(f"[GUIDE] ACTIVE {name}: {description}")
                if index < len(self.phases):
                    print("[GUIDE] When complete, press Enter to start the next phase.")
                else:
                    print("[GUIDE] When complete, press Enter to finish logging.")

            input("\n[GUIDE] Finish guided logging now? ")
        except EOFError:
            print("\n[WARN] Stdin closed; guided phase labels will stop advancing.")
        finally:
            self.done = True

    def snapshot(self):
        with self._lock:
            now = time.time()
            return {
                'phase_index': self._phase_index,
                'phase_name': self._phase_name,
                'phase_elapsed_s': now - self._phase_started_at,
            }


class ControllerReader(Thread):
    def __init__(self, device_path, state):
        Thread.__init__(self)
        self.daemon = True
        self.device_path = device_path
        self.state = state
        self.error = None
        self._stay_open = True
        self._js_file = None

    def close(self):
        self._stay_open = False
        if self._js_file is not None:
            self._js_file.close()

    def run(self):
        try:
            self._js_file = open(self.device_path, 'rb')
            fcntl.fcntl(self._js_file.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
            print(f"[INFO] Controller opened: {self.device_path}")
            print_controller_name(self._js_file)

            while self._stay_open:
                readable, _, _ = select.select([self._js_file], [], [], 0.1)
                if not readable:
                    continue

                event_data = self._js_file.read(JS_EVENT_SIZE)
                if len(event_data) != JS_EVENT_SIZE:
                    continue

                _, value, event_type, number = struct.unpack(JS_EVENT_FMT, event_data)
                event_type &= ~JS_EVENT_INIT

                if event_type == JS_EVENT_AXIS:
                    self.state.update_axis(number, value / 32767.0)
                elif event_type == JS_EVENT_BUTTON:
                    self.state.update_button(number, value)
        except Exception as exc:
            self.error = exc


class MocapReader(Thread):
    def __init__(self, host_name, body_name, state):
        Thread.__init__(self)
        self.daemon = True
        self.host_name = host_name
        self.body_name = body_name
        self.state = state
        self.error = None
        self._stay_open = True

    def close(self):
        self._stay_open = False

    def run(self):
        try:
            import motioncapture

            mc = motioncapture.connect('vrpn', {'hostname': self.host_name})
            print(f"[INFO] Mocap connected, looking for '{self.body_name}'")
            found_body = False

            while self._stay_open:
                mc.waitForNextFrame()
                for name, obj in mc.rigidBodies.items():
                    if name != self.body_name:
                        continue
                    if not found_body:
                        print(f"[INFO] Found and tracking rigid body: {name}")
                        found_body = True
                    pos = obj.position
                    quat = obj.rotation
                    self.state.update((pos[0], pos[1], pos[2]), quat)
        except Exception as exc:
            self.error = exc


def apply_deadzone(value):
    if abs(value) < DEADZONE:
        return 0.0
    sign = 1 if value > 0 else -1
    return sign * (abs(value) - DEADZONE) / (1.0 - DEADZONE)


def print_controller_name(js_file):
    try:
        device_name_bytes = bytearray(64)
        fcntl.ioctl(js_file.fileno(), 0x80006a13, device_name_bytes)
        device_name = device_name_bytes.decode('utf-8').rstrip('\x00')
        print(f"[INFO] Controller device name: {device_name}")
    except OSError:
        pass


def find_controller_device(preferred):
    if os.path.exists(preferred):
        return preferred

    for i in range(10):
        candidate = f"/dev/input/js{i}"
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        f"No joystick device found. Tried preferred device {preferred} and /dev/input/js0..js9."
    )


def make_output_path(output, prefix='mocap-guided-manual-flight'):
    if output:
        path = Path(output)
    else:
        timestamp = time.strftime('%Y%m%d-%H%M%S')
        path = Path(DEFAULT_OUTPUT_DIR) / f"{prefix}-{timestamp}.csv"

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def mocap_snapshot_fields(mocap_state, start_position, previous_sample, fresh_age_threshold):
    position, quat, last_update, frame_count = mocap_state.snapshot()
    now = time.time()

    if position is None or quat is None:
        return {
            'mocap_x': '',
            'mocap_y': '',
            'mocap_z': '',
            'height_above_floor': '',
            'mocap_qx': '',
            'mocap_qy': '',
            'mocap_qz': '',
            'mocap_qw': '',
            'mocap_age_s': '',
            'mocap_frame_count': frame_count,
            'mocap_frame_delta': '',
            'mocap_fresh': 0,
            'mocap_vx_m_s': '',
            'mocap_vy_m_s': '',
            'mocap_vz_m_s': '',
            'horizontal_distance_from_start_m': '',
        }, previous_sample

    velocity = ('', '', '')
    frame_delta = ''
    if previous_sample is not None:
        previous_frame_count, previous_time, previous_position, previous_velocity = previous_sample
        frame_delta = frame_count - previous_frame_count
        if frame_count == previous_frame_count:
            velocity = previous_velocity
        else:
            dt = last_update - previous_time
            if dt > 0:
                velocity = tuple(
                    (position[index] - previous_position[index]) / dt
                    for index in range(3)
                )

    horizontal_distance = ''
    if start_position is not None:
        dx = position[0] - start_position[0]
        dy = position[1] - start_position[1]
        horizontal_distance = (dx * dx + dy * dy) ** 0.5

    fields = {
        'mocap_x': position[0],
        'mocap_y': position[1],
        'mocap_z': position[2],
        'height_above_floor': position[2] - FLOOR_Z,
        'mocap_qx': quat.x,
        'mocap_qy': quat.y,
        'mocap_qz': quat.z,
        'mocap_qw': quat.w,
        'mocap_age_s': now - last_update,
        'mocap_frame_count': frame_count,
        'mocap_frame_delta': frame_delta,
        'mocap_fresh': int(now - last_update <= fresh_age_threshold),
        'mocap_vx_m_s': velocity[0],
        'mocap_vy_m_s': velocity[1],
        'mocap_vz_m_s': velocity[2],
        'horizontal_distance_from_start_m': horizontal_distance,
    }
    return fields, (frame_count, last_update, position, velocity)


def build_fieldnames():
    return [
        'wall_time_s',
        'elapsed_s',
        'phase_index',
        'phase_name',
        'phase_elapsed_s',
        'roll_norm',
        'pitch_norm',
        'yaw_norm',
        'thrust_norm',
        'roll_deg',
        'pitch_deg',
        'yawrate_deg_s',
        'thrust_raw',
        'thrust_axis_seen',
        'button_5',
        'button_9',
        'event_count',
        'last_event_age_s',
        'mocap_x',
        'mocap_y',
        'mocap_z',
        'height_above_floor',
        'mocap_qx',
        'mocap_qy',
        'mocap_qz',
        'mocap_qw',
        'mocap_age_s',
        'mocap_frame_count',
        'mocap_frame_delta',
        'mocap_fresh',
        'mocap_vx_m_s',
        'mocap_vy_m_s',
        'mocap_vz_m_s',
        'horizontal_distance_from_start_m',
    ]


def blank_controller_fields():
    return {
        'roll_norm': '',
        'pitch_norm': '',
        'yaw_norm': '',
        'thrust_norm': '',
        'roll_deg': '',
        'pitch_deg': '',
        'yawrate_deg_s': '',
        'thrust_raw': '',
        'thrust_axis_seen': '',
        'button_5': '',
        'button_9': '',
        'event_count': '',
        'last_event_age_s': '',
    }


def wait_for_initial_mocap(mocap_state, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        position, _, _, _ = mocap_state.snapshot()
        if position is not None:
            return position
        time.sleep(0.05)
    return None



def update_mocap_stats(stats_by_phase, phase_name, mocap_fields, fresh_age_threshold):
    stats = stats_by_phase.setdefault(
        phase_name,
        {
            'samples': 0,
            'fresh': 0,
            'stale': 0,
            'blank': 0,
            'max_age_s': 0.0,
        },
    )
    stats['samples'] += 1
    age = mocap_fields['mocap_age_s']
    if age == '':
        stats['blank'] += 1
        stats['stale'] += 1
        return

    stats['max_age_s'] = max(stats['max_age_s'], age)
    if age <= fresh_age_threshold:
        stats['fresh'] += 1
    else:
        stats['stale'] += 1


def print_mocap_stats(stats_by_phase):
    if not stats_by_phase:
        return

    print("\n[COVERAGE SUMMARY]")
    for phase_name, stats in stats_by_phase.items():
        samples = stats['samples']
        fresh_pct = 100.0 * stats['fresh'] / samples if samples else 0.0
        print(
            f"{phase_name}: fresh={fresh_pct:.1f}% "
            f"stale={stats['stale']} blank={stats['blank']} "
            f"max_age={stats['max_age_s']:.3f}s samples={samples}"
        )

def log_flight(args):
    controller_state = ControllerState()
    mocap_state = MocapState()
    skip_controller = (
        args.no_controller
        or args.world_frame_calibration
        or args.mocap_coverage_check
    )
    controller_device = None if skip_controller else find_controller_device(args.controller)
    if args.mocap_coverage_check:
        output_prefix = 'mocap-coverage-check'
    elif args.world_frame_calibration:
        output_prefix = 'mocap-world-frame-calibration'
    else:
        output_prefix = 'mocap-guided-manual-flight'
    output_path = make_output_path(args.output, output_prefix)

    controller_reader = (
        None
        if skip_controller
        else ControllerReader(controller_device, controller_state)
    )
    mocap_reader = MocapReader(args.host, args.body, mocap_state)

    if controller_reader is not None:
        controller_reader.start()
    else:
        print("[INFO] Controller logging disabled; recording mocap only.")
    mocap_reader.start()

    start_position = None
    previous_sample = None
    rows_written = 0
    started_at = time.time()
    stopped_by_user = False
    phase_controller = None
    mocap_stats_by_phase = {}

    try:
        print("[INFO] Waiting for initial mocap pose...")
        start_position = wait_for_initial_mocap(mocap_state, args.mocap_timeout)
        if start_position is None:
            print("[WARN] No mocap pose before timeout; logging will continue with blank mocap fields")
        else:
            print(
                "[INFO] Initial mocap position: "
                f"x={start_position[0]:.3f}, y={start_position[1]:.3f}, z={start_position[2]:.3f}"
            )

        print(f"[INFO] Writing CSV log: {output_path}")
        if args.freeform:
            print("[INFO] Free-form mode. Start the cfclient/Logitech flight now.")
            print("[INFO] Press Ctrl+C here to stop logging.")
        else:
            phases = (
                DEFAULT_MOCAP_COVERAGE_PHASES
                if args.mocap_coverage_check
                else (
                    DEFAULT_WORLD_FRAME_CALIBRATION_PHASES
                    if args.world_frame_calibration
                    else DEFAULT_GUIDED_PHASES
                )
            )
            phase_controller = GuidedPhaseController(phases)
            phase_controller.start()
            print("[INFO] Guided mode is active. Follow the Enter prompts in this terminal.")
            print("[INFO] Press Ctrl+C here any time to abort logging.")

        with output_path.open('w', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=build_fieldnames())
            writer.writeheader()

            next_sample_time = time.time()
            while True:
                if args.duration and time.time() - started_at >= args.duration:
                    break
                if phase_controller is not None and phase_controller.done:
                    break

                if controller_reader is not None and controller_reader.error:
                    raise RuntimeError(f"Controller reader failed: {controller_reader.error}")
                if mocap_reader.error:
                    raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")

                now = time.time()
                if now < next_sample_time:
                    time.sleep(min(0.01, next_sample_time - now))
                    continue

                controller_fields = (
                    blank_controller_fields()
                    if controller_reader is None
                    else controller_state.snapshot()
                )
                mocap_fields, previous_sample = mocap_snapshot_fields(
                    mocap_state,
                    start_position,
                    previous_sample,
                    args.fresh_age_threshold,
                )
                row = {
                    'wall_time_s': now,
                    'elapsed_s': now - started_at,
                }
                if phase_controller is None:
                    row.update({
                        'phase_index': '',
                        'phase_name': 'freeform',
                        'phase_elapsed_s': now - started_at,
                    })
                else:
                    row.update(phase_controller.snapshot())
                row.update(controller_fields)
                row.update(mocap_fields)
                writer.writerow(row)
                rows_written += 1
                if args.mocap_coverage_check:
                    update_mocap_stats(
                        mocap_stats_by_phase,
                        row['phase_name'],
                        mocap_fields,
                        args.fresh_age_threshold,
                    )

                if rows_written % max(1, int(args.rate_hz * 2)) == 0:
                    print(
                        "[STATUS] "
                        f"rows={rows_written} elapsed={now - started_at:.1f}s "
                        f"phase={row['phase_name']} "
                        f"thrust={controller_fields['thrust_raw']} "
                        f"z={mocap_fields['mocap_z']}"
                    )

                next_sample_time += 1.0 / args.rate_hz
    except KeyboardInterrupt:
        stopped_by_user = True
    finally:
        if controller_reader is not None:
            controller_reader.close()
        mocap_reader.close()

    if stopped_by_user:
        print("\n[INTERRUPT] Logging stopped by user")
    if args.mocap_coverage_check:
        print_mocap_stats(mocap_stats_by_phase)
    print(f"[DONE] Wrote {rows_written} rows to {output_path}")
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Guide and log Logitech controller input plus VRPN mocap pose during GUI/manual flight."
    )
    parser.add_argument('--controller', default=DEFAULT_CONTROLLER_DEVICE)
    parser.add_argument('--host', default=DEFAULT_HOST_NAME)
    parser.add_argument('--body', default=DEFAULT_RIGID_BODY_NAME)
    parser.add_argument('--output', default=None)
    parser.add_argument('--duration', type=float, default=0.0, help="seconds; 0 means until Ctrl+C")
    parser.add_argument('--rate-hz', type=float, default=50.0)
    parser.add_argument('--mocap-timeout', type=float, default=8.0)
    parser.add_argument(
        '--fresh-age-threshold',
        type=float,
        default=0.25,
        help="seconds; mocap samples older than this count as stale in coverage logs",
    )
    parser.add_argument(
        '--freeform',
        action='store_true',
        help="disable Enter-driven phase prompts and log one continuous free-form flight",
    )
    parser.add_argument(
        '--world-frame-calibration',
        action='store_true',
        help="use Enter-driven no-flight center/front/back/left/right/up mocap phase labels",
    )
    parser.add_argument(
        '--mocap-coverage-check',
        action='store_true',
        help="use Enter-driven no-flight cage coverage labels and summarize mocap freshness by zone",
    )
    parser.add_argument(
        '--no-controller',
        action='store_true',
        help="record mocap only without opening a joystick device",
    )
    args = parser.parse_args()
    if args.world_frame_calibration and args.mocap_coverage_check:
        parser.error('--world-frame-calibration and --mocap-coverage-check are mutually exclusive')
    return args


def main():
    log_flight(parse_args())


if __name__ == '__main__':
    main()
