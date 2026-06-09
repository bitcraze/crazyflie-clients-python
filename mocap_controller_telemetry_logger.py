#!/usr/bin/env python3
"""
Manual Logitech controller flight controller + observer logger for Crazyflie.

This script owns the Crazyradio link, reads a Logitech joystick, sends manual
commander setpoints, logs those outgoing commands, logs telemetry returned by
the Crazyflie, and optionally logs mocap pose for comparison.

It does not use High Level Commander and does not run autonomous takeoff,
landing, go_to, figure-8, replay, or position control.

Props-off observer test:

    python3 mocap_controller_telemetry_logger.py --props-off

Manual flight controller + logger:

    python3 mocap_controller_telemetry_logger.py
"""

import argparse
import csv
import fcntl
import json
import math
import os
import select
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from threading import Thread

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

try:
    import motioncapture
except ImportError:
    motioncapture = None


# Radio URI and lab mocap defaults. The controller default is intentionally
# None: Linux may renumber /dev/input/js0 and js1 after unplug/replug, so the
# script auto-detects the stable /dev/input/by-id Logitech joystick symlink.
DEFAULT_URI = "radio://0/80/2M"
DEFAULT_CONTROLLER_DEVICE = None
DEFAULT_MOCAP_HOST = "192.168.1.42:3883"
DEFAULT_RIGID_BODY_NAME = "crazyflie_21"
DEFAULT_OUTPUT_DIR = "flight_logs"

# Default Logitech Dual Action axis numbers. If these ever disagree with
# cfclient, pass --cfclient-input-config so this script reads the same JSON axis
# ids/scales that cfclient uses.
ROLL_AXIS = 0
PITCH_AXIS = 1
YAW_AXIS = 2
THRUST_AXIS = 3

DEFAULT_MAX_ROLL_DEG = 12.0
DEFAULT_MAX_PITCH_DEG = 12.0
DEFAULT_MAX_YAWRATE_DEG_S = 60.0
DEFAULT_MAX_THRUST = 52000
MIN_THRUST = 0
DEADZONE = 0.10

# The command loop runs at 50 Hz. Crazyflie logging is slower to keep the radio
# link from being overloaded by estimator, attitude, IMU, battery, motor, and
# mocap comparison data all at once.
CONTROL_PERIOD_S = 0.02
PRINT_PERIOD_S = 1.0
LOG_PERIOD_MS = 100
MOCAP_STALE_TIMEOUT_S = 0.30
EMERGENCY_ZERO_THRUST_PACKETS = 40
EMERGENCY_ZERO_THRUST_PERIOD_S = 0.01
DEFAULT_THRUST_SLEW_RAW_PER_S = 6000.0
DEFAULT_XY_ASSIST_KP = 10.0
DEFAULT_XY_ASSIST_KD = 5.0
DEFAULT_XY_ASSIST_MAX_ANGLE_DEG = 4.0
DEFAULT_XY_ASSIST_FULL_HEIGHT_M = 0.08
DEFAULT_XY_ASSIST_MIN_ACTIVE_ANGLE_DEG = 2.0
DEFAULT_XY_ASSIST_MIN_THRUST = 28000
DEFAULT_XY_ASSIST_MAX_DRIFT_M = 0.30
DEFAULT_XY_ASSIST_BODY_YAW_OFFSET_DEG = 0.0
DEFAULT_XY_ASSIST_YAW_SMOOTHING = 0.8
DEFAULT_XY_ASSIST_MAX_YAW_JUMP_DEG = 25.0
DEFAULT_XY_ASSIST_ROLL_SIGN = -1.0
DEFAULT_XY_ASSIST_PITCH_SIGN = -1.0

JS_EVENT_FMT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FMT)
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80


@dataclass(frozen=True)
class QuatSnapshot:
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class ControllerMapping:
    """Joystick axis/button mapping after applying cfclient-style scales.

    The scale fields are the important part: Linux reports raw joystick axes as
    -32767..32767, but cfclient mappings often invert pitch or thrust. Keeping
    the mapping explicit lets the CSV show both raw axes and normalized commands.
    """
    roll_axis: int = ROLL_AXIS
    pitch_axis: int = PITCH_AXIS
    yaw_axis: int = YAW_AXIS
    thrust_axis: int = THRUST_AXIS
    roll_scale: float = 1.0
    pitch_scale: float = -1.0
    yaw_scale: float = 1.0
    thrust_scale: float = -1.0
    emergency_button: int = 9
    source: str = "built-in Logitech Dual Action / cfclient PS4_shoulder_btns_yaw equivalent"


class ControllerState:
    """Thread-safe copy of the most recent joystick state.

    ControllerReader updates this from a background thread. The flight loop only
    reads snapshots, which avoids holding a lock while sending radio commands.
    The CSV logs raw axis values, normalized values, deadzoned values, and the
    requested setpoint so controller mapping mistakes are easy to diagnose.
    """

    def __init__(self, mapping):
        self.mapping = mapping
        self._lock = Lock()
        self.axes_raw = {}
        self.axes_norm = {}
        self.buttons = {}
        self.roll_norm = 0.0
        self.pitch_norm = 0.0
        self.yaw_norm = 0.0
        self.thrust_norm = 0.0
        self.thrust_axis_seen = False
        self.event_count = 0
        self.last_event_time = 0.0
        self.last_event_type = ""
        self.last_event_number = ""
        self.last_event_value = ""
        self.emergency_stop = False

    def update_axis(self, number, raw_value):
        # Linux joystick axis values are signed 16-bit-ish integers. Normalize
        # first, then apply the cfclient/built-in scale and deadzone per axis.
        normalized = clamp(raw_value / 32767.0, -1.0, 1.0)
        with self._lock:
            self.axes_raw[number] = raw_value
            self.axes_norm[number] = normalized
            if number == self.mapping.roll_axis:
                self.roll_norm = apply_deadzone(normalized * self.mapping.roll_scale)
            elif number == self.mapping.pitch_axis:
                self.pitch_norm = apply_deadzone(normalized * self.mapping.pitch_scale)
            elif number == self.mapping.yaw_axis:
                self.yaw_norm = apply_deadzone(normalized * self.mapping.yaw_scale)
            elif number == self.mapping.thrust_axis:
                thrust_value = normalized * self.mapping.thrust_scale
                self.thrust_norm = clamp((thrust_value + 1.0) / 2.0, 0.0, 1.0)
                self.thrust_axis_seen = True
            self._record_event("axis", number, raw_value)

    def update_button(self, number, raw_value):
        with self._lock:
            self.buttons[number] = raw_value
            if number == self.mapping.emergency_button and raw_value:
                self.emergency_stop = True
            self._record_event("button", number, raw_value)

    def _record_event(self, event_type, number, raw_value):
        self.event_count += 1
        self.last_event_time = time.time()
        self.last_event_type = event_type
        self.last_event_number = number
        self.last_event_value = raw_value

    def snapshot(self, args):
        with self._lock:
            requested_thrust = MIN_THRUST + self.thrust_norm * (args.max_thrust - MIN_THRUST)
            return {
                "controller_event_count": self.event_count,
                "controller_last_event_age_s": time.time() - self.last_event_time if self.last_event_time else "",
                "controller_last_event_type": self.last_event_type,
                "controller_last_event_number": self.last_event_number,
                "controller_last_event_value": self.last_event_value,
                "roll_axis_raw": self.axes_raw.get(self.mapping.roll_axis, ""),
                "pitch_axis_raw": self.axes_raw.get(self.mapping.pitch_axis, ""),
                "yaw_axis_raw": self.axes_raw.get(self.mapping.yaw_axis, ""),
                "thrust_axis_raw": self.axes_raw.get(self.mapping.thrust_axis, ""),
                "roll_axis_norm_raw": self.axes_norm.get(self.mapping.roll_axis, ""),
                "pitch_axis_norm_raw": self.axes_norm.get(self.mapping.pitch_axis, ""),
                "yaw_axis_norm_raw": self.axes_norm.get(self.mapping.yaw_axis, ""),
                "thrust_axis_norm_raw": self.axes_norm.get(self.mapping.thrust_axis, ""),
                "roll_norm_after_deadzone": self.roll_norm,
                "pitch_norm_after_deadzone": self.pitch_norm,
                "yaw_norm_after_deadzone": self.yaw_norm,
                "thrust_norm": self.thrust_norm,
                "requested_roll_deg": self.roll_norm * args.max_roll_deg,
                "requested_pitch_deg": self.pitch_norm * args.max_pitch_deg,
                "requested_yawrate_deg_s": self.yaw_norm * args.max_yawrate_deg_s,
                "requested_thrust_raw": int(requested_thrust),
                "thrust_axis_seen": int(self.thrust_axis_seen),
                "button_0": self.buttons.get(0, 0),
                "button_1": self.buttons.get(1, 0),
                "button_2": self.buttons.get(2, 0),
                "button_3": self.buttons.get(3, 0),
                "button_4": self.buttons.get(4, 0),
                "button_5": self.buttons.get(5, 0),
                "button_6": self.buttons.get(6, 0),
                "button_7": self.buttons.get(7, 0),
                "button_8": self.buttons.get(8, 0),
                "button_9": self.buttons.get(9, 0),
                "emergency_stop": int(self.emergency_stop),
            }


