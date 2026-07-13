#!/usr/bin/env python3
"""
Manual-thrust Crazyflie attitude response test with mocap logging.

This script deliberately does not run X/Y position hold. The pilot controls
vertical thrust, and the script sends short roll/pitch pulses on keypresses so
we can learn how attitude commands map to measured OptiTrack/VRPN motion.

Controls:

- R: ramp to near takeoff thrust
- Up/Down: small thrust changes
- PgUp/PgDn: larger thrust up / slow descent
- A/D: short roll -/+ pulse
- S/W: short pitch -/+ pulse
- C: cancel current pulse
- Space/Q/Esc: emergency cut
"""

import csv
import curses
import logging
import math
import os
import sys
import time
from dataclasses import dataclass
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

URI = "radio://0/80/2M"
MOCAP_HOST = "192.168.1.42:3883"
RIGID_BODY_NAME = "crazyflie_21"

# VRPN position is rotated relative to the local flight frame:
# local +X <- raw -Y, local +Y <- raw +X, local +Z <- raw +Z.
LOCAL_FRAME_DESCRIPTION = "local +X <- raw -Y, local +Y <- raw +X, local +Z <- raw +Z"
BODY_YAW_OFFSET_DEG = 0.0
YAW_COMMAND_SIGN = -1.0

# Safety limits are intentionally close to the current assisted-test box.
MAX_XY_DRIFT_M = 4.00
MAX_HEIGHT_ABOVE_START_M = 0.25
MAX_ESTIMATOR_HEIGHT_ABOVE_START_M = 0.45
MAX_CLIMB_RATE_M_S = 0.60
SAFETY_THRUST_RAW = 35000
MOCAP_STALE_TIMEOUT_S = 0.30
MOCAP_STALE_GRACE_S = 1.50
MOCAP_STALE_FORCE_DESCENT = True
MOCAP_STALE_SHUTDOWN_MIN_THRUST_RAW = 24000
STALE_LOG_PERIOD_S = 0.10
ESTIMATOR_STALE_TIMEOUT_S = 0.50

# Manual thrust controls. Crazyflie raw thrust is 0..65535.
MAX_MANUAL_THRUST = 52000
SMALL_THRUST_STEP = 100
BIG_THRUST_STEP = 500
TAKEOFF_READY_THRUST = 43000
THRUST_RAMP_UP_RAW_PER_S = 8000.0
THRUST_RAMP_DOWN_RAW_PER_S = 3500.0
DESCENT_RAMP_RAW_PER_S = 700.0
SAFETY_DESCENT_RAMP_RAW_PER_S = 5000.0

# Pulse controls. These are direct keypress probes; the log is what matters.
PULSE_ANGLE_DEG = 4.0
PULSE_DURATION_S = 0.50
PULSE_COOLDOWN_S = 0.0
PULSE_MIN_THRUST_RAW = 0
AUTO_SETTLE_DURATION_S = 0.80
AUTO_PULSE_SEQUENCE = [
    ("roll_pos", "roll", 1, PULSE_ANGLE_DEG, 0.0, PULSE_DURATION_S),
    ("settle_after_roll_pos", "", 0, 0.0, 0.0, AUTO_SETTLE_DURATION_S),
    ("roll_neg", "roll", -1, -PULSE_ANGLE_DEG, 0.0, PULSE_DURATION_S),
    ("settle_after_roll_neg", "", 0, 0.0, 0.0, AUTO_SETTLE_DURATION_S),
    ("pitch_pos", "pitch", 1, 0.0, PULSE_ANGLE_DEG, PULSE_DURATION_S),
    ("settle_after_pitch_pos", "", 0, 0.0, 0.0, AUTO_SETTLE_DURATION_S),
    ("pitch_neg", "pitch", -1, 0.0, -PULSE_ANGLE_DEG, PULSE_DURATION_S),
    ("settle_after_pitch_neg", "", 0, 0.0, 0.0, AUTO_SETTLE_DURATION_S),
]

# Yaw hold. This is only to keep heading from wandering during the response test.
YAW_KP = 3.0
YAW_KD = 0.20
MAX_YAWRATE_DEG_S = 60.0
YAW_HOLD_MIN_THRUST = 24000
YAW_HOLD_MIN_HEIGHT_M = 0.03
GROUND_MAX_YAWRATE_DEG_S = 12.0

