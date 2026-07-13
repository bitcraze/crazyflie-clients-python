#!/usr/bin/env python3
"""Manual-thrust yaw-only Crazyflie test using OptiTrack/VRPN yaw.

This script is intentionally smaller than the assisted figure-8 test. It sends:

- zero roll
- zero pitch
- manual raw thrust from the keyboard
- optional yawrate from a mocap-yaw hold loop

It does not stream external position to the Crazyflie and it does not command
X/Y position hold. Keep the first tests low and brief because horizontal drift
is not corrected here.
"""

import argparse
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


DEFAULT_URI = "radio://0/80/2M"
DEFAULT_MOCAP_HOST = "192.168.1.42:3883"
DEFAULT_BODY_NAME = "crazyflie_21"
DEFAULT_OUTPUT_DIR = "flight_logs"

MIN_THRUST = 0
MAX_THRUST = 65535
DEFAULT_MAX_MANUAL_THRUST = 52000
DEFAULT_READY_THRUST = 38000
DEFAULT_SMALL_THRUST_STEP = 100
DEFAULT_BIG_THRUST_STEP = 500
THRUST_RAMP_UP_RAW_PER_S = 2500.0
THRUST_RAMP_DOWN_RAW_PER_S = 2500.0
DESCENT_RAMP_RAW_PER_S = 700.0
SAFETY_DESCENT_RAMP_RAW_PER_S = 5000.0

COMMAND_PERIOD_S = 0.02
LOG_PERIOD_MS = 100
MOCAP_TIMEOUT_S = 8.0
MOCAP_STALE_TIMEOUT_S = 0.30
MOCAP_STALE_GRACE_S = 1.00
MOCAP_RELOCK_AFTER_STALE_S = 0.45
ESTIMATOR_STALE_TIMEOUT_S = 0.75
STALE_LOG_PERIOD_S = 0.10

LOW_BATTERY_V = 3.70
VERY_LOW_BATTERY_V = 3.50
SAFETY_THRUST_RAW = 35000
DEFAULT_MAX_HEIGHT_ABOVE_START_M = 0.35
DEFAULT_MAX_XY_DRIFT_M = 0.45
DEFAULT_MAX_CLIMB_RATE_M_S = 0.75

YAW_KP = 2.0
YAW_KD = 0.18
DEFAULT_MAX_YAWRATE_DEG_S = 25.0
GROUND_MAX_YAWRATE_DEG_S = 8.0
YAW_HOLD_MIN_THRUST = 24000
YAW_HOLD_MIN_HEIGHT_M = 0.03
YAW_TARGET_STEP_DEG = 5.0
MAX_YAW_TARGET_OFFSET_DEG = 60.0

EMERGENCY_ZERO_THRUST_PACKETS = 25


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
            self.position = tuple(float(value) for value in position)
            self.quat = quat
            self.last_update = time.time()
            self.frame_count += 1

    def snapshot(self):
        with self._lock:
            return self.position, self.quat, self.last_update, self.frame_count


class MocapReader(Thread):
    def __init__(self, host, body_name, state):
        Thread.__init__(self)
        self.daemon = True
        self.host = host
        self.body_name = body_name
        self.state = state
        self.error = None
        self._stay_open = True

    def close(self):
        self._stay_open = False

    def run(self):
        while self._stay_open:
            try:
                mocap = motioncapture.connect("vrpn", {"hostname": self.host})
                self.error = None
                print(f"[MOCAP] Connected to VRPN at {self.host}, looking for '{self.body_name}'")
                announced = False
                while self._stay_open:
                    mocap.waitForNextFrame()
                    body = mocap.rigidBodies.get(self.body_name)
                    if body is None:
                        continue
                    if not announced:
                        print(f"[MOCAP] Found and tracking rigid body: {self.body_name}")
                        announced = True
                    quat = normalized_quat(body.rotation)
                    if quat is None:
                        continue
                    self.state.update(body.position, quat)
            except Exception as exc:
                self.error = exc
                if self._stay_open:
                    print(f"[WARN] Mocap reader lost connection: {exc}; retrying...")
                    time.sleep(0.5)


