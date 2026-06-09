#!/usr/bin/env python3
"""
Manual thrust mapper with OptiTrack/VRPN logging and optional XY hold.

Default mode is guard-only: keyboard controls raw thrust, roll/pitch/yawrate are
zero, mocap pose is logged, and the drone is cut/disarmed if horizontal drift
gets too large. Optional hold-xy mode adds conservative mocap-based roll/pitch
corrections while thrust remains fully manual. Optional figure8 mode keeps
manual thrust but moves the horizontal target in a small figure-8 after a
manual climb reaches the trigger height.
"""

import argparse
import csv
import curses
import logging
import math
import time
from pathlib import Path
from threading import Lock
from threading import Thread

import cflib.crtp
import motioncapture
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie


DEFAULT_URI = 'radio://0/80/2M'
DEFAULT_HOST_NAME = '192.168.1.42:3883'
DEFAULT_RIGID_BODY_NAME = 'crazyflie_21'
DEFAULT_OUTPUT_DIR = 'flight_logs'

MIN_THRUST = 0
MAX_THRUST = 65535
DEFAULT_MAX_COMMANDED_THRUST = 36000
DEFAULT_MAX_HEIGHT_ABOVE_START = 0.35
DEFAULT_STEP = 250
DEFAULT_BIG_STEP = 1000
DEFAULT_AUTO_TAKEOFF_TARGET_THRUST = 35000
DEFAULT_AUTO_TAKEOFF_RAMP_RATE = 600.0
DEFAULT_AUTO_TAKEOFF_SLOW_ABOVE_PERCENT = 40.0
DEFAULT_AUTO_TAKEOFF_SLOW_RAMP_RATE = 300.0
DEFAULT_AUTO_TAKEOFF_PAUSE_ERROR = 0.06
DEFAULT_AUTO_TAKEOFF_HEIGHT = 0.16
DEFAULT_DESCENT_RAMP_RATE = 700.0
DEFAULT_XY_AGGRESSIVE_ERROR = 0.03
DEFAULT_XY_AGGRESSIVE_GAIN_SCALE = 2.5
DEFAULT_XY_RECOVERY_ERROR = 0.10
DEFAULT_XY_RECOVERY_GAIN_SCALE = 4.0
DEFAULT_XY_RECOVERY_MAX_ANGLE = 12.0
DEFAULT_XY_RECOVERY_LOW_ALTITUDE_MAX_ANGLE = 6.0
DEFAULT_LOW_ALTITUDE_MAX_ANGLE = 3.0
DEFAULT_FULL_CORRECTION_HEIGHT = 0.04
COMMAND_PERIOD = 0.02
LOG_PERIOD_MS = 100
POSE_STALE_TIMEOUT = 0.30
MOCAP_TIMEOUT = 8.0
LOW_BATTERY_VOLTAGE = 3.7
VERY_LOW_BATTERY_VOLTAGE = 3.5


class Telemetry:
    def __init__(self):
        self._lock = Lock()
        self.battery_voltage = 0.0
        self.estimate_z = 0.0

    def battery_callback(self, timestamp, data, logconf):
        del timestamp, logconf
        with self._lock:
            self.battery_voltage = data['pm.vbat']

    def altitude_callback(self, timestamp, data, logconf):
        del timestamp, logconf
        with self._lock:
            self.estimate_z = data['stateEstimate.z']

    def snapshot(self):
        with self._lock:
            return self.battery_voltage, self.estimate_z


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
                    self.state.update((pos[0], pos[1], pos[2]), obj.rotation)
        except Exception as exc:
            self.error = exc


class CsvLogger:
    def __init__(self, output_path):
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_file = self.output_path.open('w', newline='')
        self.writer = csv.DictWriter(self.csv_file, fieldnames=[
            'wall_time_s',
            'elapsed_s',
            'mode',
            'phase',
            'thrust_raw',
            'thrust_percent',
            'roll_cmd_deg',
            'pitch_cmd_deg',
            'yawrate_cmd_deg_s',
            'target_x',
            'target_y',
            'target_error_x_m',
            'target_error_y_m',
            'target_error_m',
            'xy_control_active',
            'figure8_active',
            'mocap_x',
            'mocap_y',
            'mocap_z',
            'mocap_qx',
            'mocap_qy',
            'mocap_qz',
            'mocap_qw',
            'yaw_deg',
            'mocap_yaw_deg',
            'body_yaw_offset_deg',
            'mocap_age_s',
            'mocap_frame_count',
            'drift_x_m',
            'drift_y_m',
            'horizontal_drift_m',
            'velocity_x_m_s',
            'velocity_y_m_s',
            'horizontal_speed_m_s',
            'body_error_x_m',
            'body_error_y_m',
            'body_velocity_x_m_s',
            'body_velocity_y_m_s',
            'xy_aggressive_active',
            'xy_recovery_active',
            'xy_gain_scale',
            'xy_angle_limit_deg',
            'low_altitude_angle_limit_active',
            'battery_v',
            'estimate_z',
            'height_above_start_m',
            'auto_takeoff_active',
            'auto_takeoff_ramp_rate_raw_s',
            'auto_takeoff_paused_for_error',
        ])
        self.writer.writeheader()

    def write(self, row):
        self.writer.writerow(row)
        self.csv_file.flush()

    def close(self):
        self.csv_file.close()


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def make_output_path(output):
    if output:
        return Path(output)
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    return Path(DEFAULT_OUTPUT_DIR) / f"mocap-vertical-thrust-map-{timestamp}.csv"


def pose_age(mocap_state):
    _, _, last_update, _ = mocap_state.snapshot()
    if last_update == 0.0:
        return float('inf')
    return time.time() - last_update


