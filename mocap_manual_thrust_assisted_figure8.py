#!/usr/bin/env python3
"""
Manual-thrust Crazyflie flight with mocap-assisted roll, pitch, yaw, and figure-8.

This is intentionally a script you tune by editing the constants below. The
pilot owns vertical thrust at all times. The script only commands:

- roll/pitch to hold or move the horizontal mocap X/Y target
- yawrate to hold the starting heading
- optional keyboard attitude trims on top of the mocap assist
- stale-mocap forced descent/abort behavior, plus safety cuts if the drone
  leaves the tight flight box, climbs too fast, or height gets too high

Recommended first flights:

1. Run this file.
2. Press R to ramp near takeoff thrust, then use Up taps into a low hover.
3. Use A/D, W/S, and J/L only as small trims while learning the response.
4. Do not press F until it can hold near the start X/Y for several seconds.
5. Press F to start/stop the tiny figure-8.
6. Use PgDn for normal slow descent. Space/Q are emergency cuts.
"""

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


# =============================================================================
# Things you should edit between flights
# =============================================================================

# Radio and mocap connection.
URI = "radio://0/80/2M"
MOCAP_HOST = "192.168.1.42:3883"
RIGID_BODY_NAME = "crazyflie_21"

# Keep this smaller than the full cage until mocap coverage is reliable.
# These limits are relative to the takeoff/start position.
MAX_XY_DRIFT_M = 0.28
MAX_TARGET_ERROR_M = 0.22
MAX_HEIGHT_ABOVE_START_M = 0.25
MAX_ESTIMATOR_HEIGHT_ABOVE_START_M = 0.45
MAX_CLIMB_RATE_M_S = 0.60
SAFETY_THRUST_RAW = 35000
MOCAP_STALE_TIMEOUT_S = 0.30
MOCAP_STALE_GRACE_S = 1.50
SHUTDOWN_ON_STALE_MOCAP = True
MOCAP_STALE_FORCE_DESCENT = True
MOCAP_RELOCK_AFTER_STALE_S = 0.45
STALE_LOG_PERIOD_S = 0.10
ESTIMATOR_STALE_TIMEOUT_S = 0.50

# Manual thrust controls. Crazyflie raw thrust is 0..65535.
# The ready key (R) requests a near-liftoff target, but the actual sent thrust
# rises at THRUST_RAMP_UP_RAW_PER_S. From there, use Up for small nudges.
MAX_MANUAL_THRUST = 52000
SMALL_THRUST_STEP = 100
BIG_THRUST_STEP = 500
TAKEOFF_READY_THRUST = 38000
TAKEOFF_HOLD_FREEZE_THRUST_RAW = 33000
THRUST_RAMP_UP_RAW_PER_S = 2500.0
THRUST_RAMP_DOWN_RAW_PER_S = 2500.0
DESCENT_RAMP_RAW_PER_S = 700.0
SAFETY_DESCENT_RAMP_RAW_PER_S = 5000.0

# Horizontal controller.
# If it corrects the wrong direction, change only one sign at a time.
ROLL_SIGN = -1.0
PITCH_SIGN = -1.0
BODY_YAW_OFFSET_DEG = 0.0

# PD + small leaky integral. Kp responds to position error, Kd damps velocity,
# Ki cancels small bias after it is already near hover.
KP_XY = 14.0
KD_XY = 7.0
KI_XY = 1.0
INTEGRAL_LEAK_PER_S = 0.20
INTEGRAL_MAX_ERROR_S = 0.20

# Angle limits. Near the floor, keep tilt small so it does not skate sideways.
GROUND_MAX_ANGLE_DEG = 1.0
LOW_ALTITUDE_MAX_ANGLE_DEG = 2.0
FULL_AUTHORITY_HEIGHT_M = 0.12
TAKEOFF_XY_ASSIST_START_HEIGHT_M = 0.02
TAKEOFF_XY_ASSIST_FULL_HEIGHT_M = 0.08
MAX_ANGLE_DEG = 12.0
AGGRESSIVE_ERROR_M = 0.08
AGGRESSIVE_GAIN_SCALE = 1.7

# Keyboard attitude trim. These are added on top of the mocap controller while
# mocap is fresh. During stale mocap, the script still commands neutral attitude.
ROLL_TRIM_STEP_DEG = 0.5
PITCH_TRIM_STEP_DEG = 0.5
MAX_ROLL_PITCH_TRIM_DEG = 6.0
YAW_TARGET_STEP_DEG = 5.0
MAX_YAW_TARGET_OFFSET_DEG = 45.0

# Yaw hold. The script captures yaw at flight start and holds it.
YAW_KP = 3.0
YAW_KD = 0.20
MAX_YAWRATE_DEG_S = 60.0
YAW_HOLD_MIN_THRUST = 24000
YAW_HOLD_MIN_HEIGHT_M = 0.03
GROUND_MAX_YAWRATE_DEG_S = 12.0

# Figure-8 target. Keep this tiny until hold is boringly stable.
FIGURE8_RADIUS_X_M = 0.04
FIGURE8_RADIUS_Y_M = 0.03
FIGURE8_PERIOD_S = 32.0
FIGURE8_MIN_HEIGHT_M = 0.12
FIGURE8_MAX_START_ERROR_M = 0.10

# Misc.
OUTPUT_DIR = "flight_logs"
COMMAND_PERIOD_S = 0.02
LOG_PERIOD_MS = 100
LOW_BATTERY_V = 3.70
VERY_LOW_BATTERY_V = 3.50
EMERGENCY_ZERO_THRUST_PACKETS = 20


MIN_THRUST = 0
MAX_THRUST = 65535
MOCAP_TIMEOUT_S = 8.0


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