class ControllerReader(Thread):
    """Reads /dev/input/js* joystick events in the background.

    This deliberately uses the old joystick API, not /dev/input/event*. The
    by-id auto-detection must therefore select the plain '*-joystick' symlink,
    not '*-event-joystick'. If this thread ever crashes during powered flight,
    run_loop sees self.error and emergency-stops instead of reusing stale input.
    """

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
            self._js_file = open(self.device_path, "rb")
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
                    self.state.update_axis(number, value)
                elif event_type == JS_EVENT_BUTTON:
                    self.state.update_button(number, value)
        except Exception as exc:
            self.error = exc


class TelemetryState:
    """Latest Crazyflie log values plus packet age/count metadata.

    The log callbacks arrive asynchronously from cflib. The flight loop combines
    the most recent telemetry snapshot with the exact outgoing setpoint for each
    CSV row, so the file can answer both "what did we command?" and "what did
    the drone estimate/sense around that time?".
    """

    def __init__(self):
        self._lock = Lock()
        self.values = {}
        self.last_packet_time_by_group = {}
        self.packet_count_by_group = {}

    def update(self, group, data):
        with self._lock:
            self.values.update(data)
            self.last_packet_time_by_group[group] = time.time()
            self.packet_count_by_group[group] = self.packet_count_by_group.get(group, 0) + 1

    def snapshot(self):
        with self._lock:
            return dict(self.values), dict(self.last_packet_time_by_group), dict(self.packet_count_by_group)


class MocapState:
    """Latest OptiTrack/VRPN pose for the tracked rigid body.

    Mocap is treated as observer data unless --mocap-xy-assist is enabled. The
    script does not reset or feed the Crazyflie estimator; it only logs estimator
    vs mocap disagreement for later analysis.
    """

    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.quat = None
        self.last_update = 0.0
        self.frame_count = 0

    def update(self, position, quat):
        with self._lock:
            self.position = tuple(position)
            self.quat = QuatSnapshot(quat.x, quat.y, quat.z, quat.w)
            self.last_update = time.time()
            self.frame_count += 1

    def snapshot(self):
        with self._lock:
            return self.position, self.quat, self.last_update, self.frame_count


class MocapVelocityState:
    """Small filtered velocity estimate from mocap position differences.

    XY assist uses this as the D term. It updates only when the mocap frame count
    changes, then low-pass filters velocity so one noisy frame does not dominate
    the roll/pitch correction.
    """

    def __init__(self):
        self.previous_position = None
        self.previous_time = 0.0
        self.previous_frame_count = 0
        self.vx = 0.0
        self.vy = 0.0

    def update(self, position, last_update, frame_count, smoothing):
        if position is None or last_update == 0.0:
            return self.vx, self.vy
        if self.previous_position is None:
            self.previous_position = position
            self.previous_time = last_update
            self.previous_frame_count = frame_count
            return self.vx, self.vy
        if frame_count == self.previous_frame_count:
            return self.vx, self.vy

        dt = last_update - self.previous_time
        if dt > 0.0:
            measured_vx = (position[0] - self.previous_position[0]) / dt
            measured_vy = (position[1] - self.previous_position[1]) / dt
            alpha = clamp(smoothing, 0.0, 0.99)
            self.vx = alpha * self.vx + (1.0 - alpha) * measured_vx
            self.vy = alpha * self.vy + (1.0 - alpha) * measured_vy

        self.previous_position = position
        self.previous_time = last_update
        self.previous_frame_count = frame_count
        return self.vx, self.vy


class AssistYawState:
    """Filtered yaw used only for rotating XY assist into the drone body frame.

    Fixed yaw is preferred for sign/authority tests because it isolates roll and
    pitch signs from mocap yaw jumps. If fixed yaw is not provided, this filter
    rejects implausibly large yaw jumps and logs the rejection count.
    """

    def __init__(self):
        self.filtered_yaw_deg = None
        self.rejected_jump_count = 0

    def update(self, raw_yaw_deg, smoothing, max_jump_deg):
        if self.filtered_yaw_deg is None:
            self.filtered_yaw_deg = raw_yaw_deg
            return self.filtered_yaw_deg, False

        jump = wrap_degrees(raw_yaw_deg - self.filtered_yaw_deg)
        if abs(jump) > max_jump_deg:
            self.rejected_jump_count += 1
            return self.filtered_yaw_deg, True

        alpha = clamp(smoothing, 0.0, 0.99)
        self.filtered_yaw_deg = wrap_degrees(self.filtered_yaw_deg + (1.0 - alpha) * jump)
        return self.filtered_yaw_deg, False