class Telemetry:
    def __init__(self):
        self._lock = Lock()
        self.values = {}
        self.updated_at = {}

    def update(self, data):
        now = time.time()
        with self._lock:
            self.values.update(data)
            for key in data:
                self.updated_at[key] = now

    def snapshot(self):
        with self._lock:
            values = dict(self.values)
            ages = {
                key: time.time() - updated_at
                for key, updated_at in self.updated_at.items()
            }
        return values, ages

    def get(self, key, default=0.0):
        with self._lock:
            return self.values.get(key, default)


class CsvLogger:
    FIELDNAMES = [
        "wall_time_s",
        "elapsed_s",
        "phase",
        "stop_reason",
        "mocap_status",
        "mocap_age_s",
        "mocap_frame_count",
        "mocap_x",
        "mocap_y",
        "mocap_z",
        "mocap_qx",
        "mocap_qy",
        "mocap_qz",
        "mocap_qw",
        "mocap_yaw_deg",
        "target_yaw_deg",
        "manual_yaw_offset_deg",
        "yaw_error_deg",
        "yawrate_measured_deg_s",
        "yawrate_cmd_deg_s",
        "yaw_hold_enabled",
        "yaw_active",
        "yaw_command_sign",
        "thrust_raw",
        "target_thrust_raw",
        "thrust_percent",
        "height_above_start_m",
        "xy_drift_from_start_m",
        "mocap_vz_m_s",
        "pm.vbat",
        "stateEstimate.z",
        "stateEstimate.yaw",
        "stabilizer.yaw",
        "gyro.z",
        "estimate_packet_age_s",
        "safety_descent_active",
        "safety_descent_reason",
    ]

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", newline="")
        self.writer = csv.DictWriter(
            self.file,
            fieldnames=self.FIELDNAMES,
            extrasaction="ignore",
        )
        self.writer.writeheader()
        self.file.flush()

    def write(self, row):
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        self.file.close()


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


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


def slew_toward(current, target, up_rate, down_rate, dt):
    if target > current:
        return min(target, current + up_rate * dt)
    if target < current:
        return max(target, current - down_rate * dt)
    return current


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
                f"pos=({position[0]:+.3f}, {position[1]:+.3f}, {position[2]:+.3f}) "
                f"yaw={math.degrees(yaw_from_quat(quat)):+.1f}deg "
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


def output_path(output):
    if output:
        return Path(output)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(DEFAULT_OUTPUT_DIR) / f"mocap-yaw-test-{timestamp}.csv"


def setup_telemetry(cf, telemetry):
    logconf = LogConfig(name="YawTest", period_in_ms=LOG_PERIOD_MS)
    for variable in (
        "pm.vbat",
        "stateEstimate.z",
        "stateEstimate.yaw",
        "stabilizer.yaw",
        "gyro.z",
    ):
        logconf.add_variable(variable, "float")

    def on_data(timestamp, data, logconf):
        del timestamp, logconf
        telemetry.update(data)

    def on_error(logconf, message):
        print(f"[WARN] Logger error from {logconf.name}: {message}")

    cf.log.add_config(logconf)
    logconf.data_received_cb.add_callback(on_data)
    logconf.error_cb.add_callback(on_error)
    logconf.start()
    return logconf


def add_line(stdscr, y, x, text):
    max_y, max_x = stdscr.getmaxyx()
    if y >= max_y or x >= max_x:
        return
    available = max_x - x - 1
    if available > 0:
        stdscr.addstr(y, x, text[:available])