def wait_for_fresh_pose(mocap_state, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pose_age(mocap_state) <= POSE_STALE_TIMEOUT:
            position, quat, _, frames = mocap_state.snapshot()
            print(
                "[MOCAP] Fresh pose: "
                f"pos=({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) "
                f"quat=({quat.x:.3f}, {quat.y:.3f}, {quat.z:.3f}, {quat.w:.3f}) "
                f"frames={frames}"
            )
            return position
        time.sleep(0.05)
    raise RuntimeError("No fresh mocap pose received before timeout")


def send_zero_thrust(cf, count=10, send_stop=True):
    for _ in range(count):
        cf.commander.send_setpoint(0.0, 0.0, 0.0, 0)
        time.sleep(COMMAND_PERIOD)
    if send_stop:
        cf.commander.send_stop_setpoint()


def yaw_from_quat(quat):
    siny_cosp = 2.0 * (quat.w * quat.z + quat.x * quat.y)
    cosy_cosp = 1.0 - 2.0 * (quat.y * quat.y + quat.z * quat.z)
    return math.atan2(siny_cosp, cosy_cosp)


def rotate_world_to_body(world_x, world_y, yaw_rad):
    cos_yaw = math.cos(yaw_rad)
    sin_yaw = math.sin(yaw_rad)
    return (
        cos_yaw * world_x + sin_yaw * world_y,
        -sin_yaw * world_x + cos_yaw * world_y,
    )


def figure8_target(args, center_position, elapsed_s):
    phase = 2.0 * math.pi * elapsed_s / args.figure8_period
    target_x = center_position[0] + args.figure8_radius_x * math.sin(phase)
    target_y = center_position[1] + args.figure8_radius_y * math.sin(phase) * math.cos(phase)
    return target_x, target_y


def compute_xy_correction(args, target_position, position, quat, velocity_x, velocity_y):
    mocap_yaw_rad = yaw_from_quat(quat)
    mocap_yaw_deg = math.degrees(mocap_yaw_rad)
    if args.fixed_body_yaw_deg is None:
        yaw_rad = mocap_yaw_rad + math.radians(args.body_yaw_offset_deg)
    else:
        yaw_rad = math.radians(args.fixed_body_yaw_deg)
    yaw_deg = math.degrees(yaw_rad)
    error_x = target_position[0] - position[0]
    error_y = target_position[1] - position[1]
    body_error_x, body_error_y = rotate_world_to_body(error_x, error_y, yaw_rad)
    body_velocity_x, body_velocity_y = rotate_world_to_body(velocity_x, velocity_y, yaw_rad)

    if args.mode == 'guard-only':
        return {
            'roll': 0.0,
            'pitch': 0.0,
            'yaw_deg': yaw_deg,
            'mocap_yaw_deg': mocap_yaw_deg,
            'body_error_x': body_error_x,
            'body_error_y': body_error_y,
            'body_velocity_x': body_velocity_x,
            'body_velocity_y': body_velocity_y,
            'xy_aggressive_active': False,
            'xy_recovery_active': False,
            'xy_gain_scale': 1.0,
        }

    body_error = math.sqrt(body_error_x * body_error_x + body_error_y * body_error_y)
    recovery_active = body_error >= args.xy_recovery_error
    aggressive_active = body_error >= args.xy_aggressive_error
    if recovery_active:
        gain_scale = args.xy_recovery_gain_scale
    elif aggressive_active:
        gain_scale = args.xy_aggressive_gain_scale
    else:
        gain_scale = 1.0
    kp_xy = args.kp_xy * gain_scale
    kd_xy = args.kd_xy * gain_scale
    correction_x = kp_xy * body_error_x - kd_xy * body_velocity_x
    correction_y = kp_xy * body_error_y - kd_xy * body_velocity_y
    pitch = args.pitch_sign * correction_x
    roll = args.roll_sign * correction_y
    return {
        'roll': clamp(roll, -args.xy_recovery_max_angle_deg, args.xy_recovery_max_angle_deg),
        'pitch': clamp(pitch, -args.xy_recovery_max_angle_deg, args.xy_recovery_max_angle_deg),
        'yaw_deg': yaw_deg,
        'mocap_yaw_deg': mocap_yaw_deg,
        'body_error_x': body_error_x,
        'body_error_y': body_error_y,
        'body_velocity_x': body_velocity_x,
        'body_velocity_y': body_velocity_y,
        'xy_aggressive_active': aggressive_active,
        'xy_recovery_active': recovery_active,
        'xy_gain_scale': gain_scale,
    }


def low_altitude_angle_limit(args, height_above_start):
    if args.full_correction_height <= 0.0:
        return args.max_angle_deg, False
    if height_above_start >= args.full_correction_height:
        return args.max_angle_deg, False

    height_fraction = clamp(height_above_start / args.full_correction_height, 0.0, 1.0)
    angle_limit = args.low_altitude_max_angle_deg + (
        args.max_angle_deg - args.low_altitude_max_angle_deg
    ) * height_fraction
    return angle_limit, True


def add_line(stdscr, y, x, text):
    max_y, max_x = stdscr.getmaxyx()
    if y >= max_y or x >= max_x:
        return
    available = max_x - x - 1
    if available <= 0:
        return
    stdscr.addstr(y, x, text[:available])


def draw(stdscr, state):
    thrust = state['thrust']
    thrust_pct = 100.0 * thrust / MAX_THRUST
    stdscr.erase()
    add_line(stdscr, 0, 0, "Mocap Vertical Thrust Mapper")
    add_line(stdscr, 2, 0, "Controls:")
    add_line(stdscr, 3, 2, "UP / DOWN        thrust +/- small step")
    add_line(stdscr, 4, 2, "PAGEUP / PAGEDN  thrust + big step / slow descent")
    add_line(stdscr, 5, 2, "SPACE            cut thrust to zero")
    add_line(stdscr, 6, 2, "q or ESC         cut, disarm, exit")
    add_line(stdscr, 8, 0, f"Mode: {state['mode']}")
    add_line(
        stdscr,
        9,
        0,
        f"Phase: {state['phase']} | Auto takeoff: {state['auto_takeoff_state']} "
        f"| Descent: {state['descent_state']}"
    )
    add_line(stdscr, 10, 0, f"Thrust: {thrust:5d} / {MAX_THRUST} ({thrust_pct:5.1f}%)")
    add_line(stdscr, 11, 0, f"Roll/Pitch cmd: {state['roll']:+.2f} / {state['pitch']:+.2f} deg")
    add_line(stdscr, 12, 0, f"Mocap pos: x={state['x']:.3f} y={state['y']:.3f} z={state['z']:.3f}")
    add_line(stdscr, 13, 0, f"Target: x={state['target_x']:.3f} y={state['target_y']:.3f} | figure8={state['figure8_state']}")
    add_line(stdscr, 14, 0, f"Target error: {state['target_error']:.3f} m")
    add_line(stdscr, 15, 0, f"Drift: x={state['dx']:+.3f} y={state['dy']:+.3f} total={state['drift']:.3f} m")
    add_line(stdscr, 16, 0, f"Speed: x={state['vx']:+.3f} y={state['vy']:+.3f} total={state['speed']:.3f} m/s")
    add_line(stdscr, 17, 0, f"Yaw: {state['yaw_deg']:+.1f} deg | Body err: x={state['body_error_x']:+.3f} y={state['body_error_y']:+.3f}")
    aggressive = "on" if state['xy_aggressive_active'] else "off"
    recovery = " recovery" if state['xy_recovery_active'] else ""
    low_limit = " low-alt" if state['low_altitude_angle_limit_active'] else ""
    add_line(
        stdscr,
        18,
        0,
        f"XY aggressive: {aggressive}{recovery} | gain scale: {state['xy_gain_scale']:.1f}x "
        f"| angle cap: {state['xy_angle_limit_deg']:.1f}deg{low_limit}"
    )
    add_line(stdscr, 19, 0, f"Battery: {state['battery']:.2f} V | Estimator z: {state['estimate_z']:.2f} m")
    guard_state = "active" if state['drift_guard_active'] else "armed after liftoff/thrust"
    add_line(stdscr, 20, 0, f"Drift guard: {guard_state}")
    add_line(stdscr, 21, 0, state['message'])
    add_line(stdscr, 22, 0, "a toggles auto-ramp. f starts figure-8 after hold. PgDn slow-descends.")
    add_line(stdscr, 23, 0, "q/ESC/SPACE cut immediately. Keep physical power-off ready.")
    stdscr.refresh()


def run_keyboard_loop(
    stdscr,
    cf,
    args,
    mocap_state,
    mocap_reader,
    telemetry,
    start_position,
    logger,
    last_thrust_holder,
):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    thrust = 0
    message = "Starting at zero thrust."
    started_at = time.time()
    last_loop_at = started_at
    last_draw = 0.0
    last_logged_frame = None
    previous_velocity_sample = None
    velocity_x = 0.0
    velocity_y = 0.0
    position = start_position
    target_x = start_position[0]
    target_y = start_position[1]
    control_center_x = start_position[0]
    control_center_y = start_position[1]
    xy_control_active = (
        args.mode == 'guard-only'
        or (args.mode in ('hold-xy', 'figure8') and not args.xy_active_after_height)
    )
    figure8_started_at = None
    figure8_ready_since = None
    auto_takeoff_active = args.auto_takeoff
    auto_takeoff_started_at = started_at if auto_takeoff_active else None
    auto_takeoff_done = False
    takeoff_ramp_rate = 0.0
    takeoff_paused_for_error = False
    descent_active = False
    manual_figure8_requested = False
    dx = 0.0
    dy = 0.0
    drift = 0.0
    target_error = 0.0
    horizontal_speed = 0.0
    battery = 0.0
    estimate_z = 0.0
    correction = {
        'roll': 0.0,
        'pitch': 0.0,
        'yaw_deg': 0.0,
        'body_error_x': 0.0,
        'body_error_y': 0.0,
        'body_velocity_x': 0.0,
        'body_velocity_y': 0.0,
        'xy_aggressive_active': False,
        'xy_recovery_active': False,
        'xy_gain_scale': 1.0,
    }
    xy_angle_limit = args.max_angle_deg
    low_altitude_angle_limit_active = False

    while True:
        now = time.time()
        loop_dt = max(0.0, now - last_loop_at)
        last_loop_at = now

        if mocap_reader.error:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")

        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):
            thrust = 0
            last_thrust_holder['value'] = thrust
            send_zero_thrust(cf, count=3)
            message = "Exit requested."
            break
        if key == ord(' '):
            thrust = 0
            auto_takeoff_active = False
            descent_active = False
            message = "Thrust cut to zero."
        elif key == curses.KEY_UP:
            thrust = clamp(thrust + args.step, MIN_THRUST, args.max_commanded_thrust)
            auto_takeoff_active = False
            descent_active = False
            message = f"Thrust increased by {args.step}."
        elif key == curses.KEY_DOWN:
            thrust = clamp(thrust - args.step, MIN_THRUST, args.max_commanded_thrust)
            auto_takeoff_active = False
            descent_active = False
            message = f"Thrust decreased by {args.step}."
        elif key == curses.KEY_PPAGE:
            thrust = clamp(thrust + args.big_step, MIN_THRUST, args.max_commanded_thrust)
            auto_takeoff_active = False
            descent_active = False
            message = f"Thrust increased by {args.big_step}."
        elif key == curses.KEY_NPAGE:
            auto_takeoff_active = False
            descent_active = True
            message = f"Slow descent ramp active at {args.descent_ramp_rate:.0f} raw/s."
        elif key in (ord('a'), ord('A')):
            auto_takeoff_active = not auto_takeoff_active
            auto_takeoff_started_at = now if auto_takeoff_active else None
            auto_takeoff_done = False
            descent_active = False
            message = "Auto takeoff ramp enabled." if auto_takeoff_active else "Auto takeoff ramp disabled."
        elif key in (ord('f'), ord('F')) and args.mode == 'figure8':
            manual_figure8_requested = True
        last_thrust_holder['value'] = thrust

        if pose_age(mocap_state) > args.pose_stale_timeout:
            raise RuntimeError("Mocap pose went stale during flight")

        position, quat, last_update, frame_count = mocap_state.snapshot()
        if previous_velocity_sample is None:
            previous_velocity_sample = (position, last_update, frame_count)
        elif frame_count != previous_velocity_sample[2]:
            previous_position, previous_time, _ = previous_velocity_sample
            dt = last_update - previous_time
            if dt > 0.0:
                measured_vx = (position[0] - previous_position[0]) / dt
                measured_vy = (position[1] - previous_position[1]) / dt
                velocity_x = (
                    args.velocity_smoothing * velocity_x
                    + (1.0 - args.velocity_smoothing) * measured_vx
                )
                velocity_y = (
                    args.velocity_smoothing * velocity_y
                    + (1.0 - args.velocity_smoothing) * measured_vy
                )
            previous_velocity_sample = (position, last_update, frame_count)

        dx = position[0] - start_position[0]
        dy = position[1] - start_position[1]
        drift = math.sqrt(dx * dx + dy * dy)
        horizontal_speed = math.sqrt(velocity_x * velocity_x + velocity_y * velocity_y)
        height_above_start = position[2] - start_position[2]
        locked_target_error = math.sqrt(
            (control_center_x - position[0]) * (control_center_x - position[0])
            + (control_center_y - position[1]) * (control_center_y - position[1])
        )
        if args.max_height_above_start is not None and height_above_start > args.max_height_above_start:
            raise RuntimeError(
                "Height above start "
                f"{height_above_start:.3f}m exceeded {args.max_height_above_start:.3f}m"
            )

        if auto_takeoff_active:
            if auto_takeoff_started_at is None:
                auto_takeoff_started_at = now
            if now - auto_takeoff_started_at > args.auto_takeoff_max_seconds:
                auto_takeoff_active = False
                auto_takeoff_done = True
                message = "Auto takeoff ramp timed out; holding current thrust."
            elif height_above_start >= args.auto_takeoff_height:
                auto_takeoff_active = False
                auto_takeoff_done = True
                message = (
                    "Auto takeoff height reached; holding current thrust. "
                    "Use PgDn to descend."
                )
            else:
                slow_above_thrust = int(MAX_THRUST * args.auto_takeoff_slow_above_percent / 100.0)
                takeoff_ramp_rate = args.auto_takeoff_ramp_rate
                if thrust >= slow_above_thrust:
                    takeoff_ramp_rate = args.auto_takeoff_slow_ramp_rate
                takeoff_paused_for_error = (
                    thrust >= slow_above_thrust
                    and locked_target_error >= args.auto_takeoff_pause_error
                )
                if takeoff_paused_for_error:
                    takeoff_ramp_rate = 0.0
                    message = (
                        "Auto takeoff paused thrust increase for XY correction "
                        f"(error {locked_target_error:.2f}m). SPACE cuts, PgDn descends."
                    )
                else:
                    thrust = int(clamp(
                        thrust + takeoff_ramp_rate * loop_dt,
                        MIN_THRUST,
                        min(args.auto_takeoff_target_thrust, args.max_commanded_thrust),
                    ))
                    message = (
                        f"Auto takeoff ramping at {takeoff_ramp_rate:.0f} raw/s while holding start X/Y. "
                        "SPACE cuts, PgDn descends."
                    )
            last_thrust_holder['value'] = thrust

        if descent_active:
            takeoff_ramp_rate = 0.0
            takeoff_paused_for_error = False
            thrust = int(clamp(
                thrust - args.descent_ramp_rate * loop_dt,
                MIN_THRUST,
                args.max_commanded_thrust,
            ))
            if thrust <= MIN_THRUST:
                descent_active = False
                message = "Slow descent ramp reached zero thrust."
            else:
                message = (
                    "Slow descent ramp lowering thrust. "
                    "UP/PgUp cancel and raise; SPACE cuts."
                )
            last_thrust_holder['value'] = thrust

        figure8_active = False
        if args.mode in ('hold-xy', 'figure8') and args.xy_active_after_height and not xy_control_active:
            if height_above_start >= args.control_activation_height:
                xy_control_active = True
                control_center_x = position[0]
                control_center_y = position[1]
                target_x = control_center_x
                target_y = control_center_y
                locked_target_error = 0.0
                message = "XY control active; holding current hover X/Y target."
            else:
                target_x = position[0]
                target_y = position[1]
                message = (
                    "Climb manually to "
                    f"{args.control_activation_height:.2f}m above start, then press f to start figure-8."
                )

        if args.mode == 'figure8':
            if figure8_started_at is None:
                if manual_figure8_requested:
                    if xy_control_active and locked_target_error <= args.figure8_start_max_error:
                        figure8_started_at = now
                        message = "Figure-8 manually started from current hover target."
                    else:
                        message = (
                            "Figure-8 start rejected: XY hold is not ready or target error is too high."
                        )
                    manual_figure8_requested = False
                figure8_ready = (
                    xy_control_active
                    and height_above_start >= args.figure8_trigger_height
                    and locked_target_error <= args.figure8_start_max_error
                    and (not auto_takeoff_active)
                    and (not args.figure8_manual_start)
                )
                if figure8_ready:
                    if figure8_ready_since is None:
                        figure8_ready_since = now
                    if now - figure8_ready_since >= args.figure8_stable_hold_s:
                        figure8_started_at = now
                        message = (
                            "Figure-8 active from current hover target. "
                            "Keep altitude with thrust; PgDn descends, q cuts."
                        )
                elif xy_control_active and args.figure8_manual_start:
                    message = (
                        "Holding current hover X/Y. Press f when ready for figure-8; "
                        "keep altitude with thrust."
                    )
                elif xy_control_active:
                    figure8_ready_since = None
                    message = (
                        "Holding start X/Y. Figure-8 waits for height "
                        f"{args.figure8_trigger_height:.2f}m, target error "
                        f"<={args.figure8_start_max_error:.2f}m, and stable hold."
                    )

            if figure8_started_at is not None:
                figure8_active = True
                target_x, target_y = figure8_target(
                    args,
                    (control_center_x, control_center_y),
                    now - figure8_started_at,
                )
            elif xy_control_active:
                target_x = control_center_x
                target_y = control_center_y
            else:
                target_x = start_position[0]
                target_y = start_position[1]
        elif args.mode == 'hold-xy' and xy_control_active:
            target_x = control_center_x
            target_y = control_center_y

        target_error_x = target_x - position[0]
        target_error_y = target_y - position[1]
        target_error = math.sqrt(target_error_x * target_error_x + target_error_y * target_error_y)
        drift_guard_active = (
            thrust >= args.drift_guard_min_thrust
            or position[2] >= start_position[2] + args.drift_guard_min_height
        )
        if drift_guard_active and drift > args.max_horizontal_drift:
            raise RuntimeError(
                f"Horizontal drift {drift:.3f}m exceeded {args.max_horizontal_drift:.3f}m"
            )
        if (
            drift_guard_active
            and xy_control_active
            and args.max_target_error is not None
            and target_error > args.max_target_error
        ):
            raise RuntimeError(
                f"Target error {target_error:.3f}m exceeded {args.max_target_error:.3f}m"
            )

        if xy_control_active:
            correction = compute_xy_correction(
                args,
                (target_x, target_y),
                position,
                quat,
                velocity_x,
                velocity_y,
            )
        else:
            correction = {
                'roll': 0.0,
                'pitch': 0.0,
                'yaw_deg': (
                    math.degrees(yaw_from_quat(quat) + math.radians(args.body_yaw_offset_deg))
                    if args.fixed_body_yaw_deg is None
                    else args.fixed_body_yaw_deg
                ),
                'mocap_yaw_deg': math.degrees(yaw_from_quat(quat)),
                'body_error_x': 0.0,
                'body_error_y': 0.0,
                'body_velocity_x': 0.0,
                'body_velocity_y': 0.0,
                'xy_aggressive_active': False,
                'xy_recovery_active': False,
                'xy_gain_scale': 1.0,
            }
        xy_angle_limit, low_altitude_angle_limit_active = low_altitude_angle_limit(
            args,
            height_above_start,
        )
        if correction['xy_recovery_active']:
            if low_altitude_angle_limit_active:
                xy_angle_limit = max(xy_angle_limit, args.xy_recovery_low_altitude_max_angle_deg)
            else:
                xy_angle_limit = max(xy_angle_limit, args.xy_recovery_max_angle_deg)
        roll = clamp(correction['roll'], -xy_angle_limit, xy_angle_limit)
        pitch = clamp(correction['pitch'], -xy_angle_limit, xy_angle_limit)
        cf.commander.send_setpoint(roll, pitch, 0.0, thrust)

        battery, estimate_z = telemetry.snapshot()
        now = time.time()
        if figure8_active:
            phase = 'figure8'
        elif auto_takeoff_active:
            phase = 'auto-takeoff'
        elif auto_takeoff_done:
            phase = 'hold-after-takeoff'
        elif xy_control_active:
            phase = 'xy-hold'
        else:
            phase = 'manual-takeoff'
        if frame_count != last_logged_frame:
            logger.write({
                'wall_time_s': now,
                'elapsed_s': now - started_at,
                'mode': args.mode,
                'phase': phase,
                'thrust_raw': thrust,
                'thrust_percent': 100.0 * thrust / MAX_THRUST,
                'roll_cmd_deg': roll,
                'pitch_cmd_deg': pitch,
                'yawrate_cmd_deg_s': 0.0,
                'target_x': target_x,
                'target_y': target_y,
                'target_error_x_m': target_error_x,
                'target_error_y_m': target_error_y,
                'target_error_m': target_error,
                'xy_control_active': int(xy_control_active),
                'figure8_active': int(figure8_active),
                'mocap_x': position[0],
                'mocap_y': position[1],
                'mocap_z': position[2],
                'mocap_qx': quat.x,
                'mocap_qy': quat.y,
                'mocap_qz': quat.z,
                'mocap_qw': quat.w,
                'yaw_deg': correction['yaw_deg'],
                'mocap_yaw_deg': correction['mocap_yaw_deg'],
                'body_yaw_offset_deg': args.body_yaw_offset_deg,
                'mocap_age_s': now - last_update,
                'mocap_frame_count': frame_count,
                'drift_x_m': dx,
                'drift_y_m': dy,
                'horizontal_drift_m': drift,
                'velocity_x_m_s': velocity_x,
                'velocity_y_m_s': velocity_y,
                'horizontal_speed_m_s': horizontal_speed,
                'body_error_x_m': correction['body_error_x'],
                'body_error_y_m': correction['body_error_y'],
                'body_velocity_x_m_s': correction['body_velocity_x'],
                'body_velocity_y_m_s': correction['body_velocity_y'],
                'xy_aggressive_active': int(correction['xy_aggressive_active']),
                'xy_recovery_active': int(correction['xy_recovery_active']),
                'xy_gain_scale': correction['xy_gain_scale'],
                'xy_angle_limit_deg': xy_angle_limit,
                'low_altitude_angle_limit_active': int(low_altitude_angle_limit_active),
                'battery_v': battery,
                'estimate_z': estimate_z,
                'height_above_start_m': height_above_start,
                'auto_takeoff_active': int(auto_takeoff_active),
                'auto_takeoff_ramp_rate_raw_s': takeoff_ramp_rate if auto_takeoff_active else 0.0,
                'auto_takeoff_paused_for_error': int(takeoff_paused_for_error),
            })
            last_logged_frame = frame_count

        if now - last_draw >= 0.1:
            draw(stdscr, {
                'mode': args.mode,
                'phase': phase,
                'auto_takeoff_state': 'ramping' if auto_takeoff_active else 'off',
                'descent_state': 'ramping' if descent_active else 'off',
                'thrust': thrust,
                'roll': roll,
                'pitch': pitch,
                'target_x': target_x,
                'target_y': target_y,
                'target_error': target_error,
                'figure8_state': 'active' if figure8_active else 'waiting',
                'x': position[0],
                'y': position[1],
                'z': position[2],
                'dx': dx,
                'dy': dy,
                'drift': drift,
                'vx': velocity_x,
                'vy': velocity_y,
                'speed': horizontal_speed,
                'yaw_deg': correction['yaw_deg'],
                'body_error_x': correction['body_error_x'],
                'body_error_y': correction['body_error_y'],
                'xy_aggressive_active': correction['xy_aggressive_active'],
                'xy_recovery_active': correction['xy_recovery_active'],
                'xy_gain_scale': correction['xy_gain_scale'],
                'xy_angle_limit_deg': xy_angle_limit,
                'low_altitude_angle_limit_active': low_altitude_angle_limit_active,
                'battery': battery,
                'estimate_z': estimate_z,
                'message': message,
                'drift_guard_active': drift_guard_active,
            })
            last_draw = now

        time.sleep(COMMAND_PERIOD)

    draw(stdscr, {
        'mode': args.mode,
        'phase': 'stopped',
        'auto_takeoff_state': 'off',
        'descent_state': 'off',
        'thrust': thrust,
        'roll': 0.0,
        'pitch': 0.0,
        'target_x': target_x,
        'target_y': target_y,
        'target_error': math.sqrt(
            (position[0] - target_x) * (position[0] - target_x)
            + (position[1] - target_y) * (position[1] - target_y)
        ),
        'figure8_state': 'active' if figure8_started_at is not None else 'waiting',
        'x': position[0],
        'y': position[1],
        'z': position[2],
        'dx': dx,
        'dy': dy,
        'drift': drift,
        'vx': velocity_x,
        'vy': velocity_y,
        'speed': horizontal_speed,
        'yaw_deg': correction['yaw_deg'],
        'body_error_x': correction['body_error_x'],
        'body_error_y': correction['body_error_y'],
        'xy_aggressive_active': correction['xy_aggressive_active'],
        'xy_recovery_active': correction['xy_recovery_active'],
        'xy_gain_scale': correction['xy_gain_scale'],
        'xy_angle_limit_deg': xy_angle_limit,
        'low_altitude_angle_limit_active': low_altitude_angle_limit_active,
        'battery': battery,
        'estimate_z': estimate_z,
        'message': message,
        'drift_guard_active': False,
    })
    return thrust