class Telemetry:
    def __init__(self):
        self._lock = Lock()
        self.battery_v = 0.0
        self.estimate_z = 0.0
        self.estimate_updated_at = 0.0

    def battery_callback(self, timestamp, data, logconf):
        del timestamp, logconf
        with self._lock:
            self.battery_v = data["pm.vbat"]

    def altitude_callback(self, timestamp, data, logconf):
        del timestamp, logconf
        with self._lock:
            self.estimate_z = data["stateEstimate.z"]
            self.estimate_updated_at = time.time()

    def snapshot(self):
        with self._lock:
            if self.estimate_updated_at:
                estimate_age = time.time() - self.estimate_updated_at
            else:
                estimate_age = float("inf")
            return self.battery_v, self.estimate_z, estimate_age


class MocapReader(Thread):
    def __init__(self, state):
        Thread.__init__(self)
        self.daemon = True
        self.state = state
        self.error = None
        self._stay_open = True

    def close(self):
        self._stay_open = False

    def run(self):
        while self._stay_open:
            try:
                mc = motioncapture.connect("vrpn", {"hostname": MOCAP_HOST})
                self.error = None
                print(f"[INFO] Mocap connected, looking for '{RIGID_BODY_NAME}'")
                announced = False
                while self._stay_open:
                    mc.waitForNextFrame()
                    for name, obj in mc.rigidBodies.items():
                        if name != RIGID_BODY_NAME:
                            continue
                        if not announced:
                            print(f"[INFO] Found and tracking rigid body: {name}")
                            announced = True
                        pos = obj.position
                        self.state.update((pos[0], pos[1], pos[2]), obj.rotation)
                        self.error = None
            except Exception as exc:
                self.error = exc
                if self._stay_open:
                    print(f"[WARN] Mocap reader lost connection: {exc}; retrying...")
                    time.sleep(0.5)