def draw(
    stdscr,
    state,
    telemetry_values,
    mocap_error,
    message,
):
    stdscr.erase()
    add_line(stdscr, 0, 0, "Crazyflie Mocap Yaw-Only Test")
    add_line(stdscr, 2, 0, "Controls:")
    add_line(stdscr, 3, 2, "UP/DOWN          target thrust +/- small step")
    add_line(stdscr, 4, 2, "PAGEUP/PAGEDN    target thrust + big step / slow descent")
    add_line(stdscr, 5, 2, "R                ramp to ready thrust")
    add_line(stdscr, 6, 2, "J / L            yaw target -/+ step")
    add_line(stdscr, 7, 2, "C                recenter yaw target to current mocap yaw")
    add_line(stdscr, 8, 2, "Y                toggle yaw hold")
    add_line(stdscr, 9, 2, "SPACE/Q/ESC      cut thrust and exit")

    add_line(
        stdscr,
        11,
        0,
        f"Thrust: {state['thrust']:5d} -> {int(state['target_thrust']):5d} "
        f"({100.0 * state['thrust'] / MAX_THRUST:4.1f}%)",
    )
    add_line(
        stdscr,
        12,
        0,
        f"Yaw: {state['yaw_deg']:+7.1f} deg  target {state['target_yaw_deg']:+7.1f} deg  "
        f"error {state['yaw_error_deg']:+6.1f} deg",
    )
    add_line(
        stdscr,
        13,
        0,
        f"Yawrate cmd: {state['yawrate_cmd_deg_s']:+6.1f} deg/s  "
        f"measured {state['yawrate_measured_deg_s']:+6.1f} deg/s  "
        f"hold {'ON' if state['yaw_hold_enabled'] else 'OFF'}",
    )
    add_line(
        stdscr,
        14,
        0,
        f"Height: {state['height']:+.3f} m  XY drift: {state['drift']:.3f} m  "
        f"Mocap age: {state['mocap_age']:.3f} s",
    )
    add_line(
        stdscr,
        15,
        0,
        f"Battery: {telemetry_values.get('pm.vbat', 0.0):.2f} V  "
        f"Estimator z: {telemetry_values.get('stateEstimate.z', 0.0):+.3f} m",
    )
    add_line(stdscr, 17, 0, "Roll and pitch are always commanded as zero in this test.")
    add_line(stdscr, 18, 0, "Keep one hand ready to cut power. This does not hold X/Y position.")
    if mocap_error:
        add_line(stdscr, 20, 0, f"Mocap reader warning: {mocap_error}")
    if message:
        add_line(stdscr, 22, 0, message)
    stdscr.refresh()