class MocapReader(Thread):
    """Background VRPN reader for OptiTrack rigid-body pose.

    Reader errors are logged as warnings because mocap is optional in observer
    mode. In XY assist mode, stale/missing mocap prevents assist or trips the
    powered guard rather than letting correction run on old pose data.
    """

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
        try:
            if motioncapture is None:
                raise RuntimeError("motioncapture package is not installed")
            mc = motioncapture.connect("vrpn", {"hostname": self.host})
            print(f"[INFO] Mocap connected, looking for '{self.body_name}'")
            announced = False
            while self._stay_open:
                mc.waitForNextFrame()
                for name, obj in mc.rigidBodies.items():
                    if name != self.body_name:
                        continue
                    if not announced:
                        print(f"[INFO] Found and tracking rigid body: {name}")
                        announced = True
                    pos = obj.position
                    self.state.update((pos[0], pos[1], pos[2]), obj.rotation)
        except Exception as exc:
            self.error = exc
            print(f"[WARN] Mocap reader stopped: {exc}")


class CsvLogger:
    """Writes one wide CSV row per command-loop iteration.

    The field list is intentionally wide and stable. Repeated values are useful:
    each row contains controller state, sent command, Crazyflie telemetry, mocap
    pose, XY assist internals, and stop reason so a single timestamped row is
    enough to reconstruct what happened.
    """

    FIELDNAMES = [
        "wall_time_s", "elapsed_s", "phase", "loop_index", "command_sent",
        "requested_roll_deg", "requested_pitch_deg", "requested_yawrate_deg_s", "requested_thrust_raw",
        "sent_roll_deg", "sent_pitch_deg", "sent_yawrate_deg_s", "sent_thrust_raw",
        "xy_assist_enabled", "xy_assist_active", "xy_assist_reason",
        "xy_assist_target_x", "xy_assist_target_y", "xy_assist_error_x_m", "xy_assist_error_y_m",
        "xy_assist_error_m", "xy_assist_velocity_x_m_s", "xy_assist_velocity_y_m_s",
        "xy_assist_body_error_x_m", "xy_assist_body_error_y_m",
        "xy_assist_body_velocity_x_m_s", "xy_assist_body_velocity_y_m_s",
        "xy_assist_roll_deg", "xy_assist_pitch_deg", "xy_assist_angle_limit_deg",
        "xy_assist_height_scale", "xy_assist_guard_drift_m",
        "xy_assist_raw_yaw_deg", "xy_assist_used_yaw_deg", "xy_assist_yaw_source",
        "xy_assist_yaw_rejected", "xy_assist_yaw_rejected_count",
        "controller_event_count", "controller_last_event_age_s", "controller_last_event_type",
        "controller_last_event_number", "controller_last_event_value",
        "roll_axis_raw", "pitch_axis_raw", "yaw_axis_raw", "thrust_axis_raw",
        "roll_axis_norm_raw", "pitch_axis_norm_raw", "yaw_axis_norm_raw", "thrust_axis_norm_raw",
        "roll_norm_after_deadzone", "pitch_norm_after_deadzone", "yaw_norm_after_deadzone", "thrust_norm",
        "thrust_axis_seen", "button_0", "button_1", "button_2", "button_3", "button_4",
        "button_5", "button_6", "button_7", "button_8", "button_9", "emergency_stop",
        "pm.vbat", "pm.state",
        "stateEstimate.x", "stateEstimate.y", "stateEstimate.z",
        "stateEstimate.vx", "stateEstimate.vy", "stateEstimate.vz",
        "stateEstimate.roll", "stateEstimate.pitch", "stateEstimate.yaw",
        "stabilizer.roll", "stabilizer.pitch", "stabilizer.yaw",
        "gyro.x", "gyro.y", "gyro.z", "acc.x", "acc.y", "acc.z",
        "motor.m1", "motor.m2", "motor.m3", "motor.m4",
        "estimate_packet_count", "estimate_vel_packet_count", "estimate_rp_packet_count",
        "attitude_packet_count", "imu_packet_count", "power_packet_count", "motor_packet_count",
        "estimate_packet_age_s", "estimate_vel_packet_age_s", "estimate_rp_packet_age_s",
        "attitude_packet_age_s", "imu_packet_age_s", "power_packet_age_s", "motor_packet_age_s",
        "mocap_x", "mocap_y", "mocap_z", "mocap_qx", "mocap_qy", "mocap_qz", "mocap_qw",
        "mocap_yaw_deg", "mocap_age_s", "mocap_frame_count", "mocap_fresh",
        "estimate_mocap_error_m", "estimate_mocap_yaw_error_deg",
        "stop_reason",
    ]

    def __init__(self, output_path):
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output_path.open("w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        self._writer.writeheader()
        self.started_at = time.time()

    def write(self, row):
        now = time.time()
        full_row = {"wall_time_s": now, "elapsed_s": now - self.started_at}
        full_row.update(row)
        self._writer.writerow(full_row)
        self._file.flush()

    def close(self):
        self._file.close()


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def apply_deadzone(value):
    """Remove small stick noise, then rescale the remaining travel to +/-1."""
    value = clamp(value, -1.0, 1.0)
    if abs(value) < DEADZONE:
        return 0.0
    sign = 1 if value > 0 else -1
    return sign * (abs(value) - DEADZONE) / (1.0 - DEADZONE)


def slew_toward(current, target, rate_per_s, dt):
    """Rate-limit raw thrust so takeoff does not jump to the stick position."""
    max_step = max(0.0, rate_per_s * dt)
    if target > current:
        return min(target, current + max_step)
    if target < current:
        return max(target, current - max_step)
    return current


def yaw_from_quat_deg(quat):
    siny_cosp = 2.0 * (quat.w * quat.z + quat.x * quat.y)
    cosy_cosp = 1.0 - 2.0 * (quat.y * quat.y + quat.z * quat.z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def wrap_degrees(angle_deg):
    while angle_deg > 180.0:
        angle_deg -= 360.0
    while angle_deg < -180.0:
        angle_deg += 360.0
    return angle_deg


def rotate_world_to_body(world_x, world_y, yaw_rad):
    """Rotate mocap/world XY vectors into the drone body frame for roll/pitch."""
    cos_yaw = math.cos(yaw_rad)
    sin_yaw = math.sin(yaw_rad)
    return (
        cos_yaw * world_x + sin_yaw * world_y,
        -sin_yaw * world_x + cos_yaw * world_y,
    )


def empty_xy_assist_row(args, reason="disabled"):
    """Fill XY assist CSV columns even when assist is inactive or unavailable."""
    return {
        "xy_assist_enabled": int(args.mocap_xy_assist),
        "xy_assist_active": 0,
        "xy_assist_reason": reason,
        "xy_assist_target_x": "",
        "xy_assist_target_y": "",
        "xy_assist_error_x_m": "",
        "xy_assist_error_y_m": "",
        "xy_assist_error_m": "",
        "xy_assist_velocity_x_m_s": "",
        "xy_assist_velocity_y_m_s": "",
        "xy_assist_body_error_x_m": "",
        "xy_assist_body_error_y_m": "",
        "xy_assist_body_velocity_x_m_s": "",
        "xy_assist_body_velocity_y_m_s": "",
        "xy_assist_roll_deg": 0.0,
        "xy_assist_pitch_deg": 0.0,
        "xy_assist_angle_limit_deg": 0.0,
        "xy_assist_height_scale": "",
        "xy_assist_guard_drift_m": "",
        "xy_assist_raw_yaw_deg": "",
        "xy_assist_used_yaw_deg": "",
        "xy_assist_yaw_source": "",
        "xy_assist_yaw_rejected": 0,
        "xy_assist_yaw_rejected_count": "",
    }


def compute_xy_assist(args, mocap_state, velocity_state, yaw_state, assist_target, sent_thrust):
    """Compute optional mocap-based roll/pitch correction.

    This is not autonomous position control: thrust and yawrate still come from
    the Logitech controller. The assist only adds a small PD correction to the
    manual roll/pitch setpoint to oppose horizontal drift from the locked mocap
    target. The function also returns a detailed CSV row showing why assist was
    inactive, what yaw was used, body-frame errors, velocity, angle limit, and
    final correction.
    """
    if not args.mocap_xy_assist:
        return 0.0, 0.0, empty_xy_assist_row(args)
    if args.no_mocap:
        return 0.0, 0.0, empty_xy_assist_row(args, "mocap_disabled")
    if assist_target is None:
        return 0.0, 0.0, empty_xy_assist_row(args, "no_target")

    position, quat, last_update, frame_count = mocap_state.snapshot()
    if position is None or quat is None:
        return 0.0, 0.0, empty_xy_assist_row(args, "no_mocap_pose")

    now = time.time()
    mocap_age = now - last_update if last_update else float("inf")
    # Thrust threshold is the main gate that keeps assist out of props-off and
    # very-low-thrust phases. If set too low, assist can tilt the vehicle while
    # it is still touching the floor and cause ground skid before true liftoff.
    if sent_thrust < args.mocap_xy_assist_min_thrust:
        row = empty_xy_assist_row(args, "below_min_thrust")
        row["xy_assist_target_x"] = assist_target[0]
        row["xy_assist_target_y"] = assist_target[1]
        return 0.0, 0.0, row
    if mocap_age > args.mocap_xy_assist_stale_timeout:
        row = empty_xy_assist_row(args, "mocap_stale")
        row["xy_assist_target_x"] = assist_target[0]
        row["xy_assist_target_y"] = assist_target[1]
        return 0.0, 0.0, row

    vx, vy = velocity_state.update(position, last_update, frame_count, args.mocap_xy_assist_velocity_smoothing)
    error_x = assist_target[0] - position[0]
    error_y = assist_target[1] - position[1]
    error_m = math.hypot(error_x, error_y)
    # Yaw only affects the coordinate transform for assist. During sign tests,
    # use --mocap-xy-assist-fixed-yaw-deg to remove mocap yaw spikes from the
    # experiment. body_yaw_offset is applied after fixed/filtered yaw.
    raw_yaw_deg = yaw_from_quat_deg(quat)
    yaw_rejected = False
    if args.mocap_xy_assist_fixed_yaw_deg is not None:
        assist_yaw_deg = args.mocap_xy_assist_fixed_yaw_deg
        yaw_source = "fixed"
    else:
        assist_yaw_deg, yaw_rejected = yaw_state.update(
            raw_yaw_deg,
            args.mocap_xy_assist_yaw_smoothing,
            args.mocap_xy_assist_max_yaw_jump_deg,
        )
        yaw_source = "filtered_mocap"
    used_yaw_deg = assist_yaw_deg + args.mocap_xy_assist_body_yaw_offset_deg
    yaw_rad = math.radians(used_yaw_deg)
    body_error_x, body_error_y = rotate_world_to_body(error_x, error_y, yaw_rad)
    body_velocity_x, body_velocity_y = rotate_world_to_body(vx, vy, yaw_rad)

    # Ramp authority with height so early corrections are gentler. The minimum
    # active angle can still force a nonzero correction near the floor, so tune
    # min_thrust and min_active_angle together.
    height_above_target = max(0.0, position[2] - assist_target[2]) if len(assist_target) > 2 else 0.0
    if args.mocap_xy_assist_full_height <= 0.0:
        height_scale = 1.0
    else:
        height_scale = clamp(height_above_target / args.mocap_xy_assist_full_height, 0.0, 1.0)
    angle_limit = args.mocap_xy_assist_max_angle_deg * height_scale
    if sent_thrust >= args.mocap_xy_assist_min_thrust:
        angle_limit = max(angle_limit, args.mocap_xy_assist_min_active_angle_deg)
    angle_limit = min(angle_limit, args.mocap_xy_assist_max_angle_deg)

    # PD in body axes: position error pulls back toward target, velocity damps
    # motion away/toward it. Signs convert body X/Y correction into Crazyflie
    # pitch/roll convention and are intentionally CLI-tunable.
    correction_x = args.mocap_xy_assist_kp * body_error_x - args.mocap_xy_assist_kd * body_velocity_x
    correction_y = args.mocap_xy_assist_kp * body_error_y - args.mocap_xy_assist_kd * body_velocity_y
    pitch = clamp(args.mocap_xy_assist_pitch_sign * correction_x, -angle_limit, angle_limit)
    roll = clamp(args.mocap_xy_assist_roll_sign * correction_y, -angle_limit, angle_limit)

    row = {
        "xy_assist_enabled": 1,
        "xy_assist_active": int(angle_limit > 0.0),
        "xy_assist_reason": "active" if angle_limit > 0.0 else "waiting_for_height",
        "xy_assist_target_x": assist_target[0],
        "xy_assist_target_y": assist_target[1],
        "xy_assist_error_x_m": error_x,
        "xy_assist_error_y_m": error_y,
        "xy_assist_error_m": error_m,
        "xy_assist_velocity_x_m_s": vx,
        "xy_assist_velocity_y_m_s": vy,
        "xy_assist_body_error_x_m": body_error_x,
        "xy_assist_body_error_y_m": body_error_y,
        "xy_assist_body_velocity_x_m_s": body_velocity_x,
        "xy_assist_body_velocity_y_m_s": body_velocity_y,
        "xy_assist_roll_deg": roll,
        "xy_assist_pitch_deg": pitch,
        "xy_assist_angle_limit_deg": angle_limit,
        "xy_assist_height_scale": height_scale,
        "xy_assist_guard_drift_m": error_m,
        "xy_assist_raw_yaw_deg": raw_yaw_deg,
        "xy_assist_used_yaw_deg": used_yaw_deg,
        "xy_assist_yaw_source": yaw_source,
        "xy_assist_yaw_rejected": int(yaw_rejected),
        "xy_assist_yaw_rejected_count": yaw_state.rejected_jump_count,
    }
    return roll, pitch, row


def check_xy_assist_guard(args, xy_assist_row, sent_thrust):
    """Return a stop reason if powered XY assist no longer has safe inputs."""
    if not args.mocap_xy_assist or sent_thrust < args.mocap_xy_assist_min_thrust:
        return None
    reason = xy_assist_row.get("xy_assist_reason")
    if reason == "mocap_stale":
        return "mocap XY assist guard: mocap stale while powered"
    drift = xy_assist_row.get("xy_assist_guard_drift_m")
    if drift != "" and drift is not None and drift > args.mocap_xy_assist_max_drift:
        return (
            "mocap XY assist guard: horizontal drift "
            f"{drift:.3f}m exceeded {args.mocap_xy_assist_max_drift:.3f}m"
        )
    return None


def mapping_from_cfclient_input_config(path):
    """Read a cfclient input JSON so this script can match cfclient controls."""
    config_path = Path(path).expanduser()
    with config_path.open() as config_file:
        config = json.load(config_file)
    axes = config["inputconfig"]["inputdevice"].get("axis", [])
    by_key = {entry["key"]: entry for entry in axes}
    missing = [key for key in ("roll", "pitch", "yaw", "thrust") if key not in by_key]
    if missing:
        raise ValueError(f"Input config {config_path} is missing axes: {', '.join(missing)}")
    return ControllerMapping(
        roll_axis=int(by_key["roll"]["id"]),
        pitch_axis=int(by_key["pitch"]["id"]),
        yaw_axis=int(by_key["yaw"]["id"]),
        thrust_axis=int(by_key["thrust"]["id"]),
        roll_scale=float(by_key["roll"].get("scale", 1.0)),
        pitch_scale=float(by_key["pitch"].get("scale", 1.0)),
        yaw_scale=float(by_key["yaw"].get("scale", 1.0)),
        thrust_scale=float(by_key["thrust"].get("scale", 1.0)),
        source=str(config_path),
    )


def mapping_from_args(args):
    if args.cfclient_input_config:
        return mapping_from_cfclient_input_config(args.cfclient_input_config)
    return ControllerMapping(emergency_button=args.emergency_button)


def print_controller_name(js_file):
    try:
        device_name_bytes = bytearray(64)
        fcntl.ioctl(js_file.fileno(), 0x80006A13, device_name_bytes)
        device_name = device_name_bytes.decode("utf-8").rstrip("\x00")
        print(f"[INFO] Controller device name: {device_name}")
    except OSError:
        pass


def find_controller_device(preferred):
    """Find the joystick device to open with the Linux js API.

    Prefer stable /dev/input/by-id symlinks because /dev/input/js0/js1 can swap
    after reconnects. Exclude '*event-joystick' because those are evdev devices
    with a different packet format than JS_EVENT_FMT.
    """
    if preferred:
        if os.path.exists(preferred):
            return preferred
        raise FileNotFoundError(f"Requested joystick device does not exist: {preferred}")

    by_id = Path("/dev/input/by-id")
    if by_id.exists():
        joystick_links = sorted(
            link for link in by_id.glob("*joystick")
            if not link.name.endswith("event-joystick")
        )
        for link in joystick_links:
            if "logitech" in link.name.lower():
                return str(link)
        if joystick_links:
            return str(joystick_links[0])

    for index in range(10):
        candidate = f"/dev/input/js{index}"
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError("No joystick device found. Tried /dev/input/by-id/*joystick and /dev/input/js0..js9.")


def make_log_config(name, variables, period_ms, telemetry_state):
    """Create one Crazyflie log block and route packets into TelemetryState."""
    logconf = LogConfig(name=name, period_in_ms=period_ms)
    for variable, var_type in variables:
        logconf.add_variable(variable, var_type)

    def on_data(timestamp, data, logconf):
        del timestamp
        telemetry_state.update(logconf.name, data)

    def on_error(logconf, msg):
        print(f"[WARN] Logger error from {logconf.name}: {msg}")

    logconf.data_received_cb.add_callback(on_data)
    logconf.error_cb.add_callback(on_error)
    return logconf


def setup_telemetry(cf, telemetry_state):
    """Start all requested Crazyflie log blocks.

    Blocks are split because the Crazyflie log subsystem limits block size.
    Missing variables or overloaded blocks are warned about but do not stop the
    manual controller; the CSV packet counts/ages show which streams arrived.
    """
    configs = [
        make_log_config("estimate", [("stateEstimate.x", "float"), ("stateEstimate.y", "float"), ("stateEstimate.z", "float"), ("stateEstimate.yaw", "float")], LOG_PERIOD_MS, telemetry_state),
        make_log_config("estimate_vel", [("stateEstimate.vx", "float"), ("stateEstimate.vy", "float"), ("stateEstimate.vz", "float")], LOG_PERIOD_MS, telemetry_state),
        make_log_config("estimate_rp", [("stateEstimate.roll", "float"), ("stateEstimate.pitch", "float")], LOG_PERIOD_MS, telemetry_state),
        make_log_config("attitude", [("stabilizer.roll", "float"), ("stabilizer.pitch", "float"), ("stabilizer.yaw", "float")], LOG_PERIOD_MS, telemetry_state),
        make_log_config("imu", [("gyro.x", "float"), ("gyro.y", "float"), ("gyro.z", "float"), ("acc.x", "float"), ("acc.y", "float"), ("acc.z", "float")], LOG_PERIOD_MS, telemetry_state),
        make_log_config("power", [("pm.vbat", "float"), ("pm.state", "uint8_t")], LOG_PERIOD_MS, telemetry_state),
        make_log_config("motor", [("motor.m1", "uint16_t"), ("motor.m2", "uint16_t"), ("motor.m3", "uint16_t"), ("motor.m4", "uint16_t")], LOG_PERIOD_MS, telemetry_state),
    ]
    started_configs = []
    for config in configs:
        try:
            cf.log.add_config(config)
            config.start()
            started_configs.append(config)
        except Exception as exc:
            print(f"[WARN] Could not start log block {config.name}: {exc}")
    return started_configs


def telemetry_meta_fields(last_packet_time_by_group, packet_count_by_group):
    now = time.time()
    row = {}
    for group in ("estimate", "estimate_vel", "estimate_rp", "attitude", "imu", "power", "motor"):
        row[f"{group}_packet_count"] = packet_count_by_group.get(group, 0)
        last_packet_time = last_packet_time_by_group.get(group, 0.0)
        row[f"{group}_packet_age_s"] = now - last_packet_time if last_packet_time else ""
    return row


def mocap_fields(mocap_state, telemetry_values):
    """Build CSV mocap columns and estimator-vs-mocap comparison fields."""
    position, quat, last_update, frame_count = mocap_state.snapshot()
    if position is None or quat is None:
        return {
            "mocap_x": "", "mocap_y": "", "mocap_z": "", "mocap_qx": "", "mocap_qy": "",
            "mocap_qz": "", "mocap_qw": "", "mocap_yaw_deg": "", "mocap_age_s": "",
            "mocap_frame_count": frame_count, "mocap_fresh": 0,
            "estimate_mocap_error_m": "", "estimate_mocap_yaw_error_deg": "",
        }

    now = time.time()
    mocap_yaw = yaw_from_quat_deg(quat)
    row = {
        "mocap_x": position[0], "mocap_y": position[1], "mocap_z": position[2],
        "mocap_qx": quat.x, "mocap_qy": quat.y, "mocap_qz": quat.z, "mocap_qw": quat.w,
        "mocap_yaw_deg": mocap_yaw,
        "mocap_age_s": now - last_update,
        "mocap_frame_count": frame_count,
        "mocap_fresh": int(now - last_update <= MOCAP_STALE_TIMEOUT_S),
        "estimate_mocap_error_m": "",
        "estimate_mocap_yaw_error_deg": "",
    }
    estimate_position = (
        telemetry_values.get("stateEstimate.x"),
        telemetry_values.get("stateEstimate.y"),
        telemetry_values.get("stateEstimate.z"),
    )
    if all(value is not None for value in estimate_position):
        row["estimate_mocap_error_m"] = math.dist(position, estimate_position)
    estimate_yaw = telemetry_values.get("stateEstimate.yaw")
    if estimate_yaw is not None:
        row["estimate_mocap_yaw_error_deg"] = wrap_degrees(estimate_yaw - mocap_yaw)
    return row


def write_log_row(logger, phase, loop_index, command_sent, controller_row, telemetry_state, mocap_state, sent, xy_assist_row=None, stop_reason=""):
    """Merge controller, command, telemetry, mocap, and assist data into CSV."""
    telemetry_values, telemetry_times, telemetry_counts = telemetry_state.snapshot()
    row = {
        "phase": phase,
        "loop_index": loop_index,
        "command_sent": int(command_sent),
        "sent_roll_deg": sent[0],
        "sent_pitch_deg": sent[1],
        "sent_yawrate_deg_s": sent[2],
        "sent_thrust_raw": int(sent[3]),
    }
    row.update(xy_assist_row or {})
    row.update(controller_row)
    row.update(telemetry_values)
    row.update(telemetry_meta_fields(telemetry_times, telemetry_counts))
    row.update(mocap_fields(mocap_state, telemetry_values))
    row["stop_reason"] = stop_reason
    logger.write(row)


def wait_for_low_thrust(controller_state, args, label):
    """Block until the throttle axis has been seen and is near zero.

    This prevents connecting or arming while the stick is high or while the
    script is accidentally reading the wrong joystick device.
    """
    print(f"[INFO] {label}: move the right/thrust stick fully down.")
    while True:
        state = controller_state.snapshot(args)
        if state["emergency_stop"]:
            raise KeyboardInterrupt
        if state["thrust_axis_seen"] and state["thrust_norm"] <= 0.05:
            print(f"[INFO] {label}: thrust stick is low.")
            return
        time.sleep(0.25)


def supervisor_state_text(cf):
    try:
        states = cf.supervisor.read_state_list()
        if states:
            return ", ".join(states)
        return "no supervisor state bits set"
    except Exception as exc:
        return f"unavailable ({exc})"


def send_zero_thrust_packets(cf, count=10, include_stop=False):
    """Send repeated zero-thrust packets because one lost radio packet is not enough."""
    for _ in range(count):
        try:
            cf.commander.send_setpoint(0.0, 0.0, 0.0, 0)
        except Exception:
            pass
        if include_stop:
            try:
                cf.commander.send_stop_setpoint()
            except Exception:
                pass
        time.sleep(EMERGENCY_ZERO_THRUST_PERIOD_S)


def arm_for_manual_flight(cf):
    """Request supervisor arming for low-level manual setpoint flight."""
    print(f"[INFO] Supervisor before arm: {supervisor_state_text(cf)}")
    send_zero_thrust_packets(cf, count=20, include_stop=False)
    try:
        can_arm = cf.supervisor.can_be_armed
        print(f"[INFO] Supervisor can_be_armed={int(can_arm)}")
    except Exception as exc:
        print(f"[WARN] Could not read can_be_armed: {exc}")

    print("[INFO] Sending supervisor arm request...")
    cf.supervisor.send_arming_request(True)
    send_zero_thrust_packets(cf, count=20, include_stop=False)

    for _ in range(10):
        try:
            if cf.supervisor.is_armed:
                print(f"[INFO] Supervisor after arm: {supervisor_state_text(cf)}")
                print("[INFO] Crazyflie reports armed.")
                return
        except Exception:
            break
        time.sleep(0.1)

    state = supervisor_state_text(cf)
    print(f"[WARN] Crazyflie did not report armed after request. Supervisor: {state}")
    print("[WARN] Continuing only if firmware accepts manual setpoints/auto-arm; keep thrust low and be ready to abort.")


def disarm(cf):
    try:
        cf.supervisor.send_arming_request(False)
    except Exception:
        try:
            cf.platform.send_arming_request(False)
        except Exception:
            pass


def send_emergency_stop(cf):
    """Best-effort powered stop used for Ctrl+C, guard trips, and errors."""
    print("[SAFETY] Sending repeated zero thrust, stop setpoint, and disarm.")
    send_zero_thrust_packets(cf, count=EMERGENCY_ZERO_THRUST_PACKETS, include_stop=True)
    disarm(cf)


def print_battery_warning(telemetry_state):
    values, _, _ = telemetry_state.snapshot()
    battery_v = values.get("pm.vbat")
    if battery_v is None:
        print("[WARN] Battery voltage has not arrived yet.")
        return
    print(f"[INFO] Battery: {battery_v:.2f} V")
    if battery_v < 3.70:
        print("[WARN] Battery is low; use a fresh pack if possible.")


def is_radio_busy_error(exc):
    message = str(exc)
    return "Resource busy" in message or "Errno 16" in message


def run_loop(cf, args, logger, controller_reader, controller_state, telemetry_state, mocap_state):
    """Main 50 Hz command/log loop.

    Safety invariants in this loop:
    - props-off always sends zero thrust and never arms in main().
    - controller reader errors stop the run instead of holding stale inputs.
    - Start button and Ctrl+C lead to repeated zero-thrust/stop/disarm in finally.
    - XY assist guard stops powered flight on stale mocap or excessive drift.
    """
    started_at = time.time()
    last_print = 0.0
    last_loop_time = started_at
    loop_index = 0
    phase = "props_off" if args.props_off else "manual_flight"
    sent_thrust = 0.0
    stop_reason = "operator_stop_or_duration"
    assist_target = None
    mocap_velocity_state = MocapVelocityState()
    assist_yaw_state = AssistYawState()

    print("[INFO] Manual flight controller + logger is running.")
    print("[INFO] Press controller Start or Ctrl+C to stop.")

    while True:
        now = time.time()
        # Powered safety check: if the joystick thread dies after arming, do not
        # keep sending the last known command. Log the failure row and stop.
        if controller_reader.error is not None:
            stop_reason = f"controller_reader_error: {controller_reader.error}"
            write_log_row(
                logger,
                "controller-error",
                loop_index,
                False,
                controller_state.snapshot(args),
                telemetry_state,
                mocap_state,
                (0, 0, 0, 0),
                empty_xy_assist_row(args, "controller_error"),
                stop_reason=stop_reason,
            )
            raise RuntimeError(stop_reason)

        if args.duration and now - started_at >= args.duration:
            print("[INFO] Requested duration reached.")
            stop_reason = "duration_reached"
            break

        control = controller_state.snapshot(args)
        if control["emergency_stop"]:
            print("[SAFETY] Controller Start button pressed.")
            stop_reason = "controller_start_button"
            break

        dt = max(0.0, now - last_loop_time)
        last_loop_time = now
        # In normal mode, the Logitech stick chooses target thrust. The slew
        # limiter makes the sent thrust ramp gradually. In props-off mode this
        # path is hard-forced to zero every loop.
        target_thrust = 0 if args.props_off else control["requested_thrust_raw"]
        sent_thrust = 0.0 if args.props_off else slew_toward(sent_thrust, target_thrust, args.thrust_slew_raw_per_s, dt)
        # XY assist holds the initial mocap X/Y target. It is locked once, from
        # a fresh pose near the start of the run; it is not a moving trajectory.
        if args.mocap_xy_assist and assist_target is None:
            position, _, last_update, _ = mocap_state.snapshot()
            if position is not None and time.time() - last_update <= args.mocap_xy_assist_stale_timeout:
                assist_target = position
                print(
                    "[INFO] Mocap XY assist target locked: "
                    f"x={assist_target[0]:+.3f}, y={assist_target[1]:+.3f}, z={assist_target[2]:+.3f}"
                )

        assist_roll, assist_pitch, xy_assist_row = compute_xy_assist(
            args, mocap_state, mocap_velocity_state, assist_yaw_state, assist_target, sent_thrust
        )
        guard_reason = check_xy_assist_guard(args, xy_assist_row, sent_thrust)
        if guard_reason is not None:
            print(f"[SAFETY] {guard_reason}")
            write_log_row(
                logger,
                "xy-assist-guard",
                loop_index,
                False,
                control,
                telemetry_state,
                mocap_state,
                (0, 0, 0, 0),
                xy_assist_row,
                stop_reason=guard_reason,
            )
            raise RuntimeError(guard_reason)

        # Manual roll/pitch remain available. XY assist adds on top and then the
        # final command is clamped to the manual max angle limits.
        sent_roll = control["requested_roll_deg"]
        sent_pitch = control["requested_pitch_deg"]
        if args.mocap_xy_assist and xy_assist_row["xy_assist_active"]:
            sent_roll = clamp(control["requested_roll_deg"] + assist_roll, -args.max_roll_deg, args.max_roll_deg)
            sent_pitch = clamp(control["requested_pitch_deg"] + assist_pitch, -args.max_pitch_deg, args.max_pitch_deg)

        sent = (
            sent_roll,
            sent_pitch,
            control["requested_yawrate_deg_s"],
            int(sent_thrust),
        )
        # This is the only flight command sent during the loop: low-level manual
        # roll, pitch, yawrate, thrust. No HLC or position setpoints are used.
        cf.commander.send_setpoint(sent[0], sent[1], sent[2], sent[3])

        write_log_row(logger, phase, loop_index, True, control, telemetry_state, mocap_state, sent, xy_assist_row)

        if now - last_print >= PRINT_PERIOD_S:
            values, _, counts = telemetry_state.snapshot()
            position, _, mocap_time, mocap_frames = mocap_state.snapshot()
            mocap_age = now - mocap_time if mocap_time else float("nan")
            mocap_text = f"mocap_age={mocap_age:.2f}s frames={mocap_frames}" if position else "mocap=no-pose"
            print(
                f"[{phase}] sent thrust={sent[3]:5d}/{target_thrust:5d} "
                f"r/p/y={sent[0]:+5.1f}/{sent[1]:+5.1f}/{sent[2]:+6.1f} "
                f"assist={xy_assist_row.get('xy_assist_reason', 'off')} "
                f"z={values.get('stateEstimate.z', float('nan')):+.2f} "
                f"vbat={values.get('pm.vbat', float('nan')):.2f} "
                f"packets={sum(counts.values())} {mocap_text}"
            )
            last_print = now

        loop_index += 1
        time.sleep(CONTROL_PERIOD_S)

    write_log_row(
        logger,
        "stop",
        loop_index,
        False,
        controller_state.snapshot(args),
        telemetry_state,
        mocap_state,
        (0, 0, 0, 0),
        empty_xy_assist_row(args, "stop"),
        stop_reason=stop_reason,
    )


def output_path_from_args(args):
    if args.output:
        return Path(args.output)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(args.output_dir) / f"controller-drone-observer-{timestamp}.csv"


def parse_args():
    """CLI flags are tuning knobs; defaults keep behavior manual and conservative."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--controller", default=DEFAULT_CONTROLLER_DEVICE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output")
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--props-off", action="store_true")
    parser.add_argument("--max-roll-deg", type=float, default=DEFAULT_MAX_ROLL_DEG)
    parser.add_argument("--max-pitch-deg", type=float, default=DEFAULT_MAX_PITCH_DEG)
    parser.add_argument("--max-yawrate-deg-s", type=float, default=DEFAULT_MAX_YAWRATE_DEG_S)
    parser.add_argument("--max-thrust", type=int, default=DEFAULT_MAX_THRUST)
    parser.add_argument("--thrust-slew-raw-per-s", type=float, default=DEFAULT_THRUST_SLEW_RAW_PER_S)
    parser.add_argument(
        "--cfclient-input-config",
        default=None,
        help="Path to a cfclient input JSON mapping, for example ~/.config/cfclient/input/PS4_shoulder_btns_yaw.json.",
    )
    parser.add_argument("--emergency-button", type=int, default=9, help="Joystick button number used as emergency stop.")
    parser.add_argument("--no-mocap", action="store_true")
    parser.add_argument("--mocap-host", default=DEFAULT_MOCAP_HOST)
    parser.add_argument("--rigid-body", default=DEFAULT_RIGID_BODY_NAME)
    parser.add_argument(
        "--mocap-xy-assist",
        action="store_true",
        help="Use mocap PD correction for roll/pitch while Logitech still controls thrust and yawrate.",
    )
    parser.add_argument("--mocap-xy-assist-kp", type=float, default=DEFAULT_XY_ASSIST_KP)
    parser.add_argument("--mocap-xy-assist-kd", type=float, default=DEFAULT_XY_ASSIST_KD)
    parser.add_argument("--mocap-xy-assist-max-angle-deg", type=float, default=DEFAULT_XY_ASSIST_MAX_ANGLE_DEG)
    parser.add_argument("--mocap-xy-assist-full-height", type=float, default=DEFAULT_XY_ASSIST_FULL_HEIGHT_M)
    parser.add_argument("--mocap-xy-assist-min-active-angle-deg", type=float, default=DEFAULT_XY_ASSIST_MIN_ACTIVE_ANGLE_DEG)
    parser.add_argument("--mocap-xy-assist-min-thrust", type=int, default=DEFAULT_XY_ASSIST_MIN_THRUST)
    parser.add_argument("--mocap-xy-assist-max-drift", type=float, default=DEFAULT_XY_ASSIST_MAX_DRIFT_M)
    parser.add_argument("--mocap-xy-assist-body-yaw-offset-deg", type=float, default=DEFAULT_XY_ASSIST_BODY_YAW_OFFSET_DEG)
    parser.add_argument("--mocap-xy-assist-fixed-yaw-deg", type=float, default=None)
    parser.add_argument("--mocap-xy-assist-yaw-smoothing", type=float, default=DEFAULT_XY_ASSIST_YAW_SMOOTHING)
    parser.add_argument("--mocap-xy-assist-max-yaw-jump-deg", type=float, default=DEFAULT_XY_ASSIST_MAX_YAW_JUMP_DEG)
    parser.add_argument("--mocap-xy-assist-roll-sign", type=float, choices=(-1.0, 1.0), default=DEFAULT_XY_ASSIST_ROLL_SIGN)
    parser.add_argument("--mocap-xy-assist-pitch-sign", type=float, choices=(-1.0, 1.0), default=DEFAULT_XY_ASSIST_PITCH_SIGN)
    parser.add_argument("--mocap-xy-assist-velocity-smoothing", type=float, default=0.7)
    parser.add_argument("--mocap-xy-assist-stale-timeout", type=float, default=MOCAP_STALE_TIMEOUT_S)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.mocap_xy_assist and args.no_mocap:
        raise RuntimeError("--mocap-xy-assist requires mocap; remove --no-mocap")
    if args.mocap_xy_assist and args.props_off:
        print("[WARN] --mocap-xy-assist has no effect in --props-off mode because thrust is forced to zero.")
    if args.mocap_xy_assist_max_angle_deg < 0.0:
        raise RuntimeError("--mocap-xy-assist-max-angle-deg must be non-negative")
    if args.mocap_xy_assist_min_active_angle_deg < 0.0:
        raise RuntimeError("--mocap-xy-assist-min-active-angle-deg must be non-negative")
    if args.mocap_xy_assist_min_active_angle_deg > args.mocap_xy_assist_max_angle_deg:
        raise RuntimeError("--mocap-xy-assist-min-active-angle-deg must be <= --mocap-xy-assist-max-angle-deg")
    if args.mocap_xy_assist_min_thrust < 0:
        raise RuntimeError("--mocap-xy-assist-min-thrust must be non-negative")
    if args.mocap_xy_assist_max_drift <= 0.0:
        raise RuntimeError("--mocap-xy-assist-max-drift must be positive")
    if args.mocap_xy_assist_max_yaw_jump_deg <= 0.0:
        raise RuntimeError("--mocap-xy-assist-max-yaw-jump-deg must be positive")
    controller_mapping = mapping_from_args(args)
    controller_state = ControllerState(controller_mapping)
    telemetry_state = TelemetryState()
    mocap_state = MocapState()
    controller_reader = ControllerReader(find_controller_device(args.controller), controller_state)
    mocap_reader = None if args.no_mocap else MocapReader(args.mocap_host, args.rigid_body, mocap_state)
    logger = CsvLogger(output_path_from_args(args))
    logconfigs = []
    cf = None

    print("=" * 72)
    print("MANUAL FLIGHT CONTROLLER + OBSERVER LOGGER")
    print("=" * 72)
    print(f"URI: {args.uri}")
    print(f"Controller: {controller_reader.device_path}")
    print(
        "Mapping: "
        f"roll axis {controller_mapping.roll_axis} scale {controller_mapping.roll_scale:+.1f}, "
        f"pitch axis {controller_mapping.pitch_axis} scale {controller_mapping.pitch_scale:+.1f}, "
        f"yaw axis {controller_mapping.yaw_axis} scale {controller_mapping.yaw_scale:+.1f}, "
        f"thrust axis {controller_mapping.thrust_axis} scale {controller_mapping.thrust_scale:+.1f}; "
        f"source={controller_mapping.source}"
    )
    print(f"Mocap: {'disabled' if args.no_mocap else args.rigid_body + '@' + args.mocap_host}")
    print(f"Limits: roll={args.max_roll_deg:.1f}deg pitch={args.max_pitch_deg:.1f}deg yawrate={args.max_yawrate_deg_s:.1f}deg/s thrust_cap={args.max_thrust}")
    print(f"Thrust slew: {args.thrust_slew_raw_per_s:.0f} raw/s")
    if args.mocap_xy_assist:
        print(
            "Mocap XY assist: ENABLED, "
            f"kp={args.mocap_xy_assist_kp:.2f}, kd={args.mocap_xy_assist_kd:.2f}, "
            f"max_angle={args.mocap_xy_assist_max_angle_deg:.1f}deg, "
            f"min_active_angle={args.mocap_xy_assist_min_active_angle_deg:.1f}deg, "
            f"min_thrust={args.mocap_xy_assist_min_thrust}, "
            f"max_drift={args.mocap_xy_assist_max_drift:.2f}m, "
            f"body_yaw_offset={args.mocap_xy_assist_body_yaw_offset_deg:+.1f}deg, "
            f"fixed_yaw={args.mocap_xy_assist_fixed_yaw_deg}, "
            f"yaw_smoothing={args.mocap_xy_assist_yaw_smoothing:.2f}, "
            f"max_yaw_jump={args.mocap_xy_assist_max_yaw_jump_deg:.1f}deg, "
            f"roll_sign={args.mocap_xy_assist_roll_sign:+.0f}, "
            f"pitch_sign={args.mocap_xy_assist_pitch_sign:+.0f}"
        )
    else:
        print("Mocap XY assist: disabled")
    print(f"Output: {logger.output_path}")
    if args.props_off:
        print("[MODE] Props-off: this will never arm and sent thrust is forced to zero.")
    else:
        print("[MODE] Normal: this is a MANUAL FLIGHT CONTROLLER + LOGGER, not logger-only.")
    print("[INFO] No HLC, no estimator reset/config, no autonomous takeoff/landing/go_to/replay.")
    if args.mocap_xy_assist:
        print("[INFO] XY assist is low-level mocap drift correction; thrust remains manual from Logitech.")
    print("=" * 72)

    try:
        controller_reader.start()
        if mocap_reader is not None:
            mocap_reader.start()
        time.sleep(0.3)
        if controller_reader.error is not None:
            raise RuntimeError(f"Controller reader failed: {controller_reader.error}")
        wait_for_low_thrust(controller_state, args, "Before connecting")

        input("Press ENTER to connect Crazyflie, or Ctrl+C to abort...")
        cflib.crtp.init_drivers()
        with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
            cf = scf.cf
            print("[INFO] Crazyflie connected.")
            logconfigs = setup_telemetry(cf, telemetry_state)
            time.sleep(0.8)
            print_battery_warning(telemetry_state)

            if args.props_off:
                print("[INFO] Props-off mode: not arming.")
            else:
                wait_for_low_thrust(controller_state, args, "Immediately before arming")
                input("Press ENTER to ARM for MANUAL flight logging, or Ctrl+C to abort...")
                arm_for_manual_flight(cf)

            run_loop(cf, args, logger, controller_reader, controller_state, telemetry_state, mocap_state)
    except KeyboardInterrupt:
        print("\n[SAFETY] Operator abort.")
    except Exception as exc:
        if is_radio_busy_error(exc):
            print("\n[SAFETY] Crazyradio is busy; could not open the radio link.")
            print("[HINT] Close cfclient or any other Crazyflie script, then unplug/replug the Crazyradio if it stays busy.")
        else:
            print(f"\n[SAFETY] Error: {exc}")
        error_row = {"phase": "error", "stop_reason": str(exc)}
        error_row.update(empty_xy_assist_row(args, "error"))
        logger.write(error_row)
    finally:
        if cf is not None:
            send_emergency_stop(cf)
        for config in logconfigs:
            try:
                config.stop()
            except Exception:
                pass
        controller_reader.close()
        if mocap_reader is not None:
            mocap_reader.close()
        logger.close()
        print(f"[DONE] Wrote log: {logger.output_path}")


if __name__ == "__main__":
    main()