class CsvLogger:
    FIELDNAMES = [
        "wall_time_s",
        "elapsed_s",
        "phase",
        "safety_descent_active",
        "safety_descent_reason",
        "hold_target_frozen",
        "mocap_status",
        "thrust_raw",
        "target_thrust_raw",
        "thrust_percent",
        "roll_cmd_deg",
        "pitch_cmd_deg",
        "yawrate_cmd_deg_s",
        "manual_roll_trim_deg",
        "manual_pitch_trim_deg",
        "manual_yaw_offset_deg",
        "target_x",
        "target_y",
        "target_error_x_m",
        "target_error_y_m",
        "target_error_m",
        "figure8_active",
        "mocap_x",
        "mocap_y",
        "mocap_z",
        "mocap_qx",
        "mocap_qy",
        "mocap_qz",
        "mocap_qw",
        "mocap_age_s",
        "mocap_frame_count",
        "yaw_deg",
        "target_yaw_deg",
        "yaw_error_deg",
        "yawrate_measured_deg_s",
        "height_above_start_m",
        "estimator_height_above_start_m",
        "estimator_age_s",
        "drift_x_m",
        "drift_y_m",
        "horizontal_drift_m",
        "velocity_x_m_s",
        "velocity_y_m_s",
        "velocity_z_m_s",
        "horizontal_speed_m_s",
        "body_error_x_m",
        "body_error_y_m",
        "body_velocity_x_m_s",
        "body_velocity_y_m_s",
        "integral_x_error_s",
        "integral_y_error_s",
        "xy_gain_scale",
        "xy_angle_limit_deg",
        "xy_assist_blend",
        "battery_v",
        "estimate_z",
        "stop_reason",
    ]

    def __init__(self):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.output_path = Path(OUTPUT_DIR) / f"mocap-assisted-figure8-{timestamp}.csv"
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output_path.open("w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        self._writer.writeheader()

    def write(self, row):
        self._writer.writerow(row)
        self._file.flush()

    def close(self):
        self._file.close()


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def wrap_pi(angle_rad):
    while angle_rad > math.pi:
        angle_rad -= 2.0 * math.pi
    while angle_rad < -math.pi:
        angle_rad += 2.0 * math.pi
    return angle_rad


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


def pose_age(mocap_state):
    _, _, last_update, _ = mocap_state.snapshot()
    if last_update == 0.0:
        return float("inf")
    return time.time() - last_update


def wait_for_fresh_pose(mocap_state):
    deadline = time.time() + MOCAP_TIMEOUT_S
    while time.time() < deadline:
        if pose_age(mocap_state) <= MOCAP_STALE_TIMEOUT_S:
            position, quat, _, frames = mocap_state.snapshot()
            print(
                "[MOCAP] Fresh pose: "
                f"pos=({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) "
                f"quat=({quat.x:.3f}, {quat.y:.3f}, {quat.z:.3f}, {quat.w:.3f}) "
                f"frames={frames}"
            )
            return position, quat
        time.sleep(0.05)
    raise RuntimeError("No fresh mocap pose received before timeout")


def send_zero_thrust(cf, count=10, send_stop=True):
    for _ in range(count):
        cf.commander.send_setpoint(0.0, 0.0, 0.0, 0)
        time.sleep(COMMAND_PERIOD_S)
    if send_stop:
        cf.commander.send_stop_setpoint()


def slew_toward(current, target, up_rate, down_rate, dt):
    if target > current:
        return min(target, current + up_rate * dt)
    if target < current:
        return max(target, current - down_rate * dt)
    return current


def low_altitude_angle_limit(height_above_start):
    if height_above_start <= 0.0:
        return GROUND_MAX_ANGLE_DEG
    if height_above_start >= FULL_AUTHORITY_HEIGHT_M:
        return MAX_ANGLE_DEG
    fraction = clamp(height_above_start / FULL_AUTHORITY_HEIGHT_M, 0.0, 1.0)
    return GROUND_MAX_ANGLE_DEG + fraction * (
        MAX_ANGLE_DEG - GROUND_MAX_ANGLE_DEG
    )


def figure8_target(center_x, center_y, elapsed_s):
    phase = 2.0 * math.pi * elapsed_s / FIGURE8_PERIOD_S
    return (
        center_x + FIGURE8_RADIUS_X_M * math.sin(phase),
        center_y + FIGURE8_RADIUS_Y_M * math.sin(phase) * math.cos(phase),
    )


def add_line(stdscr, y, x, text):
    max_y, max_x = stdscr.getmaxyx()
    if y >= max_y or x >= max_x:
        return
    available = max_x - x - 1
    if available > 0:
        stdscr.addstr(y, x, text[:available])


def draw(stdscr, state):
    stdscr.erase()
    add_line(stdscr, 0, 0, "Manual Thrust + Mocap Assisted Figure-8")
    add_line(stdscr, 2, 0, "Controls: R ramp to ready | Up/Down fine | PgUp bigger up | PgDn slow descent")
    add_line(stdscr, 3, 0, "Trim: W/S pitch +/- | A/D roll -/+ | J/L yaw target -/+ | C clear")
    add_line(stdscr, 4, 0, "F toggle figure-8 | H lock current X/Y | Space cut | Q/Esc cut+quit")
    add_line(stdscr, 5, 0, f"Phase: {state['phase']} | {state['message']}")
    add_line(
        stdscr,
        6,
        0,
        f"Thrust: {state['thrust']:5d} -> {state['target_thrust']:5d} "
        f"({100.0 * state['thrust'] / MAX_THRUST:4.1f}%)",
    )
    add_line(
        stdscr,
        7,
        0,
        f"Cmd roll/pitch/yawrate: {state['roll']:+5.2f} / "
        f"{state['pitch']:+5.2f} deg / {state['yawrate']:+5.1f} deg/s",
    )
    add_line(
        stdscr,
        8,
        0,
        f"Pos: x={state['x']:+.3f} y={state['y']:+.3f} z={state['z']:+.3f} "
        f"| height={state['height']:+.3f}",
    )
    add_line(
        stdscr,
        9,
        0,
        f"Target: x={state['target_x']:+.3f} y={state['target_y']:+.3f} "
        f"| error={state['target_error']:.3f} m",
    )
    add_line(
        stdscr,
        10,
        0,
        f"Drift from start: dx={state['drift_x']:+.3f} dy={state['drift_y']:+.3f} "
        f"total={state['drift']:.3f} m",
    )
    add_line(
        stdscr,
        11,
        0,
        f"Velocity: vx={state['vx']:+.3f} vy={state['vy']:+.3f} "
        f"vz={state['vz']:+.3f} | xy speed={state['speed']:.3f} m/s",
    )
    add_line(
        stdscr,
        12,
        0,
        f"Yaw: {state['yaw']:+.1f} deg | target={state['target_yaw']:+.1f} "
        f"| err={state['yaw_error']:+.1f}",
    )
    add_line(
        stdscr,
        13,
        0,
        f"Body error: x={state['body_error_x']:+.3f} y={state['body_error_y']:+.3f} "
        f"| angle cap={state['angle_limit']:.1f} deg | assist={state['assist_blend']:.2f}x",
    )
    add_line(
        stdscr,
        14,
        0,
        f"Manual trim: roll={state['roll_trim']:+.1f} pitch={state['pitch_trim']:+.1f} deg "
        f"| yaw target offset={state['yaw_offset']:+.1f} deg",
    )
    add_line(
        stdscr,
        15,
        0,
        f"Battery: {state['battery']:.2f} V | estimator dz={state['estimator_height']:+.2f} m "
        f"| est age={state['estimator_age']:.2f}s",
    )
    add_line(stdscr, 17, 0, "Normal landing: PgDn. Emergency: Space or Q.")
    stdscr.refresh()


def run_control_loop(stdscr, cf, mocap_state, mocap_reader, telemetry, start_position, start_quat, logger):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    start_x, start_y, start_z = start_position
    _, start_estimate_z, _ = telemetry.snapshot()
    hold_x = start_x
    hold_y = start_y
    target_x = hold_x
    target_y = hold_y
    target_yaw = yaw_from_quat(start_quat) + math.radians(BODY_YAW_OFFSET_DEG)
    hold_target_frozen = False

    thrust = 0.0
    target_thrust = 0.0
    descent_active = False
    safety_descent_active = False
    safety_descent_reason = ""
    figure8_active = False
    figure8_started_at = None
    message = "Neutral takeoff: raise thrust manually, X/Y assist fades in after lift."
    started_at = time.time()
    last_loop_at = started_at
    last_draw_at = 0.0
    last_logged_frame = None
    last_stale_log_at = 0.0
    previous_sample = None
    stale_started_at = None
    exit_after_log = False

    velocity_x = 0.0
    velocity_y = 0.0
    velocity_z = 0.0
    yawrate_measured = 0.0
    integral_x = 0.0
    integral_y = 0.0
    manual_roll_trim = 0.0
    manual_pitch_trim = 0.0
    manual_yaw_offset = 0.0
    stop_reason = ""

    def start_safety_descent(reason):
        nonlocal target_thrust
        nonlocal descent_active, safety_descent_active, safety_descent_reason
        nonlocal figure8_active, figure8_started_at, integral_x, integral_y
        if not safety_descent_active:
            safety_descent_reason = reason
        target_thrust = min(target_thrust, thrust)
        safety_descent_active = True
        descent_active = True
        figure8_active = False
        figure8_started_at = None
        integral_x = 0.0
        integral_y = 0.0

    while True:
        now = time.time()
        dt = max(0.0, now - last_loop_at)
        last_loop_at = now

        if mocap_state is None:
            raise RuntimeError("Internal error: mocap state missing")

        position, quat, last_update, frame_count = mocap_state.snapshot()
        if position is None or quat is None:
            raise RuntimeError("Internal error: mocap pose missing")

        mocap_age = now - last_update if last_update else float("inf")
        mocap_stale = mocap_age > MOCAP_STALE_TIMEOUT_S
        yaw = yaw_from_quat(quat) + math.radians(BODY_YAW_OFFSET_DEG)

        if mocap_stale:
            if stale_started_at is None:
                stale_started_at = now
                figure8_active = False
                figure8_started_at = None
                previous_sample = None
                velocity_x = 0.0
                velocity_y = 0.0
                velocity_z = 0.0
                yawrate_measured = 0.0
                integral_x = 0.0
                integral_y = 0.0
                message = "Mocap stale: leveling roll/pitch/yaw. Use PgDn or Space if needed."
            stale_for = now - stale_started_at
            # Normally this would shut down after MOCAP_STALE_GRACE_S. For
            # hardening, force a descent while thrust is high, then abort if
            # mocap does not recover inside the grace window.
            if (
                MOCAP_STALE_FORCE_DESCENT
                and thrust > SAFETY_THRUST_RAW
                and not descent_active
            ):
                start_safety_descent(
                    f"mocap stale while thrust > {SAFETY_THRUST_RAW}"
                )
                message = (
                    f"Mocap stale with thrust > {SAFETY_THRUST_RAW}; "
                    "forcing slow descent."
                )
            if SHUTDOWN_ON_STALE_MOCAP and stale_for > MOCAP_STALE_GRACE_S:
                start_safety_descent(
                    f"mocap stale for {stale_for:.2f}s"
                )
                message = f"Mocap stale for {stale_for:.1f}s; safety descent active."
            if not SHUTDOWN_ON_STALE_MOCAP and stale_for > MOCAP_STALE_GRACE_S:
                message = (
                    f"Mocap stale for {stale_for:.1f}s; stale shutdown disabled. "
                    "Manual thrust only."
                )
        elif stale_started_at is not None:
            stale_for = now - stale_started_at
            stale_started_at = None
            previous_sample = None
            velocity_x = 0.0
            velocity_y = 0.0
            velocity_z = 0.0
            yawrate_measured = 0.0
            integral_x = 0.0
            integral_y = 0.0
            if stale_for >= MOCAP_RELOCK_AFTER_STALE_S:
                hold_x, hold_y = position[0], position[1]
                target_x, target_y = hold_x, hold_y
                hold_target_frozen = True
                figure8_active = False
                figure8_started_at = None
                message = f"Mocap reacquired after {stale_for:.1f}s; re-locked current X/Y."
            else:
                message = "Mocap reacquired; continuing hold."

        if not mocap_stale:
            if previous_sample is None:
                previous_sample = (position, yaw, last_update, frame_count)
            elif frame_count != previous_sample[3]:
                previous_position, previous_yaw, previous_time, _ = previous_sample
                sample_dt = last_update - previous_time
                if sample_dt > 0.0:
                    measured_vx = (position[0] - previous_position[0]) / sample_dt
                    measured_vy = (position[1] - previous_position[1]) / sample_dt
                    measured_vz = (position[2] - previous_position[2]) / sample_dt
                    measured_yawrate = wrap_pi(yaw - previous_yaw) / sample_dt
                    velocity_x = 0.70 * velocity_x + 0.30 * measured_vx
                    velocity_y = 0.70 * velocity_y + 0.30 * measured_vy
                    velocity_z = 0.70 * velocity_z + 0.30 * measured_vz
                    yawrate_measured = 0.70 * yawrate_measured + 0.30 * measured_yawrate
                previous_sample = (position, yaw, last_update, frame_count)

        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            stop_reason = "operator_exit"
            send_zero_thrust(cf, count=EMERGENCY_ZERO_THRUST_PACKETS)
            break
        if key == ord(" "):
            stop_reason = "operator_cut"
            thrust = 0
            target_thrust = 0
            descent_active = False
            safety_descent_active = False
            send_zero_thrust(cf, count=EMERGENCY_ZERO_THRUST_PACKETS, send_stop=False)
            message = "Emergency zero thrust sent immediately."
        elif key == curses.KEY_UP:
            if safety_descent_active:
                message = "Safety descent active; thrust increase ignored."
            else:
                target_thrust = int(clamp(target_thrust + SMALL_THRUST_STEP, MIN_THRUST, MAX_MANUAL_THRUST))
                descent_active = False
                message = f"Target thrust +{SMALL_THRUST_STEP}; ramping up."
        elif key == curses.KEY_DOWN:
            target_thrust = int(clamp(target_thrust - SMALL_THRUST_STEP, MIN_THRUST, MAX_MANUAL_THRUST))
            descent_active = False
            message = f"Target thrust -{SMALL_THRUST_STEP}; ramping down."
        elif key == curses.KEY_PPAGE:
            if safety_descent_active:
                message = "Safety descent active; thrust increase ignored."
            else:
                target_thrust = int(clamp(target_thrust + BIG_THRUST_STEP, MIN_THRUST, MAX_MANUAL_THRUST))
                descent_active = False
                message = f"Target thrust +{BIG_THRUST_STEP}; ramping up."
        elif key in (ord("r"), ord("R")):
            if safety_descent_active:
                message = "Safety descent active; ready thrust ignored."
            else:
                target_thrust = int(clamp(TAKEOFF_READY_THRUST, MIN_THRUST, MAX_MANUAL_THRUST))
                descent_active = False
                message = f"Ready target {TAKEOFF_READY_THRUST}; thrust is ramping up."
        elif key == curses.KEY_NPAGE:
            descent_active = True
            message = "Slow descent ramp active."
        elif key in (ord("a"), ord("A")):
            manual_roll_trim = clamp(
                manual_roll_trim - ROLL_TRIM_STEP_DEG,
                -MAX_ROLL_PITCH_TRIM_DEG,
                MAX_ROLL_PITCH_TRIM_DEG,
            )
            message = f"Roll trim {manual_roll_trim:+.1f} deg."
        elif key in (ord("d"), ord("D")):
            manual_roll_trim = clamp(
                manual_roll_trim + ROLL_TRIM_STEP_DEG,
                -MAX_ROLL_PITCH_TRIM_DEG,
                MAX_ROLL_PITCH_TRIM_DEG,
            )
            message = f"Roll trim {manual_roll_trim:+.1f} deg."
        elif key in (ord("w"), ord("W")):
            manual_pitch_trim = clamp(
                manual_pitch_trim + PITCH_TRIM_STEP_DEG,
                -MAX_ROLL_PITCH_TRIM_DEG,
                MAX_ROLL_PITCH_TRIM_DEG,
            )
            message = f"Pitch trim {manual_pitch_trim:+.1f} deg."
        elif key in (ord("s"), ord("S")):
            manual_pitch_trim = clamp(
                manual_pitch_trim - PITCH_TRIM_STEP_DEG,
                -MAX_ROLL_PITCH_TRIM_DEG,
                MAX_ROLL_PITCH_TRIM_DEG,
            )
            message = f"Pitch trim {manual_pitch_trim:+.1f} deg."
        elif key in (ord("j"), ord("J")):
            manual_yaw_offset = math.radians(
                clamp(
                    math.degrees(manual_yaw_offset) - YAW_TARGET_STEP_DEG,
                    -MAX_YAW_TARGET_OFFSET_DEG,
                    MAX_YAW_TARGET_OFFSET_DEG,
                )
            )
            message = f"Yaw target offset {math.degrees(manual_yaw_offset):+.1f} deg."
        elif key in (ord("l"), ord("L")):
            manual_yaw_offset = math.radians(
                clamp(
                    math.degrees(manual_yaw_offset) + YAW_TARGET_STEP_DEG,
                    -MAX_YAW_TARGET_OFFSET_DEG,
                    MAX_YAW_TARGET_OFFSET_DEG,
                )
            )
            message = f"Yaw target offset {math.degrees(manual_yaw_offset):+.1f} deg."
        elif key in (ord("c"), ord("C")):
            manual_roll_trim = 0.0
            manual_pitch_trim = 0.0
            manual_yaw_offset = 0.0
            message = "Manual attitude trims cleared."
        elif key in (ord("h"), ord("H")):
            if mocap_stale:
                message = "Cannot lock X/Y while mocap is stale."
            else:
                hold_x, hold_y = position[0], position[1]
                hold_target_frozen = True
                figure8_active = False
                figure8_started_at = None
                integral_x = 0.0
                integral_y = 0.0
                message = "Locked current X/Y as new hold target."
        elif key in (ord("f"), ord("F")):
            if mocap_stale:
                message = "Cannot start figure-8 while mocap is stale."
            elif figure8_active:
                figure8_active = False
                figure8_started_at = None
                target_x, target_y = hold_x, hold_y
                message = "Figure-8 stopped; holding center."
            else:
                height_for_start = position[2] - start_z
                error_to_hold = math.hypot(position[0] - hold_x, position[1] - hold_y)
                if height_for_start < FIGURE8_MIN_HEIGHT_M:
                    message = f"Figure-8 rejected: height {height_for_start:.2f}m is too low."
                elif height_for_start < TAKEOFF_XY_ASSIST_FULL_HEIGHT_M:
                    message = (
                        f"Figure-8 rejected: wait for full X/Y assist "
                        f"above {TAKEOFF_XY_ASSIST_FULL_HEIGHT_M:.2f}m."
                    )
                elif error_to_hold > FIGURE8_MAX_START_ERROR_M:
                    message = f"Figure-8 rejected: hold error {error_to_hold:.2f}m is too high."
                else:
                    figure8_active = True
                    figure8_started_at = now
                    integral_x = 0.0
                    integral_y = 0.0
                    message = "Figure-8 active. Keep altitude with thrust."

        # Re-apply this after keyboard handling so an Up/PgUp tap cannot
        # accidentally override the stale-mocap descent guard for one loop.
        if (
            mocap_stale
            and MOCAP_STALE_FORCE_DESCENT
            and max(thrust, target_thrust) > SAFETY_THRUST_RAW
        ):
            if not descent_active:
                message = (
                    f"Mocap stale with thrust > {SAFETY_THRUST_RAW}; "
                    "forcing slow descent."
                )
            start_safety_descent(
                f"mocap stale while thrust > {SAFETY_THRUST_RAW}"
            )

        if safety_descent_active:
            descent_active = True
            message = f"Safety descent: {safety_descent_reason}."

        if descent_active:
            descent_rate = (
                SAFETY_DESCENT_RAMP_RAW_PER_S
                if safety_descent_active
                else DESCENT_RAMP_RAW_PER_S
            )
            target_thrust = min(target_thrust, thrust)
            target_thrust = clamp(
                target_thrust - descent_rate * dt,
                MIN_THRUST,
                MAX_MANUAL_THRUST,
            )
            if target_thrust <= MIN_THRUST:
                descent_active = False
                if safety_descent_active:
                    stop_reason = safety_descent_reason or "safety_descent_complete"
                    target_thrust = 0
                    thrust = 0
                    exit_after_log = True
                    message = "Safety descent reached zero thrust."
                else:
                    message = "Slow descent reached zero thrust."

        target_thrust = clamp(target_thrust, MIN_THRUST, MAX_MANUAL_THRUST)
        thrust_down_rate = (
            SAFETY_DESCENT_RAMP_RAW_PER_S
            if safety_descent_active
            else THRUST_RAMP_DOWN_RAW_PER_S
        )
        thrust = slew_toward(
            thrust,
            target_thrust,
            THRUST_RAMP_UP_RAW_PER_S,
            thrust_down_rate,
            dt,
        )
        thrust = int(clamp(thrust, MIN_THRUST, MAX_MANUAL_THRUST))

        height = position[2] - start_z
        battery_v, estimate_z, estimator_age = telemetry.snapshot()
        estimator_height = estimate_z - start_estimate_z
        if thrust > SAFETY_THRUST_RAW and estimator_age > ESTIMATOR_STALE_TIMEOUT_S:
            start_safety_descent(
                f"Estimator height telemetry stale for {estimator_age:.2f}s "
                f"while thrust is {thrust}"
            )
        if mocap_stale:
            assist_blend = 0.0
        else:
            blend_span = max(
                0.01,
                TAKEOFF_XY_ASSIST_FULL_HEIGHT_M - TAKEOFF_XY_ASSIST_START_HEIGHT_M,
            )
            assist_blend = clamp(
                (height - TAKEOFF_XY_ASSIST_START_HEIGHT_M) / blend_span,
                0.0,
                1.0,
            )

        # Match the successful cfclient takeoff: do not chase X/Y while the
        # drone is still in ground effect. Before liftoff, follow the current
        # mocap position; near liftoff, freeze that point so early drift is not
        # silently accepted as the new center.
        if (
            not hold_target_frozen
            and not mocap_stale
            and target_thrust >= TAKEOFF_HOLD_FREEZE_THRUST_RAW
        ):
            hold_x, hold_y = position[0], position[1]
            target_x, target_y = hold_x, hold_y
            hold_target_frozen = True
            integral_x = 0.0
            integral_y = 0.0

        if (
            not hold_target_frozen
            and not mocap_stale
            and not figure8_active
            and assist_blend <= 0.0
        ):
            hold_x, hold_y = position[0], position[1]
            target_x, target_y = hold_x, hold_y
            integral_x = 0.0
            integral_y = 0.0

        drift_x = position[0] - start_x
        drift_y = position[1] - start_y
        drift = math.hypot(drift_x, drift_y)
        speed = math.hypot(velocity_x, velocity_y)

        if estimator_height > MAX_ESTIMATOR_HEIGHT_ABOVE_START_M:
            start_safety_descent(
                f"Estimator height {estimator_height:.3f}m exceeded "
                f"{MAX_ESTIMATOR_HEIGHT_ABOVE_START_M:.3f}m"
            )
        if (
            not mocap_stale
            and thrust > SAFETY_THRUST_RAW
            and height > 0.03
            and velocity_z > MAX_CLIMB_RATE_M_S
        ):
            start_safety_descent(
                f"Mocap climb rate {velocity_z:.3f}m/s exceeded "
                f"{MAX_CLIMB_RATE_M_S:.3f}m/s"
            )

        if not mocap_stale:
            if height > MAX_HEIGHT_ABOVE_START_M:
                start_safety_descent(
                    f"Mocap height {height:.3f}m exceeded {MAX_HEIGHT_ABOVE_START_M:.3f}m"
                )
            if drift > MAX_XY_DRIFT_M:
                start_safety_descent(
                    f"XY drift {drift:.3f}m exceeded {MAX_XY_DRIFT_M:.3f}m"
                )

        if safety_descent_active:
            target_x, target_y = hold_x, hold_y
            phase = "safety-descent"
        elif mocap_stale:
            target_x, target_y = hold_x, hold_y
            phase = "mocap-stale"
        elif figure8_active and figure8_started_at is not None:
            target_x, target_y = figure8_target(hold_x, hold_y, now - figure8_started_at)
            phase = "figure8"
        else:
            target_x, target_y = hold_x, hold_y
            if assist_blend <= 0.0:
                phase = "takeoff-neutral"
            elif assist_blend < 1.0:
                phase = "xy-assist-blend"
            else:
                phase = "xy-hold"
            if descent_active:
                phase = "descent"

        error_x = target_x - position[0]
        error_y = target_y - position[1]
        target_error = math.hypot(error_x, error_y)
        if not mocap_stale and assist_blend >= 1.0 and target_error > MAX_TARGET_ERROR_M:
            start_safety_descent(
                f"Target error {target_error:.3f}m exceeded {MAX_TARGET_ERROR_M:.3f}m"
            )

        target_yaw_command = wrap_pi(target_yaw + manual_yaw_offset)
        yaw_error = wrap_pi(target_yaw_command - yaw)
        if safety_descent_active or mocap_stale or assist_blend <= 0.0:
            body_error_x = 0.0
            body_error_y = 0.0
            body_velocity_x = 0.0
            body_velocity_y = 0.0
            integral_x = 0.0
            integral_y = 0.0
            gain_scale = 0.0
            angle_limit = 0.0
            roll_cmd = 0.0
            pitch_cmd = 0.0
            yawrate_cmd = 0.0
        else:
            body_error_x, body_error_y = rotate_world_to_body(error_x, error_y, yaw)
            body_velocity_x, body_velocity_y = rotate_world_to_body(velocity_x, velocity_y, yaw)

            airborne = thrust > 22000 or height > 0.03
            if airborne and dt > 0.0:
                leak = max(0.0, 1.0 - INTEGRAL_LEAK_PER_S * dt)
                integral_x = clamp(
                    integral_x * leak + body_error_x * dt,
                    -INTEGRAL_MAX_ERROR_S,
                    INTEGRAL_MAX_ERROR_S,
                )
                integral_y = clamp(
                    integral_y * leak + body_error_y * dt,
                    -INTEGRAL_MAX_ERROR_S,
                    INTEGRAL_MAX_ERROR_S,
                )
            else:
                integral_x = 0.0
                integral_y = 0.0

            gain_scale = AGGRESSIVE_GAIN_SCALE if target_error >= AGGRESSIVE_ERROR_M else 1.0
            control_x = assist_blend * (
                gain_scale * (KP_XY * body_error_x - KD_XY * body_velocity_x)
                + KI_XY * integral_x
            )
            control_y = assist_blend * (
                gain_scale * (KP_XY * body_error_y - KD_XY * body_velocity_y)
                + KI_XY * integral_y
            )
            angle_limit = assist_blend * low_altitude_angle_limit(height)

            pitch_cmd = clamp(
                PITCH_SIGN * control_x + assist_blend * manual_pitch_trim,
                -angle_limit,
                angle_limit,
            )
            roll_cmd = clamp(
                ROLL_SIGN * control_y + assist_blend * manual_roll_trim,
                -angle_limit,
                angle_limit,
            )

            yaw_active = thrust >= YAW_HOLD_MIN_THRUST or height >= YAW_HOLD_MIN_HEIGHT_M
            if yaw_active:
                yawrate_cmd = YAW_KP * math.degrees(yaw_error) - YAW_KD * math.degrees(yawrate_measured)
                yawrate_limit = MAX_YAWRATE_DEG_S if height >= YAW_HOLD_MIN_HEIGHT_M else GROUND_MAX_YAWRATE_DEG_S
                yawrate_limit *= assist_blend
                yawrate_cmd = clamp(yawrate_cmd * assist_blend, -yawrate_limit, yawrate_limit)
            else:
                yawrate_cmd = 0.0

        cf.commander.send_setpoint(roll_cmd, pitch_cmd, yawrate_cmd, thrust)

        if battery_v and battery_v < VERY_LOW_BATTERY_V:
            start_safety_descent("battery is very low")

        should_log = frame_count != last_logged_frame
        if mocap_stale and now - last_stale_log_at >= STALE_LOG_PERIOD_S:
            should_log = True
            last_stale_log_at = now
        if exit_after_log:
            should_log = True

        if should_log:
            logger.write({
                "wall_time_s": now,
                "elapsed_s": now - started_at,
                "phase": phase,
                "safety_descent_active": int(safety_descent_active),
                "safety_descent_reason": safety_descent_reason,
                "hold_target_frozen": int(hold_target_frozen),
                "mocap_status": "stale" if mocap_stale else "fresh",
                "thrust_raw": thrust,
                "target_thrust_raw": int(target_thrust),
                "thrust_percent": 100.0 * thrust / MAX_THRUST,
                "roll_cmd_deg": roll_cmd,
                "pitch_cmd_deg": pitch_cmd,
                "yawrate_cmd_deg_s": yawrate_cmd,
                "manual_roll_trim_deg": manual_roll_trim,
                "manual_pitch_trim_deg": manual_pitch_trim,
                "manual_yaw_offset_deg": math.degrees(manual_yaw_offset),
                "target_x": target_x,
                "target_y": target_y,
                "target_error_x_m": error_x,
                "target_error_y_m": error_y,
                "target_error_m": target_error,
                "figure8_active": int(figure8_active),
                "mocap_x": position[0],
                "mocap_y": position[1],
                "mocap_z": position[2],
                "mocap_qx": quat.x,
                "mocap_qy": quat.y,
                "mocap_qz": quat.z,
                "mocap_qw": quat.w,
                "mocap_age_s": mocap_age,
                "mocap_frame_count": frame_count,
                "yaw_deg": math.degrees(yaw),
                "target_yaw_deg": math.degrees(target_yaw_command),
                "yaw_error_deg": math.degrees(yaw_error),
                "yawrate_measured_deg_s": math.degrees(yawrate_measured),
                "height_above_start_m": height,
                "estimator_height_above_start_m": estimator_height,
                "estimator_age_s": estimator_age,
                "drift_x_m": drift_x,
                "drift_y_m": drift_y,
                "horizontal_drift_m": drift,
                "velocity_x_m_s": velocity_x,
                "velocity_y_m_s": velocity_y,
                "velocity_z_m_s": velocity_z,
                "horizontal_speed_m_s": speed,
                "body_error_x_m": body_error_x,
                "body_error_y_m": body_error_y,
                "body_velocity_x_m_s": body_velocity_x,
                "body_velocity_y_m_s": body_velocity_y,
                "integral_x_error_s": integral_x,
                "integral_y_error_s": integral_y,
                "xy_gain_scale": gain_scale,
                "xy_angle_limit_deg": angle_limit,
                "xy_assist_blend": assist_blend,
                "battery_v": battery_v,
                "estimate_z": estimate_z,
                "stop_reason": stop_reason,
            })
            last_logged_frame = frame_count

        if now - last_draw_at >= 0.10:
            draw(stdscr, {
                "phase": phase,
                "message": message,
                "thrust": thrust,
                "target_thrust": int(target_thrust),
                "roll": roll_cmd,
                "pitch": pitch_cmd,
                "yawrate": yawrate_cmd,
                "x": position[0],
                "y": position[1],
                "z": position[2],
                "height": height,
                "estimator_height": estimator_height,
                "estimator_age": estimator_age,
                "target_x": target_x,
                "target_y": target_y,
                "target_error": target_error,
                "drift_x": drift_x,
                "drift_y": drift_y,
                "drift": drift,
                "vx": velocity_x,
                "vy": velocity_y,
                "vz": velocity_z,
                "speed": speed,
                "yaw": math.degrees(yaw),
                "target_yaw": math.degrees(target_yaw_command),
                "yaw_error": math.degrees(yaw_error),
                "body_error_x": body_error_x,
                "body_error_y": body_error_y,
                "angle_limit": angle_limit,
                "gain_scale": gain_scale,
                "assist_blend": assist_blend,
                "roll_trim": manual_roll_trim,
                "pitch_trim": manual_pitch_trim,
                "yaw_offset": math.degrees(manual_yaw_offset),
                "battery": battery_v,
                "estimate_z": estimate_z,
            })
            last_draw_at = now

        if exit_after_log:
            send_zero_thrust(cf, count=EMERGENCY_ZERO_THRUST_PACKETS)
            break

        time.sleep(COMMAND_PERIOD_S)

    return thrust

def main():
    logging.basicConfig(level=logging.ERROR)
    cflib.crtp.init_drivers()

    print("=" * 72)
    print("MANUAL THRUST + MOCAP ASSISTED FIGURE-8")
    print("=" * 72)
    print(f"URI: {URI}")
    print(f"Mocap: {RIGID_BODY_NAME}@{MOCAP_HOST}")
    print(f"Max manual thrust: {MAX_MANUAL_THRUST}")
    print(
        f"Thrust ramp: up {THRUST_RAMP_UP_RAW_PER_S:.0f} raw/s, "
        f"down {THRUST_RAMP_DOWN_RAW_PER_S:.0f} raw/s, "
        f"PgDn {DESCENT_RAMP_RAW_PER_S:.0f} raw/s"
    )
    print(
        f"Safety box: drift <= {MAX_XY_DRIFT_M:.2f}m, "
        f"mocap height <= {MAX_HEIGHT_ABOVE_START_M:.2f}m, "
        f"estimator height <= {MAX_ESTIMATOR_HEIGHT_ABOVE_START_M:.2f}m"
    )
    print(
        f"Hard stops: climb <= {MAX_CLIMB_RATE_M_S:.2f}m/s, "
        f"estimator age <= {ESTIMATOR_STALE_TIMEOUT_S:.2f}s above thrust {SAFETY_THRUST_RAW}, "
        f"stale mocap shutdown={SHUTDOWN_ON_STALE_MOCAP}"
    )
    print(f"XY gains: kp={KP_XY}, kd={KD_XY}, ki={KI_XY}, signs roll={ROLL_SIGN}, pitch={PITCH_SIGN}")
    print(
        f"Keyboard trim: roll/pitch step={ROLL_TRIM_STEP_DEG:.1f}/{PITCH_TRIM_STEP_DEG:.1f} deg, "
        f"max=+/-{MAX_ROLL_PITCH_TRIM_DEG:.1f} deg, yaw step={YAW_TARGET_STEP_DEG:.1f} deg"
    )
    print(f"Figure-8: {FIGURE8_RADIUS_X_M:.2f}m x {FIGURE8_RADIUS_Y_M:.2f}m, period {FIGURE8_PERIOD_S:.1f}s")
    print("Close cfclient first. Keep a physical power-off option ready.")
    print("=" * 72)
    input("Press ENTER to connect mocap and Crazyflie, or Ctrl+C to abort...")

    mocap_state = MocapState()
    mocap_reader = MocapReader(mocap_state)
    telemetry = Telemetry()
    logger = CsvLogger()
    cf = None

    try:
        mocap_reader.start()
        start_position, start_quat = wait_for_fresh_pose(mocap_state)

        battery_log = LogConfig(name="Battery", period_in_ms=LOG_PERIOD_MS)
        battery_log.add_variable("pm.vbat", "float")
        altitude_log = LogConfig(name="Altitude", period_in_ms=LOG_PERIOD_MS)
        altitude_log.add_variable("stateEstimate.z", "float")

        with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="./cache")) as scf:
            cf = scf.cf
            print("[INFO] Crazyflie connected.")
            cf.log.add_config(battery_log)
            battery_log.data_received_cb.add_callback(telemetry.battery_callback)
            battery_log.start()
            cf.log.add_config(altitude_log)
            altitude_log.data_received_cb.add_callback(telemetry.altitude_callback)
            altitude_log.start()
            time.sleep(0.8)

            battery_v, _, _ = telemetry.snapshot()
            print(f"[INFO] Battery: {battery_v:.2f} V")
            if battery_v < VERY_LOW_BATTERY_V:
                raise RuntimeError("Battery is very low. Do not fly.")
            if battery_v < LOW_BATTERY_V:
                print("[WARN] Battery is low; use a fresh pack if possible.")

            input("Press ENTER to arm and start at zero thrust, or Ctrl+C to abort...")
            cf.platform.send_arming_request(True)
            time.sleep(1.0)
            send_zero_thrust(cf, count=25, send_stop=False)

            start_position, start_quat = wait_for_fresh_pose(mocap_state)
            print(
                "[INFO] Locked flight-start target: "
                f"x={start_position[0]:.3f}, y={start_position[1]:.3f}, z={start_position[2]:.3f}"
            )

            curses.wrapper(
                run_control_loop,
                cf,
                mocap_state,
                mocap_reader,
                telemetry,
                start_position,
                start_quat,
                logger,
            )

            print("\n[INFO] Flight loop ended.")
            send_zero_thrust(cf, count=25)
            cf.platform.send_arming_request(False)
            altitude_log.stop()
            battery_log.stop()
    finally:
        print("\n[SAFETY] Cutting thrust and closing resources...")
        try:
            if cf is not None:
                send_zero_thrust(cf, count=25)
                cf.platform.send_arming_request(False)
        finally:
            mocap_reader.close()
            logger.close()
        print(f"[DONE] Wrote log: {logger.output_path}")


if __name__ == "__main__":
    main()