def run_control_loop(
    stdscr,
    cf,
    mocap_state,
    mocap_reader,
    telemetry,
    logger,
    args,
    start_position,
    start_quat,
):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    start_x, start_y, start_z = start_position
    target_yaw = yaw_from_quat(start_quat)
    manual_yaw_offset = 0.0
    yaw_hold_enabled = True

    thrust = 0.0
    target_thrust = 0.0
    descent_active = False
    safety_descent_active = False
    safety_descent_reason = ""
    message = "Raise thrust manually. Yaw hold starts only above the yaw-active threshold."
    stop_reason = ""

    started_at = time.time()
    last_loop_at = started_at
    last_draw_at = 0.0
    last_logged_frame = None
    last_stale_log_at = 0.0
    previous_sample = None
    stale_started_at = None
    exit_after_log = False
    yawrate_measured = 0.0
    velocity_z = 0.0

    def start_safety_descent(reason):
        nonlocal target_thrust, descent_active, safety_descent_active
        nonlocal safety_descent_reason, message
        if not safety_descent_active:
            safety_descent_reason = reason
        target_thrust = min(target_thrust, thrust)
        descent_active = True
        safety_descent_active = True
        message = f"Safety descent: {safety_descent_reason}."

    while True:
        now = time.time()
        dt = max(0.0, now - last_loop_at)
        last_loop_at = now

        position, quat, last_update, frame_count = mocap_state.snapshot()
        if position is None or quat is None:
            raise RuntimeError("Internal error: mocap pose disappeared")

        mocap_age = now - last_update if last_update else float("inf")
        mocap_stale = mocap_age > MOCAP_STALE_TIMEOUT_S
        yaw = yaw_from_quat(quat)
        height = position[2] - start_z
        drift = math.hypot(position[0] - start_x, position[1] - start_y)

        if mocap_stale:
            if stale_started_at is None:
                stale_started_at = now
                previous_sample = None
                yawrate_measured = 0.0
                velocity_z = 0.0
                message = "Mocap stale: yaw command disabled."
            stale_for = now - stale_started_at
            if (
                max(thrust, target_thrust) >= YAW_HOLD_MIN_THRUST
                or height >= YAW_HOLD_MIN_HEIGHT_M
            ):
                start_safety_descent(
                    "mocap stale while yaw/airborne guard was active"
                )
            if stale_for > MOCAP_STALE_GRACE_S:
                start_safety_descent(f"mocap stale for {stale_for:.2f}s")
        elif stale_started_at is not None:
            stale_for = now - stale_started_at
            stale_started_at = None
            previous_sample = None
            yawrate_measured = 0.0
            velocity_z = 0.0
            if stale_for >= MOCAP_RELOCK_AFTER_STALE_S:
                target_yaw = yaw
                manual_yaw_offset = 0.0
                message = "Mocap reacquired; yaw target recentered."
            else:
                message = "Mocap reacquired; continuing yaw hold."

        if not mocap_stale:
            if previous_sample is None:
                previous_sample = (position, yaw, last_update, frame_count)
            elif frame_count != previous_sample[3]:
                previous_position, previous_yaw, previous_time, _ = previous_sample
                sample_dt = last_update - previous_time
                if sample_dt > 0.0:
                    measured_yawrate = wrap_pi(yaw - previous_yaw) / sample_dt
                    measured_vz = (position[2] - previous_position[2]) / sample_dt
                    yawrate_measured = 0.70 * yawrate_measured + 0.30 * measured_yawrate
                    velocity_z = 0.70 * velocity_z + 0.30 * measured_vz
                previous_sample = (position, yaw, last_update, frame_count)

        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            stop_reason = "operator_exit"
            thrust = 0
            target_thrust = 0
            send_zero_thrust(cf, count=EMERGENCY_ZERO_THRUST_PACKETS, send_stop=False)
            message = "Exit requested; zero thrust sent."
            exit_after_log = True
        elif key == ord(" "):
            stop_reason = "operator_cut"
            thrust = 0
            target_thrust = 0
            send_zero_thrust(cf, count=EMERGENCY_ZERO_THRUST_PACKETS, send_stop=False)
            message = "Emergency zero thrust sent immediately."
            exit_after_log = True
        elif key == curses.KEY_UP:
            if safety_descent_active:
                message = "Safety descent active; thrust increase ignored."
            else:
                target_thrust = int(clamp(target_thrust + args.step, MIN_THRUST, args.max_manual_thrust))
                descent_active = False
                message = f"Target thrust +{args.step}; ramping up."
        elif key == curses.KEY_DOWN:
            target_thrust = int(clamp(target_thrust - args.step, MIN_THRUST, args.max_manual_thrust))
            descent_active = False
            message = f"Target thrust -{args.step}; ramping down."
        elif key == curses.KEY_PPAGE:
            if safety_descent_active:
                message = "Safety descent active; thrust increase ignored."
            else:
                target_thrust = int(clamp(target_thrust + args.big_step, MIN_THRUST, args.max_manual_thrust))
                descent_active = False
                message = f"Target thrust +{args.big_step}; ramping up."
        elif key == curses.KEY_NPAGE:
            descent_active = True
            message = "Slow descent ramp active."
        elif key in (ord("r"), ord("R")):
            if safety_descent_active:
                message = "Safety descent active; ready thrust ignored."
            else:
                target_thrust = int(clamp(args.ready_thrust, MIN_THRUST, args.max_manual_thrust))
                descent_active = False
                message = f"Ready target {args.ready_thrust}; thrust is ramping up."
        elif key in (ord("j"), ord("J")):
            manual_yaw_offset = math.radians(
                clamp(
                    math.degrees(manual_yaw_offset) - args.yaw_step_deg,
                    -MAX_YAW_TARGET_OFFSET_DEG,
                    MAX_YAW_TARGET_OFFSET_DEG,
                )
            )
            message = f"Yaw target offset {math.degrees(manual_yaw_offset):+.1f} deg."
        elif key in (ord("l"), ord("L")):
            manual_yaw_offset = math.radians(
                clamp(
                    math.degrees(manual_yaw_offset) + args.yaw_step_deg,
                    -MAX_YAW_TARGET_OFFSET_DEG,
                    MAX_YAW_TARGET_OFFSET_DEG,
                )
            )
            message = f"Yaw target offset {math.degrees(manual_yaw_offset):+.1f} deg."
        elif key in (ord("c"), ord("C")):
            if mocap_stale:
                message = "Cannot recenter yaw while mocap is stale."
            else:
                target_yaw = yaw
                manual_yaw_offset = 0.0
                message = "Yaw target recentered to current mocap yaw."
        elif key in (ord("y"), ord("Y")):
            yaw_hold_enabled = not yaw_hold_enabled
            message = f"Yaw hold {'enabled' if yaw_hold_enabled else 'disabled'}."

        if safety_descent_active:
            descent_active = True

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
                args.max_manual_thrust,
            )
            if target_thrust <= MIN_THRUST:
                descent_active = False
                if safety_descent_active:
                    stop_reason = safety_descent_reason or "safety_descent_complete"
                    thrust = 0
                    target_thrust = 0
                    exit_after_log = True
                    message = "Safety descent reached zero thrust."
                else:
                    message = "Slow descent reached zero thrust."

        target_thrust = clamp(target_thrust, MIN_THRUST, args.max_manual_thrust)
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
        thrust = int(clamp(thrust, MIN_THRUST, args.max_manual_thrust))

        telemetry_values, telemetry_ages = telemetry.snapshot()
        battery_v = telemetry_values.get("pm.vbat", 0.0)
        estimate_age = telemetry_ages.get("stateEstimate.z", float("inf"))

        if battery_v and battery_v < VERY_LOW_BATTERY_V:
            start_safety_descent("battery is very low")
        if estimate_age > ESTIMATOR_STALE_TIMEOUT_S and thrust > SAFETY_THRUST_RAW:
            start_safety_descent(
                f"estimator height telemetry stale for {estimate_age:.2f}s"
            )
        safety_guard_active = (
            max(thrust, target_thrust) >= YAW_HOLD_MIN_THRUST
            or height >= YAW_HOLD_MIN_HEIGHT_M
        )
        if not mocap_stale and safety_guard_active:
            if height > args.max_height_above_start:
                start_safety_descent(
                    f"mocap height {height:.3f}m exceeded {args.max_height_above_start:.3f}m"
                )
            if drift > args.max_xy_drift:
                start_safety_descent(
                    f"XY drift {drift:.3f}m exceeded {args.max_xy_drift:.3f}m"
                )
            if height > 0.03 and velocity_z > args.max_climb_rate:
                start_safety_descent(
                    f"mocap climb rate {velocity_z:.3f}m/s exceeded {args.max_climb_rate:.3f}m/s"
                )

        target_yaw_command = wrap_pi(target_yaw + manual_yaw_offset)
        yaw_error = wrap_pi(target_yaw_command - yaw)
        yaw_active = (
            yaw_hold_enabled
            and not safety_descent_active
            and not mocap_stale
            and (thrust >= YAW_HOLD_MIN_THRUST or height >= YAW_HOLD_MIN_HEIGHT_M)
        )
        if yaw_active:
            raw_yawrate_cmd = (
                YAW_KP * math.degrees(yaw_error)
                - YAW_KD * math.degrees(yawrate_measured)
            )
            yawrate_limit = (
                args.max_yawrate
                if height >= YAW_HOLD_MIN_HEIGHT_M
                else min(args.max_yawrate, GROUND_MAX_YAWRATE_DEG_S)
            )
            yawrate_cmd = args.yaw_command_sign * clamp(
                raw_yawrate_cmd,
                -yawrate_limit,
                yawrate_limit,
            )
        else:
            yawrate_cmd = 0.0

        phase = "yaw-hold" if yaw_active else "manual-thrust"
        if mocap_stale:
            phase = "mocap-stale"
        if safety_descent_active:
            phase = "safety-descent"

        cf.commander.send_setpoint(0.0, 0.0, yawrate_cmd, thrust)

        should_log = frame_count != last_logged_frame
        if mocap_stale and now - last_stale_log_at >= STALE_LOG_PERIOD_S:
            should_log = True
            last_stale_log_at = now
        if exit_after_log:
            should_log = True

        row = {
            "wall_time_s": now,
            "elapsed_s": now - started_at,
            "phase": phase,
            "stop_reason": stop_reason,
            "mocap_status": "stale" if mocap_stale else "fresh",
            "mocap_age_s": mocap_age,
            "mocap_frame_count": frame_count,
            "mocap_x": position[0],
            "mocap_y": position[1],
            "mocap_z": position[2],
            "mocap_qx": quat.x,
            "mocap_qy": quat.y,
            "mocap_qz": quat.z,
            "mocap_qw": quat.w,
            "mocap_yaw_deg": math.degrees(yaw),
            "target_yaw_deg": math.degrees(target_yaw_command),
            "manual_yaw_offset_deg": math.degrees(manual_yaw_offset),
            "yaw_error_deg": math.degrees(yaw_error),
            "yawrate_measured_deg_s": math.degrees(yawrate_measured),
            "yawrate_cmd_deg_s": yawrate_cmd,
            "yaw_hold_enabled": int(yaw_hold_enabled),
            "yaw_active": int(yaw_active),
            "yaw_command_sign": args.yaw_command_sign,
            "thrust_raw": thrust,
            "target_thrust_raw": int(target_thrust),
            "thrust_percent": 100.0 * thrust / MAX_THRUST,
            "height_above_start_m": height,
            "xy_drift_from_start_m": drift,
            "mocap_vz_m_s": velocity_z,
            "pm.vbat": battery_v,
            "stateEstimate.z": telemetry_values.get("stateEstimate.z", ""),
            "stateEstimate.yaw": telemetry_values.get("stateEstimate.yaw", ""),
            "stabilizer.yaw": telemetry_values.get("stabilizer.yaw", ""),
            "gyro.z": telemetry_values.get("gyro.z", ""),
            "estimate_packet_age_s": estimate_age if math.isfinite(estimate_age) else "",
            "safety_descent_active": int(safety_descent_active),
            "safety_descent_reason": safety_descent_reason,
        }
        if should_log:
            logger.write(row)
            last_logged_frame = frame_count

        if now - last_draw_at >= 0.1:
            draw(
                stdscr,
                {
                    "thrust": thrust,
                    "target_thrust": target_thrust,
                    "yaw_deg": math.degrees(yaw),
                    "target_yaw_deg": math.degrees(target_yaw_command),
                    "yaw_error_deg": math.degrees(yaw_error),
                    "yawrate_cmd_deg_s": yawrate_cmd,
                    "yawrate_measured_deg_s": math.degrees(yawrate_measured),
                    "yaw_hold_enabled": yaw_hold_enabled,
                    "height": height,
                    "drift": drift,
                    "mocap_age": mocap_age,
                },
                telemetry_values,
                mocap_reader.error,
                message,
            )
            last_draw_at = now

        if exit_after_log:
            break

        time.sleep(COMMAND_PERIOD_S)

    return stop_reason or "operator_exit", thrust