def run(args):
    if args.figure8_period <= 0.0:
        raise ValueError("--figure8-period must be greater than zero")
    if args.figure8_trigger_height < 0.0:
        raise ValueError("--figure8-trigger-height must be zero or greater")
    if args.figure8_radius_x < 0.0 or args.figure8_radius_y < 0.0:
        raise ValueError("--figure8-radius-x and --figure8-radius-y must be zero or greater")
    if args.max_height_above_start is not None and args.max_height_above_start <= 0.0:
        raise ValueError("--max-height-above-start must be greater than zero")
    if args.max_target_error is not None and args.max_target_error <= 0.0:
        raise ValueError("--max-target-error must be greater than zero")
    if args.max_commanded_thrust < MIN_THRUST or args.max_commanded_thrust > MAX_THRUST:
        raise ValueError(
            f"--max-commanded-thrust must be between {MIN_THRUST} and {MAX_THRUST}"
        )
    if args.control_activation_height < 0.0:
        raise ValueError("--control-activation-height must be zero or greater")
    if args.kp_xy < 0.0 or args.kd_xy < 0.0:
        raise ValueError("--kp-xy and --kd-xy must be zero or greater")
    if args.xy_aggressive_error <= 0.0:
        raise ValueError("--xy-aggressive-error must be greater than zero")
    if args.xy_aggressive_gain_scale < 1.0:
        raise ValueError("--xy-aggressive-gain-scale must be at least 1.0")
    if args.xy_recovery_error <= args.xy_aggressive_error:
        raise ValueError("--xy-recovery-error must be greater than --xy-aggressive-error")
    if args.xy_recovery_gain_scale < args.xy_aggressive_gain_scale:
        raise ValueError("--xy-recovery-gain-scale must be at least --xy-aggressive-gain-scale")
    if args.max_angle_deg <= 0.0:
        raise ValueError("--max-angle-deg must be greater than zero")
    if args.low_altitude_max_angle_deg < 0.0:
        raise ValueError("--low-altitude-max-angle-deg must be zero or greater")
    if args.low_altitude_max_angle_deg > args.max_angle_deg:
        raise ValueError("--low-altitude-max-angle-deg must be no greater than --max-angle-deg")
    if args.xy_recovery_low_altitude_max_angle_deg < args.low_altitude_max_angle_deg:
        raise ValueError("--xy-recovery-low-altitude-max-angle-deg must be at least --low-altitude-max-angle-deg")
    if args.xy_recovery_max_angle_deg < args.max_angle_deg:
        raise ValueError("--xy-recovery-max-angle-deg must be at least --max-angle-deg")
    if args.full_correction_height <= 0.0:
        raise ValueError("--full-correction-height must be greater than zero")
    if args.auto_takeoff_target_thrust < MIN_THRUST or args.auto_takeoff_target_thrust > MAX_THRUST:
        raise ValueError(
            f"--auto-takeoff-target-thrust must be between {MIN_THRUST} and {MAX_THRUST}"
        )
    if args.auto_takeoff_ramp_rate <= 0.0:
        raise ValueError("--auto-takeoff-ramp-rate must be greater than zero")
    if args.auto_takeoff_slow_above_percent < 0.0 or args.auto_takeoff_slow_above_percent > 100.0:
        raise ValueError("--auto-takeoff-slow-above-percent must be between 0 and 100")
    if args.auto_takeoff_slow_ramp_rate <= 0.0:
        raise ValueError("--auto-takeoff-slow-ramp-rate must be greater than zero")
    if args.auto_takeoff_pause_error <= 0.0:
        raise ValueError("--auto-takeoff-pause-error must be greater than zero")
    if args.descent_ramp_rate <= 0.0:
        raise ValueError("--descent-ramp-rate must be greater than zero")
    if args.auto_takeoff_height <= 0.0:
        raise ValueError("--auto-takeoff-height must be greater than zero")
    if args.auto_takeoff_max_seconds <= 0.0:
        raise ValueError("--auto-takeoff-max-seconds must be greater than zero")
    if args.figure8_start_max_error <= 0.0:
        raise ValueError("--figure8-start-max-error must be greater than zero")
    if args.figure8_stable_hold_s < 0.0:
        raise ValueError("--figure8-stable-hold-s must be zero or greater")

    logging.basicConfig(level=logging.ERROR)
    cflib.crtp.init_drivers()

    output_path = make_output_path(args.output)
    mocap_state = MocapState()
    mocap_reader = MocapReader(args.host, args.body, mocap_state)
    telemetry = Telemetry()

    print("=" * 72)
    print("MOCAP VERTICAL THRUST MAPPER")
    print("=" * 72)
    print(f"URI: {args.uri}")
    print(f"Rigid body: {args.body}@{args.host}")
    print(f"Mode: {args.mode}")
    print(f"Output: {output_path}")
    print(f"Commanded thrust cap: {args.max_commanded_thrust}")
    print(f"Max horizontal drift: {args.max_horizontal_drift:.3f} m")
    if args.max_target_error is not None:
        print(f"Max target error: {args.max_target_error:.3f} m")
    if args.mode in ('hold-xy', 'figure8'):
        print(
            "XY control: "
            f"kp={args.kp_xy:.2f}, kd={args.kd_xy:.2f}, "
            f"max_angle={args.max_angle_deg:.1f} deg, "
            f"low_alt_angle={args.low_altitude_max_angle_deg:.1f} deg "
            f"until {args.full_correction_height:.2f}m, "
            f"aggressive_above={args.xy_aggressive_error:.2f}m, "
            f"aggressive_scale={args.xy_aggressive_gain_scale:.1f}x, "
            f"recovery_above={args.xy_recovery_error:.2f}m, "
            f"recovery_scale={args.xy_recovery_gain_scale:.1f}x, "
            f"recovery_angle={args.xy_recovery_max_angle_deg:.1f} deg, "
            f"roll_sign={args.roll_sign:+.0f}, pitch_sign={args.pitch_sign:+.0f}, "
            f"body_yaw_offset={args.body_yaw_offset_deg:+.1f} deg, "
            f"fixed_body_yaw={args.fixed_body_yaw_deg}"
        )
        if args.xy_active_after_height:
            print(
                "XY activation: "
                f"{args.control_activation_height:.3f} m above flight-start z, "
                "locked to current hover X/Y"
            )
        else:
            print("XY activation: immediate at zero thrust; locked to start X/Y")
    if args.auto_takeoff:
        slow_above_thrust = int(MAX_THRUST * args.auto_takeoff_slow_above_percent / 100.0)
        print(
            "Auto takeoff: "
            f"target_thrust={args.auto_takeoff_target_thrust}, "
            f"ramp={args.auto_takeoff_ramp_rate:.0f} raw/s, "
            f"slow_ramp={args.auto_takeoff_slow_ramp_rate:.0f} raw/s "
            f"above {args.auto_takeoff_slow_above_percent:.1f}% ({slow_above_thrust}), "
            f"pause_error={args.auto_takeoff_pause_error:.2f}m, "
            f"stop_height={args.auto_takeoff_height:.2f} m above start"
        )
    if args.mode == 'figure8':
        print(
            "Figure-8: "
            f"trigger_height={args.figure8_trigger_height:.2f} m above start, "
            f"radius_x={args.figure8_radius_x:.2f} m, "
            f"radius_y={args.figure8_radius_y:.2f} m, "
            f"period={args.figure8_period:.1f} s"
        )
    if args.max_height_above_start is not None:
        print(f"Max height above start: {args.max_height_above_start:.3f} m")
    print("Manual control is thrust only. Yaw is fixed at zero.")
    print("Close cfclient first; only one process can own the radio.")
    print("=" * 72)
    input("Press ENTER to connect mocap and Crazyflie, or Ctrl+C to abort...")

    mocap_reader.start()
    start_position = wait_for_fresh_pose(mocap_state, MOCAP_TIMEOUT)
    print(
        "[INFO] Holding horizontal target at start position: "
        f"x={start_position[0]:.3f}, y={start_position[1]:.3f}"
    )

    battery_logconf = LogConfig(name='Battery', period_in_ms=LOG_PERIOD_MS)
    battery_logconf.add_variable('pm.vbat', 'float')
    altitude_logconf = LogConfig(name='Altitude', period_in_ms=LOG_PERIOD_MS)
    altitude_logconf.add_variable('stateEstimate.z', 'float')

    logger = CsvLogger(output_path)
    last_thrust = 0
    last_thrust_holder = {'value': 0}
    try:
        with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache='./cache')) as scf:
            cf = scf.cf
            print("[INFO] Crazyflie connected.")

            cf.log.add_config(battery_logconf)
            battery_logconf.data_received_cb.add_callback(telemetry.battery_callback)
            battery_logconf.start()

            cf.log.add_config(altitude_logconf)
            altitude_logconf.data_received_cb.add_callback(telemetry.altitude_callback)
            altitude_logconf.start()
            time.sleep(0.8)

            battery, _ = telemetry.snapshot()
            print(f"[INFO] Battery: {battery:.2f} V")
            if battery < VERY_LOW_BATTERY_VOLTAGE:
                raise RuntimeError("Battery is very low. Do not fly.")
            elif battery < LOW_BATTERY_VOLTAGE:
                print("[WARN] Battery is low.")

            input("Press ENTER to arm and start at zero thrust, or Ctrl+C to abort...")
            print("[INFO] Sending arm request...")
            cf.platform.send_arming_request(True)
            time.sleep(1.0)
            print("[INFO] Priming commander with zero-thrust setpoints...")
            send_zero_thrust(cf, count=25, send_stop=False)
            start_position = wait_for_fresh_pose(mocap_state, MOCAP_TIMEOUT)
            print(
                "[INFO] Reset horizontal target at flight start: "
                f"x={start_position[0]:.3f}, y={start_position[1]:.3f}, z={start_position[2]:.3f}"
            )

            last_thrust = curses.wrapper(
                run_keyboard_loop,
                cf,
                args,
                mocap_state,
                mocap_reader,
                telemetry,
                start_position,
                logger,
                last_thrust_holder,
            )

            print("\n[INFO] Flight loop ended.")
            send_zero_thrust(cf, count=25)
            cf.platform.send_arming_request(False)
            altitude_logconf.stop()
            battery_logconf.stop()
    finally:
        print("\n[SAFETY] Cutting thrust and closing resources...")
        try:
            if 'cf' in locals():
                send_zero_thrust(cf, count=25)
                cf.platform.send_arming_request(False)
        finally:
            logger.close()
            mocap_reader.close()
        print(f"[DONE] Wrote log: {output_path}")
        print(f"[DONE] Last commanded thrust: {max(last_thrust, last_thrust_holder['value'])}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uri', default=DEFAULT_URI)
    parser.add_argument('--host', default=DEFAULT_HOST_NAME)
    parser.add_argument('--body', default=DEFAULT_RIGID_BODY_NAME)
    parser.add_argument('--output', default=None)
    parser.add_argument('--mode', choices=('guard-only', 'hold-xy', 'figure8'), default='guard-only')
    parser.add_argument('--step', type=int, default=DEFAULT_STEP)
    parser.add_argument('--big-step', type=int, default=DEFAULT_BIG_STEP)
    parser.add_argument(
        '--max-commanded-thrust',
        type=int,
        default=DEFAULT_MAX_COMMANDED_THRUST,
        help='Upper limit for keyboard-commanded raw thrust.',
    )
    parser.add_argument('--max-horizontal-drift', type=float, default=0.20)
    parser.add_argument(
        '--max-target-error',
        type=float,
        default=None,
        help='Optional guard on distance from the moving target, meters.',
    )
    parser.add_argument('--drift-guard-min-thrust', type=int, default=10000)
    parser.add_argument('--drift-guard-min-height', type=float, default=0.03)
    parser.add_argument('--pose-stale-timeout', type=float, default=POSE_STALE_TIMEOUT)
    parser.add_argument('--kp-xy', type=float, default=12.0)
    parser.add_argument('--kd-xy', type=float, default=6.0)
    parser.add_argument(
        '--xy-aggressive-error',
        type=float,
        default=DEFAULT_XY_AGGRESSIVE_ERROR,
        help='Start boosted XY hold gains when body-frame XY error reaches this many meters.',
    )
    parser.add_argument(
        '--xy-aggressive-gain-scale',
        type=float,
        default=DEFAULT_XY_AGGRESSIVE_GAIN_SCALE,
        help='Multiplier applied to kp/kd when XY error exceeds --xy-aggressive-error.',
    )
    parser.add_argument(
        '--xy-recovery-error',
        type=float,
        default=DEFAULT_XY_RECOVERY_ERROR,
        help='Start the strongest XY recovery tier when body-frame error reaches this many meters.',
    )
    parser.add_argument(
        '--xy-recovery-gain-scale',
        type=float,
        default=DEFAULT_XY_RECOVERY_GAIN_SCALE,
        help='Multiplier applied to kp/kd in the strongest XY recovery tier.',
    )
    parser.add_argument(
        '--xy-recovery-max-angle-deg',
        type=float,
        default=DEFAULT_XY_RECOVERY_MAX_ANGLE,
        help='Roll/pitch cap during the strongest XY recovery tier after low-altitude limit clears.',
    )
    parser.add_argument(
        '--xy-recovery-low-altitude-max-angle-deg',
        type=float,
        default=DEFAULT_XY_RECOVERY_LOW_ALTITUDE_MAX_ANGLE,
        help='Roll/pitch cap during strongest recovery while still near the floor.',
    )
    parser.add_argument('--velocity-smoothing', type=float, default=0.7)
    parser.add_argument('--max-angle-deg', type=float, default=10.0)
    parser.add_argument(
        '--low-altitude-max-angle-deg',
        type=float,
        default=DEFAULT_LOW_ALTITUDE_MAX_ANGLE,
        help='Roll/pitch angle cap while still near the floor.',
    )
    parser.add_argument(
        '--full-correction-height',
        type=float,
        default=DEFAULT_FULL_CORRECTION_HEIGHT,
        help='Height above start where full --max-angle-deg correction becomes available.',
    )
    parser.add_argument('--roll-sign', type=float, choices=(-1.0, 1.0), default=-1.0)
    parser.add_argument('--pitch-sign', type=float, choices=(-1.0, 1.0), default=-1.0)
    parser.add_argument(
        '--body-yaw-offset-deg',
        type=float,
        default=0.0,
        help=(
            'Offset added to mocap yaw before converting world XY error into drone body axes. '
            'Use -90 when the drone nose points toward mocap -Y while mocap yaw reads near 0.'
        ),
    )
    parser.add_argument(
        '--fixed-body-yaw-deg',
        type=float,
        default=None,
        help=(
            'Use this yaw directly for XY correction instead of live mocap yaw. '
            'Useful when the rigid-body yaw jumps but the drone nose is physically aligned.'
        ),
    )
    parser.add_argument(
        '--control-activation-height',
        type=float,
        default=0.06,
        help='Height above flight-start mocap z before XY correction is enabled.',
    )
    parser.add_argument(
        '--xy-active-after-height',
        action='store_true',
        help='Delay XY correction until --control-activation-height. Default locks start X/Y immediately.',
    )
    parser.add_argument(
        '--auto-takeoff',
        action='store_true',
        help='Slowly ramp raw thrust while holding the start X/Y mocap target.',
    )
    parser.add_argument(
        '--auto-takeoff-target-thrust',
        type=int,
        default=DEFAULT_AUTO_TAKEOFF_TARGET_THRUST,
        help='Raw thrust cap for the automatic takeoff ramp.',
    )
    parser.add_argument(
        '--auto-takeoff-ramp-rate',
        type=float,
        default=DEFAULT_AUTO_TAKEOFF_RAMP_RATE,
        help='Raw thrust units per second during automatic takeoff.',
    )
    parser.add_argument(
        '--auto-takeoff-slow-above-percent',
        type=float,
        default=DEFAULT_AUTO_TAKEOFF_SLOW_ABOVE_PERCENT,
        help='Percent of full raw thrust where auto takeoff switches to the slower ramp.',
    )
    parser.add_argument(
        '--auto-takeoff-slow-ramp-rate',
        type=float,
        default=DEFAULT_AUTO_TAKEOFF_SLOW_RAMP_RATE,
        help='Raw thrust units per second during automatic takeoff above the slow-ramp threshold.',
    )
    parser.add_argument(
        '--auto-takeoff-pause-error',
        type=float,
        default=DEFAULT_AUTO_TAKEOFF_PAUSE_ERROR,
        help='Pause auto takeoff thrust increases above the slow threshold when start-X/Y error reaches this many meters.',
    )
    parser.add_argument(
        '--descent-ramp-rate',
        type=float,
        default=DEFAULT_DESCENT_RAMP_RATE,
        help='Raw thrust units per second removed while PgDn slow descent is active.',
    )
    parser.add_argument(
        '--auto-takeoff-height',
        type=float,
        default=DEFAULT_AUTO_TAKEOFF_HEIGHT,
        help='Height above flight-start mocap z where auto takeoff stops ramping.',
    )
    parser.add_argument(
        '--auto-takeoff-max-seconds',
        type=float,
        default=70.0,
        help='Maximum time spent auto-ramping before holding current thrust.',
    )
    parser.add_argument(
        '--figure8-trigger-height',
        type=float,
        default=0.25,
        help='Height above the flight-start mocap z before figure-8 begins.',
    )
    parser.add_argument(
        '--figure8-radius-x',
        type=float,
        default=0.06,
        help='Figure-8 horizontal radius in mocap x, meters.',
    )
    parser.add_argument(
        '--figure8-radius-y',
        type=float,
        default=0.05,
        help='Figure-8 horizontal radius in mocap y, meters.',
    )
    parser.add_argument(
        '--figure8-period',
        type=float,
        default=24.0,
        help='Seconds for one full figure-8 cycle.',
    )
    parser.add_argument(
        '--figure8-start-max-error',
        type=float,
        default=0.08,
        help='Max locked-target error allowed before auto/manual figure-8 start.',
    )
    parser.add_argument(
        '--figure8-stable-hold-s',
        type=float,
        default=2.0,
        help='Seconds of stable locked XY hold required before automatic figure-8 start.',
    )
    parser.add_argument(
        '--figure8-manual-start',
        action='store_true',
        help='Require pressing f before starting the figure-8 after delayed/manual hover activation.',
    )
    parser.add_argument(
        '--max-height-above-start',
        type=float,
        default=DEFAULT_MAX_HEIGHT_ABOVE_START,
        help='Optional safety ceiling above flight-start mocap z, meters.',
    )
    return parser.parse_args()


if __name__ == '__main__':
    run(parse_args())