# Misc.
OUTPUT_DIR = "flight_logs"
COMMAND_PERIOD_S = 0.02
LOG_PERIOD_MS = 100
LOW_BATTERY_V = 3.70
VERY_LOW_BATTERY_V = 3.45
CRITICAL_BATTERY_V = 3.30
LOW_BATTERY_SUSTAINED_S = 5.00
ENFORCE_BATTERY_LIMITS = False
EMERGENCY_ZERO_THRUST_PACKETS = 20

MIN_THRUST = 0
MAX_THRUST = 65535
MOCAP_TIMEOUT_S = 8.0


@dataclass(frozen=True)
class Quat:
    x: float
    y: float
    z: float
    w: float


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
        if self.is_alive():
            self.join(timeout=1.0)

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
                        quat = normalized_quat(obj.rotation)
                        if quat is None:
                            continue
                        pos = raw_position_to_local(obj.position)
                        self.state.update(pos, quat)
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
        "mocap_status",
        "key_code",
        "key_name",
        "auto_sequence_active",
        "auto_step_index",
        "auto_step_label",
        "pulse_id",
        "pulse_label",
        "pulse_axis",
        "pulse_sign",
        "pulse_age_s",
        "thrust_raw",
        "target_thrust_raw",
        "thrust_percent",
        "roll_cmd_deg",
        "pitch_cmd_deg",
        "yawrate_cmd_deg_s",
        "yaw_command_sign",
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
        "body_velocity_x_m_s",
        "body_velocity_y_m_s",
        "battery_v",
        "estimate_z",
        "stop_reason",
    ]

    def __init__(self):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.output_path = Path(OUTPUT_DIR) / f"mocap-attitude-response-{timestamp}.csv"
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


def raw_position_to_local(raw_position):
    raw_x, raw_y, raw_z = (float(value) for value in raw_position)
    return (-raw_y, raw_x, raw_z)


def normalized_quat(rotation):
    values = (
        float(rotation.x),
        float(rotation.y),
        float(rotation.z),
        float(rotation.w),
    )
    if not all(math.isfinite(value) for value in values):
        return None

    norm = math.sqrt(sum(value * value for value in values))
    if not 0.5 <= norm <= 1.5:
        return None

    return Quat(*(value / norm for value in values))


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


def send_arming_request(cf, do_arm):
    supervisor = getattr(cf, "supervisor", None)
    if supervisor is not None and hasattr(supervisor, "send_arming_request"):
        supervisor.send_arming_request(do_arm)
    else:
        cf.platform.send_arming_request(do_arm)


def slew_toward(current, target, up_rate, down_rate, dt):
    if target > current:
        return min(target, current + up_rate * dt)
    if target < current:
        return max(target, current - down_rate * dt)
    return current


def add_line(stdscr, y, x, text):
    max_y, max_x = stdscr.getmaxyx()
    if y >= max_y or x >= max_x:
        return
    available = max_x - x - 1
    if available > 0:
        stdscr.addstr(y, x, text[:available])


def describe_key(key):
    if key == -1:
        return ""
    try:
        return curses.keyname(key).decode("ascii", errors="replace")
    except Exception:
        if 0 <= key <= 255:
            return chr(key)
        return str(key)


def draw(stdscr, state):
    stdscr.erase()
    add_line(stdscr, 0, 0, "Manual Thrust + Mocap Attitude Response Test")
    add_line(stdscr, 2, 0, "Controls: R ready | Up/Down fine | PgUp up | PgDn descent")
    add_line(stdscr, 3, 0, "Pulses: P auto sequence | A/D roll -/+ | S/W pitch -/+ | C cancel")
    add_line(stdscr, 4, 0, f"Phase: {state['phase']} | {state['message']}")
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
        f"Pulse: {state['pulse_label']} | roll={state['roll']:+.2f} "
        f"pitch={state['pitch']:+.2f} yawrate={state['yawrate']:+.1f}",
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
        f"Drift: dx={state['drift_x']:+.3f} dy={state['drift_y']:+.3f} "
        f"total={state['drift']:.3f} m",
    )
    add_line(
        stdscr,
        10,
        0,
        f"Velocity local: vx={state['vx']:+.3f} vy={state['vy']:+.3f} "
        f"vz={state['vz']:+.3f} | xy={state['speed']:.3f} m/s",
    )
    add_line(
        stdscr,
        11,
        0,
        f"Velocity body: x={state['body_vx']:+.3f} y={state['body_vy']:+.3f}",
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
        f"Battery: {state['battery']:.2f} V | estimator dz={state['estimator_height']:+.2f} m "
        f"| est age={state['estimator_age']:.2f}s",
    )
    add_line(stdscr, 15, 0, "Press P once in low hover for a balanced roll/pitch probe sequence.")
    stdscr.refresh()