def run(args):
    logging.basicConfig(level=logging.ERROR)
    cflib.crtp.init_drivers()

    mocap_state = MocapState()
    mocap_reader = MocapReader(args.mocap_host, args.body_name, mocap_state)
    mocap_reader.start()

    log_path = output_path(args.output)
    logger = CsvLogger(log_path)
    telemetry = Telemetry()
    telemetry_logconf = None
    clean_exit = False

    print("=" * 72)
    print("CRAZYFLIE MOCAP YAW-ONLY TEST")
    print("=" * 72)
    print(f"URI: {args.uri}")
    print(f"VRPN: {args.mocap_host}, rigid body: {args.body_name}")
    print(f"Output: {log_path}")
    print(f"Yaw command sign: {args.yaw_command_sign:+.0f}")
    print(f"Yaw rate cap: {args.max_yawrate:.1f} deg/s")
    print("This sends zero roll/pitch, keyboard thrust, and mocap-based yawrate only.")
    print("Close cfclient first; only one process can own the radio.")
    print("=" * 72)

    try:
        start_position, start_quat = wait_for_fresh_pose(mocap_state)
        input("Press ENTER to connect to Crazyflie, or Ctrl+C to abort...")

        with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
            cf = scf.cf
            print("[CF] Connected.")
            telemetry_logconf = setup_telemetry(cf, telemetry)
            time.sleep(0.8)

            battery_v = telemetry.get("pm.vbat", None)
            if battery_v is None:
                print("[WARN] No battery telemetry received yet.")
            else:
                print(f"[CF] Battery: {battery_v:.2f} V")
            if battery_v is not None and battery_v < VERY_LOW_BATTERY_V:
                raise RuntimeError("Battery is very low. Do not fly.")
            if battery_v is not None and battery_v < LOW_BATTERY_V:
                print("[WARN] Battery is low.")

            start_position, start_quat = wait_for_fresh_pose(mocap_state)
            print(
                "[START] "
                f"pos=({start_position[0]:+.3f}, {start_position[1]:+.3f}, {start_position[2]:+.3f}) "
                f"yaw={math.degrees(yaw_from_quat(start_quat)):+.1f}deg"
            )
            input("Press ENTER to arm and start at zero thrust, or Ctrl+C to abort...")

            stop_reason = "not_started"
            last_thrust = 0
            try:
                cf.platform.send_arming_request(True)
                time.sleep(1.0)
                send_zero_thrust(cf, count=25, send_stop=False)
                stop_reason, last_thrust = curses.wrapper(
                    run_control_loop,
                    cf,
                    mocap_state,
                    mocap_reader,
                    telemetry,
                    logger,
                    args,
                    start_position,
                    start_quat,
                )
            finally:
                print("\n[SAFETY] Cutting thrust and disarming...")
                send_zero_thrust(cf, count=25)
                cf.platform.send_arming_request(False)
                print(f"[DONE] Stop reason: {stop_reason}. Last thrust: {last_thrust}.")
        clean_exit = True
    finally:
        if telemetry_logconf is not None:
            try:
                telemetry_logconf.stop()
            except Exception:
                pass
        mocap_reader.close()
        logger.close()
        print(f"[DONE] Log: {log_path}")
        if clean_exit:
            # The motioncapture VRPN extension has no public close hook and can
            # abort during interpreter teardown after an otherwise clean flight
            # stop. All flight-critical cleanup above has already completed.
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--mocap-host", default=DEFAULT_MOCAP_HOST)
    parser.add_argument("--body-name", default=DEFAULT_BODY_NAME)
    parser.add_argument("--output")
    parser.add_argument("--step", type=int, default=DEFAULT_SMALL_THRUST_STEP)
    parser.add_argument("--big-step", type=int, default=DEFAULT_BIG_THRUST_STEP)
    parser.add_argument("--ready-thrust", type=int, default=DEFAULT_READY_THRUST)
    parser.add_argument("--max-manual-thrust", type=int, default=DEFAULT_MAX_MANUAL_THRUST)
    parser.add_argument("--yaw-step-deg", type=float, default=YAW_TARGET_STEP_DEG)
    parser.add_argument("--max-yawrate", type=float, default=DEFAULT_MAX_YAWRATE_DEG_S)
    parser.add_argument(
        "--yaw-command-sign",
        type=float,
        choices=(-1.0, 1.0),
        default=1.0,
        help="Flip to -1 if yaw hold drives away from the mocap target.",
    )
    parser.add_argument("--max-height-above-start", type=float, default=DEFAULT_MAX_HEIGHT_ABOVE_START_M)
    parser.add_argument("--max-xy-drift", type=float, default=DEFAULT_MAX_XY_DRIFT_M)
    parser.add_argument("--max-climb-rate", type=float, default=DEFAULT_MAX_CLIMB_RATE_M_S)
    args = parser.parse_args()

    if args.max_manual_thrust < MIN_THRUST or args.max_manual_thrust > MAX_THRUST:
        raise ValueError(f"--max-manual-thrust must be between {MIN_THRUST} and {MAX_THRUST}")
    if args.ready_thrust < MIN_THRUST or args.ready_thrust > args.max_manual_thrust:
        raise ValueError("--ready-thrust must be between 0 and --max-manual-thrust")
    if args.step <= 0 or args.big_step <= 0:
        raise ValueError("--step and --big-step must be positive")
    if args.max_yawrate <= 0.0:
        raise ValueError("--max-yawrate must be positive")
    if args.yaw_step_deg <= 0.0:
        raise ValueError("--yaw-step-deg must be positive")
    if args.max_height_above_start <= 0.0:
        raise ValueError("--max-height-above-start must be positive")
    if args.max_xy_drift <= 0.0:
        raise ValueError("--max-xy-drift must be positive")
    if args.max_climb_rate <= 0.0:
        raise ValueError("--max-climb-rate must be positive")
    return args


if __name__ == "__main__":
    run(parse_args())