def run_control_loop(stdscr, cf, mocap_state, telemetry, start_position, start_quat, logger):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    start_x, start_y, start_z = start_position
    _, start_estimate_z, _ = telemetry.snapshot()
    target_yaw = yaw_from_quat(start_quat) + math.radians(BODY_YAW_OFFSET_DEG)

    thrust = 0.0
    target_thrust = 0.0
    descent_active = False
    safety_descent_active = False
    safety_descent_reason = ""
    started_at = time.time()
    last_loop_at = started_at
    last_draw_at = 0.0
    last_logged_frame = None
    last_stale_log_at = 0.0
    previous_sample = None
    stale_started_at = None
    low_battery_started_at = None
    exit_after_log = False

    velocity_x = 0.0
    velocity_y = 0.0
    velocity_z = 0.0
    yawrate_measured = 0.0
    active_pulse = None
    last_pulse_ended_at = 0.0
    pulse_counter = 0
    auto_sequence_active = False
    auto_step_index = -1
    auto_step_label = ""
    auto_step_ends_at = 0.0
    stop_reason = ""
    message = "Raise thrust to low hover, then press P for auto probes."

    def start_safety_descent(reason):
        nonlocal target_thrust
        nonlocal descent_active, safety_descent_active, safety_descent_reason
        nonlocal active_pulse
        nonlocal auto_sequence_active, auto_step_label
        if not safety_descent_active:
            safety_descent_reason = reason
        target_thrust = min(target_thrust, thrust)
        safety_descent_active = True
        descent_active = True
        active_pulse = None
        auto_sequence_active = False
        auto_step_label = ""

    def start_pulse(label, axis, sign, roll_cmd, pitch_cmd, now):
        nonlocal active_pulse, pulse_counter, message
        nonlocal last_pulse_ended_at
        nonlocal auto_sequence_active, auto_step_label
        if safety_descent_active:
            message = "Safety descent active; pulse ignored."
            return
        if thrust < PULSE_MIN_THRUST_RAW:
            message = f"Pulse rejected: thrust below {PULSE_MIN_THRUST_RAW}."
            return
        if now - last_pulse_ended_at < PULSE_COOLDOWN_S:
            message = "Pulse cooldown; let the motion settle."
            return
        pulse_counter += 1
        active_pulse = {
            "id": pulse_counter,
            "label": label,
            "axis": axis,
            "sign": sign,
            "roll": roll_cmd,
            "pitch": pitch_cmd,
            "started_at": now,
            "ends_at": now + PULSE_DURATION_S,
        }
        auto_sequence_active = False
        auto_step_label = ""
        message = f"Pulse {label} active for {PULSE_DURATION_S:.2f}s."

    def load_auto_step(now):
        nonlocal active_pulse, pulse_counter, message
        nonlocal auto_sequence_active, auto_step_index, auto_step_label, auto_step_ends_at
        if auto_step_index >= len(AUTO_PULSE_SEQUENCE):
            auto_sequence_active = False
            auto_step_index = -1
            auto_step_label = ""
            auto_step_ends_at = 0.0
            active_pulse = None
            message = "Auto probe sequence complete."
            return

        label, axis, sign, roll_cmd, pitch_cmd, duration_s = AUTO_PULSE_SEQUENCE[auto_step_index]
        auto_step_label = label
        auto_step_ends_at = now + duration_s
        if axis:
            pulse_counter += 1
            active_pulse = {
                "id": pulse_counter,
                "label": label,
                "axis": axis,
                "sign": sign,
                "roll": roll_cmd,
                "pitch": pitch_cmd,
                "started_at": now,
                "ends_at": auto_step_ends_at,
            }
        else:
            active_pulse = None

        message = (
            f"Auto step {auto_step_index + 1}/{len(AUTO_PULSE_SEQUENCE)}: "
            f"{label}."
        )

    while True:
        now = time.time()
        dt = max(0.0, now - last_loop_at)
        last_loop_at = now

        position, quat, last_update, frame_count = mocap_state.snapshot()
        if position is None or quat is None:
            raise RuntimeError("Internal error: mocap pose missing")

        mocap_age = now - last_update if last_update else float("inf")
        mocap_stale = mocap_age > MOCAP_STALE_TIMEOUT_S
        yaw = yaw_from_quat(quat) + math.radians(BODY_YAW_OFFSET_DEG)

        if mocap_stale:
            if stale_started_at is None:
                stale_started_at = now
                previous_sample = None
                velocity_x = 0.0
                velocity_y = 0.0
                velocity_z = 0.0
                yawrate_measured = 0.0
                active_pulse = None
                auto_sequence_active = False
                auto_step_label = ""
                message = "Mocap stale: neutral attitude."
            stale_for = now - stale_started_at
            if (
                MOCAP_STALE_FORCE_DESCENT
                and thrust > SAFETY_THRUST_RAW
                and not descent_active
            ):
                start_safety_descent(
                    f"mocap stale while thrust > {SAFETY_THRUST_RAW}"
                )
            if stale_for > MOCAP_STALE_GRACE_S:
                if max(thrust, target_thrust) > MOCAP_STALE_SHUTDOWN_MIN_THRUST_RAW:
                    start_safety_descent(f"mocap stale for {stale_for:.2f}s")
                else:
                    message = (
                        f"Mocap stale for {stale_for:.1f}s; waiting while thrust is low."
                    )
        elif stale_started_at is not None:
            stale_started_at = None
            previous_sample = None
            velocity_x = 0.0
            velocity_y = 0.0
            velocity_z = 0.0
            yawrate_measured = 0.0
            message = "Mocap reacquired; continuing."

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
        key_code = "" if key == -1 else key
        key_name = describe_key(key)
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
            active_pulse = None
            auto_sequence_active = False
            auto_step_label = ""
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
        elif key == curses.KEY_NPAGE:
            descent_active = True
            active_pulse = None
            auto_sequence_active = False
            auto_step_label = ""
            message = "Slow descent ramp active."
        elif key in (ord("r"), ord("R")):
            if safety_descent_active:
                message = "Safety descent active; ready thrust ignored."
            else:
                target_thrust = int(clamp(TAKEOFF_READY_THRUST, MIN_THRUST, MAX_MANUAL_THRUST))
                descent_active = False
                message = f"Ready target {TAKEOFF_READY_THRUST}; thrust is ramping up."
        elif key in (ord("c"), ord("C")):
            active_pulse = None
            auto_sequence_active = False
            auto_step_label = ""
            last_pulse_ended_at = now
            message = "Pulse canceled."
        elif key in (ord("p"), ord("P")):
            if safety_descent_active:
                message = "Safety descent active; auto probe ignored."
            elif mocap_stale:
                message = "Cannot start auto probe while mocap is stale."
            else:
                auto_sequence_active = True
                auto_step_index = 0
                load_auto_step(now)
        elif key in (ord("a"), ord("A")):
            start_pulse("roll_neg", "roll", -1, -PULSE_ANGLE_DEG, 0.0, now)
        elif key in (ord("d"), ord("D")):
            start_pulse("roll_pos", "roll", 1, PULSE_ANGLE_DEG, 0.0, now)
        elif key in (ord("s"), ord("S")):
            start_pulse("pitch_neg", "pitch", -1, 0.0, -PULSE_ANGLE_DEG, now)
        elif key in (ord("w"), ord("W")):
            start_pulse("pitch_pos", "pitch", 1, 0.0, PULSE_ANGLE_DEG, now)

        if (
            mocap_stale
            and MOCAP_STALE_FORCE_DESCENT
            and max(thrust, target_thrust) > MOCAP_STALE_SHUTDOWN_MIN_THRUST_RAW
        ):
            start_safety_descent(
                f"mocap stale while thrust > {MOCAP_STALE_SHUTDOWN_MIN_THRUST_RAW}"
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
        drift_x = position[0] - start_x
        drift_y = position[1] - start_y
        drift = math.hypot(drift_x, drift_y)
        speed = math.hypot(velocity_x, velocity_y)
        battery_v, estimate_z, estimator_age = telemetry.snapshot()
        estimator_height = estimate_z - start_estimate_z

        if thrust > SAFETY_THRUST_RAW and estimator_age > ESTIMATOR_STALE_TIMEOUT_S:
            start_safety_descent(
                f"Estimator height telemetry stale for {estimator_age:.2f}s "
                f"while thrust is {thrust}"
            )
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
        if ENFORCE_BATTERY_LIMITS and battery_v and battery_v < CRITICAL_BATTERY_V:
            start_safety_descent(f"battery is critically low at {battery_v:.2f}V")
        elif ENFORCE_BATTERY_LIMITS and battery_v and battery_v < VERY_LOW_BATTERY_V:
            if low_battery_started_at is None:
                low_battery_started_at = now
            low_battery_for = now - low_battery_started_at
            if not safety_descent_active:
                message = (
                    f"Battery sag {battery_v:.2f}V; "
                    f"abort if below {VERY_LOW_BATTERY_V:.2f}V for "
                    f"{LOW_BATTERY_SUSTAINED_S:.1f}s."
                )
            if low_battery_for >= LOW_BATTERY_SUSTAINED_S:
                start_safety_descent(
                    f"battery below {VERY_LOW_BATTERY_V:.2f}V for "
                    f"{low_battery_for:.1f}s"
                )
        elif ENFORCE_BATTERY_LIMITS:
            low_battery_started_at = None

        if auto_sequence_active and now >= auto_step_ends_at:
            auto_step_index += 1
            load_auto_step(now)

        if (
            active_pulse is not None
            and not auto_sequence_active
            and now >= active_pulse["ends_at"]
        ):
            last_pulse_ended_at = now
            message = f"Pulse {active_pulse['label']} ended; neutral attitude."
            active_pulse = None

        body_velocity_x, body_velocity_y = rotate_world_to_body(velocity_x, velocity_y, yaw)
        target_yaw_command = wrap_pi(target_yaw)
        yaw_error = wrap_pi(target_yaw_command - yaw)

        if safety_descent_active:
            phase = "safety-descent"
            roll_cmd = 0.0
            pitch_cmd = 0.0
            yawrate_cmd = 0.0
        elif mocap_stale:
            phase = "mocap-stale"
            roll_cmd = 0.0
            pitch_cmd = 0.0
            yawrate_cmd = 0.0
        else:
            if active_pulse is not None:
                phase = "pulse"
            elif auto_sequence_active:
                phase = "auto-settle"
            else:
                phase = "neutral"
            roll_cmd = active_pulse["roll"] if active_pulse is not None else 0.0
            pitch_cmd = active_pulse["pitch"] if active_pulse is not None else 0.0
            yaw_active = thrust >= YAW_HOLD_MIN_THRUST or height >= YAW_HOLD_MIN_HEIGHT_M
            if yaw_active:
                raw_yawrate_cmd = (
                    YAW_KP * math.degrees(yaw_error)
                    - YAW_KD * math.degrees(yawrate_measured)
                )
                yawrate_limit = (
                    MAX_YAWRATE_DEG_S
                    if height >= YAW_HOLD_MIN_HEIGHT_M
                    else GROUND_MAX_YAWRATE_DEG_S
                )
                yawrate_cmd = YAW_COMMAND_SIGN * clamp(
                    raw_yawrate_cmd,
                    -yawrate_limit,
                    yawrate_limit,
                )
            else:
                yawrate_cmd = 0.0

        cf.commander.send_setpoint(roll_cmd, pitch_cmd, yawrate_cmd, thrust)

        should_log = frame_count != last_logged_frame
        if mocap_stale and now - last_stale_log_at >= STALE_LOG_PERIOD_S:
            should_log = True
            last_stale_log_at = now
        if exit_after_log:
            should_log = True

        pulse_id = active_pulse["id"] if active_pulse is not None else ""
        pulse_label = active_pulse["label"] if active_pulse is not None else ""
        pulse_axis = active_pulse["axis"] if active_pulse is not None else ""
        pulse_sign = active_pulse["sign"] if active_pulse is not None else ""
        pulse_age = now - active_pulse["started_at"] if active_pulse is not None else ""

        if should_log:
            logger.write({
                "wall_time_s": now,
                "elapsed_s": now - started_at,
                "phase": phase,
                "safety_descent_active": int(safety_descent_active),
                "safety_descent_reason": safety_descent_reason,
                "mocap_status": "stale" if mocap_stale else "fresh",
                "key_code": key_code,
                "key_name": key_name,
                "auto_sequence_active": int(auto_sequence_active),
                "auto_step_index": auto_step_index,
                "auto_step_label": auto_step_label,
                "pulse_id": pulse_id,
                "pulse_label": pulse_label,
                "pulse_axis": pulse_axis,
                "pulse_sign": pulse_sign,
                "pulse_age_s": pulse_age,
                "thrust_raw": thrust,
                "target_thrust_raw": int(target_thrust),
                "thrust_percent": 100.0 * thrust / MAX_THRUST,
                "roll_cmd_deg": roll_cmd,
                "pitch_cmd_deg": pitch_cmd,
                "yawrate_cmd_deg_s": yawrate_cmd,
                "yaw_command_sign": YAW_COMMAND_SIGN,
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
                "body_velocity_x_m_s": body_velocity_x,
                "body_velocity_y_m_s": body_velocity_y,
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
                "pulse_label": pulse_label or auto_step_label or "none",
                "roll": roll_cmd,
                "pitch": pitch_cmd,
                "yawrate": yawrate_cmd,
                "x": position[0],
                "y": position[1],
                "z": position[2],
                "height": height,
                "drift_x": drift_x,
                "drift_y": drift_y,
                "drift": drift,
                "vx": velocity_x,
                "vy": velocity_y,
                "vz": velocity_z,
                "speed": speed,
                "body_vx": body_velocity_x,
                "body_vy": body_velocity_y,
                "yaw": math.degrees(yaw),
                "target_yaw": math.degrees(target_yaw_command),
                "yaw_error": math.degrees(yaw_error),
                "battery": battery_v,
                "estimator_height": estimator_height,
                "estimator_age": estimator_age,
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
    print("MANUAL THRUST + MOCAP ATTITUDE RESPONSE TEST")
    print("=" * 72)
    print(f"URI: {URI}")
    print(f"Mocap: {RIGID_BODY_NAME}@{MOCAP_HOST}")
    print(f"Max manual thrust: {MAX_MANUAL_THRUST}")
    print(
        f"Pulse: +/-{PULSE_ANGLE_DEG:.1f} deg for {PULSE_DURATION_S:.2f}s, "
        f"cooldown {PULSE_COOLDOWN_S:.2f}s"
    )
    print(
        f"Ready thrust: {TAKEOFF_READY_THRUST}; "
        f"ramp up {THRUST_RAMP_UP_RAW_PER_S:.0f} raw/s"
    )
    print(
        f"Safety box: drift <= {MAX_XY_DRIFT_M:.2f}m, "
        f"mocap height <= {MAX_HEIGHT_ABOVE_START_M:.2f}m, "
        f"estimator height <= {MAX_ESTIMATOR_HEIGHT_ABOVE_START_M:.2f}m"
    )
    print(f"Mocap frame: {LOCAL_FRAME_DESCRIPTION}")
    print(f"Body yaw offset used for body-velocity logging: {BODY_YAW_OFFSET_DEG:+.1f} deg")
    print("Close cfclient first. Keep a physical power-off option ready.")
    print("=" * 72)
    input("Press ENTER to connect mocap and Crazyflie, or Ctrl+C to abort...")

    mocap_state = MocapState()
    mocap_reader = MocapReader(mocap_state)
    telemetry = Telemetry()
    logger = CsvLogger()
    cf = None

    clean_exit = False
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
            if ENFORCE_BATTERY_LIMITS and battery_v < VERY_LOW_BATTERY_V:
                raise RuntimeError("Battery is very low. Do not fly.")
            if battery_v < LOW_BATTERY_V:
                print("[WARN] Battery is low; use a fresh pack if possible.")

            input("Press ENTER to arm and start at zero thrust, or Ctrl+C to abort...")
            send_arming_request(cf, True)
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
                telemetry,
                start_position,
                start_quat,
                logger,
            )

            print("\n[INFO] Flight loop ended.")
            send_zero_thrust(cf, count=25)
            send_arming_request(cf, False)
            altitude_log.stop()
            battery_log.stop()
            clean_exit = True
    finally:
        print("\n[SAFETY] Cutting thrust and closing resources...")
        try:
            if cf is not None:
                send_zero_thrust(cf, count=25)
                send_arming_request(cf, False)
        finally:
            mocap_reader.close()
            logger.close()
        print(f"[DONE] Wrote log: {logger.output_path}")
        if clean_exit:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)


if __name__ == "__main__":
    main()
