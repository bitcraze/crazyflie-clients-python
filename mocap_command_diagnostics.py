#!/usr/bin/env python3
"""
Diagnostic Logitech/Crazyflie/mocap logger.

This script is intentionally diagnostic only. It has no replay mode, no High
Level Commander usage, no autonomous takeoff, and no autonomous landing.

Modes:

    python3 mocap_command_diagnostics.py validate
    python3 mocap_command_diagnostics.py controller-log --duration 20
    python3 mocap_command_diagnostics.py manual-log --props-off --duration 20
    python3 mocap_command_diagnostics.py manual-log --duration 60

manual-log sends only low-level manual commander setpoints:
roll, pitch, yawrate, thrust. controller-log never opens the Crazyflie link.
props-off manual-log may stream zero-thrust setpoints for radio/telemetry
diagnostics, but it must never arm.
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

try:
    import cflib.crtp as crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.platformservice import PLATFORM_COMMAND
    from cflib.crazyflie.platformservice import PLATFORM_REQUEST_ARMING
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    from cflib.crtp.crtpstack import CRTPPacket
    from cflib.crtp.crtpstack import CRTPPort
except ImportError as exc:
    crtp = None
    Crazyflie = None
    LogConfig = None
    PLATFORM_COMMAND = None
    PLATFORM_REQUEST_ARMING = None
    SyncCrazyflie = None
    CRTPPacket = None
    CRTPPort = None
    CFLIB_IMPORT_ERROR = exc
else:
    CFLIB_IMPORT_ERROR = None

try:
    import motioncapture
except ImportError:
    motioncapture = None


DEFAULT_URI = "radio://0/80/2M"
DEFAULT_CONTROLLER_DEVICE = None
DEFAULT_MOCAP_HOST = "192.168.1.42:3883"
DEFAULT_RIGID_BODY_NAME = "crazyflie_21"
DEFAULT_OUTPUT_DIR = "flight_logs"

ROLL_AXIS = 0
PITCH_AXIS = 1
YAW_AXIS = 2
THRUST_AXIS = 3

DEFAULT_MAX_ROLL_DEG = 12.0
DEFAULT_MAX_PITCH_DEG = 12.0
DEFAULT_MAX_YAWRATE_DEG_S = 60.0
DEFAULT_MAX_THRUST = 52000
DEFAULT_THRUST_SLEW_RAW_PER_S = 6000.0
MIN_THRUST = 0
DEADZONE = 0.10

CONTROL_PERIOD_S = 0.02
PRINT_PERIOD_S = 1.0
LOG_PERIOD_MS = 100
MOCAP_STALE_TIMEOUT_S = 0.30
EMERGENCY_ZERO_THRUST_PACKETS = 40
EMERGENCY_ZERO_THRUST_PERIOD_S = 0.01

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
    roll_axis: int = ROLL_AXIS
    pitch_axis: int = PITCH_AXIS
    yaw_axis: int = YAW_AXIS
    thrust_axis: int = THRUST_AXIS
    roll_scale: float = 1.0
    pitch_scale: float = -1.0
    yaw_scale: float = 1.0
    thrust_scale: float = -1.0
    deadman_button: int = 4
    emergency_button: int = 9
    source: str = "built-in Logitech Dual Action / cfclient-style mapping"


class SafetyEvents:
    def __init__(self):
        self._lock = Lock()
        self.events = []

    def add(self, event_type, detail):
        with self._lock:
            event = {
                "time_s": time.time(),
                "event_type": event_type,
                "detail": detail,
            }
            self.events.append(event)
            print(f"[SAFETY] {event_type}: {detail}")

    def snapshot(self):
        with self._lock:
            if not self.events:
                return {
                    "safety_event_count": 0,
                    "last_safety_event_type": "",
                    "last_safety_event_detail": "",
                    "last_safety_event_age_s": "",
                }
            event = self.events[-1]
            return {
                "safety_event_count": len(self.events),
                "last_safety_event_type": event["event_type"],
                "last_safety_event_detail": event["detail"],
                "last_safety_event_age_s": time.time() - event["time_s"],
            }


class ControllerState:
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
                self.thrust_norm = clamp(thrust_value, 0.0, 1.0)
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
            deadman_pressed = bool(self.buttons.get(self.mapping.deadman_button, 0))
            enabled_thrust = int(requested_thrust) if deadman_pressed else 0
            row = {
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
                "mapped_roll_deg": self.roll_norm * args.max_roll_deg,
                "mapped_pitch_deg": self.pitch_norm * args.max_pitch_deg,
                "mapped_yawrate_deg_s": self.yaw_norm * args.max_yawrate_deg_s,
                "mapped_thrust_raw": int(requested_thrust),
                "enabled_roll_deg": self.roll_norm * args.max_roll_deg if deadman_pressed else 0.0,
                "enabled_pitch_deg": self.pitch_norm * args.max_pitch_deg if deadman_pressed else 0.0,
                "enabled_yawrate_deg_s": self.yaw_norm * args.max_yawrate_deg_s if deadman_pressed else 0.0,
                "enabled_thrust_raw": enabled_thrust,
                "deadman_pressed": int(deadman_pressed),
                "command_enabled": int(deadman_pressed),
                "deadman_button": self.mapping.deadman_button,
                "thrust_axis_seen": int(self.thrust_axis_seen),
                "emergency_stop": int(self.emergency_stop),
            }
            for button in range(10):
                row[f"button_{button}"] = self.buttons.get(button, 0)
            return row


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
            self._js_file = open(self.device_path, "rb")
            fcntl.fcntl(self._js_file.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
            print(f"[INFO] Controller opened: {self.device_path}")
            print_controller_name(self._js_file)
            while self._stay_open:
                readable, _, _ = select.select([self._js_file], [], [], 0.1)
                if not readable:
                    continue
                event_data = self._js_file.read(JS_EVENT_SIZE)
                if not event_data:
                    raise RuntimeError("Joystick disconnected or reached EOF")
                if len(event_data) != JS_EVENT_SIZE:
                    raise RuntimeError(
                        f"Short joystick read: expected {JS_EVENT_SIZE} bytes, got {len(event_data)}"
                    )
                _, value, event_type, number = struct.unpack(JS_EVENT_FMT, event_data)
                event_type &= ~JS_EVENT_INIT
                if event_type == JS_EVENT_AXIS:
                    self.state.update_axis(number, value)
                elif event_type == JS_EVENT_BUTTON:
                    self.state.update_button(number, value)
        except Exception as exc:
            self.error = exc


class TelemetryState:
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
        mc = None
        tracked_body = None
        try:
            if motioncapture is None:
                raise RuntimeError("motioncapture package is not installed")
            mc = motioncapture.connect("vrpn", {"hostname": self.host})
            print(f"[INFO] Mocap connected, looking for '{self.body_name}'")
            announced = False
            while self._stay_open:
                mc.waitForNextFrame()
                for name, tracked_body in mc.rigidBodies.items():
                    if name != self.body_name:
                        continue
                    if not announced:
                        print(f"[INFO] Found and tracking rigid body: {name}")
                        announced = True
                    pos = tracked_body.position
                    self.state.update(
                        (pos[0], pos[1], pos[2]),
                        tracked_body.rotation,
                    )
                tracked_body = None
        except Exception as exc:
            self.error = exc
            print(f"[WARN] Mocap reader stopped: {exc}")
        finally:
            tracked_body = None
            mc = None


class CsvLogger:
    FIELDNAMES = [
        "wall_time_s", "elapsed_s", "mode", "phase", "loop_index",
        "loop_dt_s", "command_rate_hz", "command_sent", "sent_command_count",
        "mapped_roll_deg", "mapped_pitch_deg", "mapped_yawrate_deg_s", "mapped_thrust_raw",
        "enabled_roll_deg", "enabled_pitch_deg", "enabled_yawrate_deg_s", "enabled_thrust_raw",
        "sent_roll_deg", "sent_pitch_deg", "sent_yawrate_deg_s", "sent_thrust_raw",
        "thrust_slew_limited", "props_off", "radio_connected", "armed_by_script",
        "controller_event_count", "controller_last_event_age_s", "controller_last_event_type",
        "controller_last_event_number", "controller_last_event_value",
        "roll_axis_raw", "pitch_axis_raw", "yaw_axis_raw", "thrust_axis_raw",
        "roll_axis_norm_raw", "pitch_axis_norm_raw", "yaw_axis_norm_raw", "thrust_axis_norm_raw",
        "roll_norm_after_deadzone", "pitch_norm_after_deadzone", "yaw_norm_after_deadzone", "thrust_norm",
        "thrust_axis_seen", "deadman_button", "deadman_pressed", "command_enabled", "button_0", "button_1", "button_2", "button_3", "button_4",
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
        "stream_extpos_enabled", "stream_extpos_sent_count", "stream_extpos_error",
        "estimate_mocap_error_m", "estimate_mocap_yaw_error_deg",
        "safety_event_count", "last_safety_event_type", "last_safety_event_detail",
        "last_safety_event_age_s", "stop_reason",
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
    value = clamp(value, -1.0, 1.0)
    if abs(value) < DEADZONE:
        return 0.0
    sign = 1 if value > 0 else -1
    return sign * (abs(value) - DEADZONE) / (1.0 - DEADZONE)


def slew_toward(current, target, rate_per_s, dt):
    max_step = max(0.0, rate_per_s * dt)
    if target > current:
        return min(target, current + max_step)
    if target < current:
        return target
    return current


def yaw_from_quat_deg(quat):
    siny_cosp = 2.0 * (quat.w * quat.z + quat.x * quat.y)
    cosy_cosp = 1.0 - 2.0 * (quat.y * quat.y + quat.z * quat.z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def mapping_from_cfclient_input_config(path):
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
        mapping = mapping_from_cfclient_input_config(args.cfclient_input_config)
        return ControllerMapping(
            roll_axis=mapping.roll_axis,
            pitch_axis=mapping.pitch_axis,
            yaw_axis=mapping.yaw_axis,
            thrust_axis=mapping.thrust_axis,
            roll_scale=mapping.roll_scale,
            pitch_scale=mapping.pitch_scale,
            yaw_scale=mapping.yaw_scale,
            thrust_scale=mapping.thrust_scale,
            deadman_button=args.deadman_button,
            emergency_button=args.emergency_button,
            source=mapping.source,
        )
    return ControllerMapping(deadman_button=args.deadman_button, emergency_button=args.emergency_button)


def print_controller_name(js_file):
    try:
        device_name_bytes = bytearray(64)
        fcntl.ioctl(js_file.fileno(), 0x80006A13, device_name_bytes)
        device_name = device_name_bytes.decode("utf-8").rstrip("\x00")
        print(f"[INFO] Controller device name: {device_name}")
    except OSError:
        pass


def find_controller_device(preferred):
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
    require_cflib()
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


def mocap_fields(mocap_state):
    # estimate_mocap_error_m is intentionally left blank in this diagnostic
    # script. It is only meaningful when mocap is explicitly streamed into a
    # configured/reset estimator, which this script does not do.
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
    return row


def write_log_row(
    logger,
    args,
    phase,
    loop_index,
    loop_dt,
    command_sent,
    sent_command_count,
    controller_row,
    telemetry_state,
    mocap_state,
    sent,
    safety_events,
    armed_by_script=False,
    radio_connected=False,
    stop_reason="",
):
    telemetry_values, telemetry_times, telemetry_counts = telemetry_state.snapshot()
    if not command_sent or getattr(args, "props_off", False):
        thrust_slew_limited = ""
    else:
        thrust_slew_limited = int(sent[3] != controller_row.get("mapped_thrust_raw", 0))
    row = {
        "mode": args.mode,
        "phase": phase,
        "loop_index": loop_index,
        "loop_dt_s": loop_dt,
        "command_rate_hz": 1.0 / loop_dt if loop_dt > 0.0 else "",
        "command_sent": int(command_sent),
        "sent_command_count": sent_command_count,
        "sent_roll_deg": sent[0],
        "sent_pitch_deg": sent[1],
        "sent_yawrate_deg_s": sent[2],
        "sent_thrust_raw": int(sent[3]),
        "thrust_slew_limited": thrust_slew_limited,
        "props_off": int(getattr(args, "props_off", False)),
        "radio_connected": int(radio_connected),
        "armed_by_script": int(armed_by_script),
    }
    row.update(controller_row)
    row.update(telemetry_values)
    row.update(telemetry_meta_fields(telemetry_times, telemetry_counts))
    row.update(mocap_fields(mocap_state))
    row["stream_extpos_enabled"] = 0
    row["stream_extpos_sent_count"] = ""
    row["stream_extpos_error"] = ""
    row.update(safety_events.snapshot())
    row["stop_reason"] = stop_reason
    logger.write(row)


def write_shutdown_row(
    logger,
    args,
    phase,
    controller_state,
    telemetry_state,
    mocap_state,
    safety_events,
    armed_by_script=False,
    radio_connected=False,
    stop_reason="",
):
    write_log_row(
        logger, args, phase, -1, 0.0, False, "",
        controller_state.snapshot(args), telemetry_state, mocap_state,
        (0.0, 0.0, 0.0, 0), safety_events,
        armed_by_script=armed_by_script,
        radio_connected=radio_connected,
        stop_reason=stop_reason,
    )


def output_path_from_args(args):
    if args.output:
        return Path(args.output)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(args.output_dir) / f"mocap-command-diagnostics-{args.mode}-{timestamp}.csv"


def print_mapping(args, controller_device, mapping, output_path=None):
    print("=" * 72)
    print("MOCAP COMMAND DIAGNOSTICS")
    print("=" * 72)
    print(f"Mode: {args.mode}")
    print(f"URI: {args.uri}")
    print(f"Controller: {controller_device}")
    print(
        "Mapping: "
        f"roll axis {mapping.roll_axis} scale {mapping.roll_scale:+.1f}, "
        f"pitch axis {mapping.pitch_axis} scale {mapping.pitch_scale:+.1f}, "
        f"yaw axis {mapping.yaw_axis} scale {mapping.yaw_scale:+.1f}, "
        f"thrust axis {mapping.thrust_axis} scale {mapping.thrust_scale:+.1f}; "
        f"dead-man button {mapping.deadman_button}; "
        f"emergency button {mapping.emergency_button}; source={mapping.source}"
    )
    print(f"Mocap: {'disabled' if args.no_mocap else args.rigid_body + '@' + args.mocap_host}")
    print(f"Limits: roll={args.max_roll_deg:.1f}deg pitch={args.max_pitch_deg:.1f}deg yawrate={args.max_yawrate_deg_s:.1f}deg/s thrust_cap={args.max_thrust}")
    print(f"Thrust slew: {args.thrust_slew_raw_per_s:.0f} raw/s")
    if output_path is not None:
        print(f"Output: {output_path}")
    print("[INFO] No replay, no HLC, no autonomous takeoff/landing, no position setpoints.")
    print("[INFO] External mocap streaming is disabled in this diagnostic script.")
    print("[INFO] estimate_mocap_error_m/yaw_error stay blank unless estimator streaming/setup is added later.")
    print("=" * 72)


def wait_for_low_thrust(controller_state, args, label):
    print(f"[INFO] {label}: move the right/thrust stick fully down.")
    while True:
        state = controller_state.snapshot(args)
        if state["emergency_stop"]:
            raise KeyboardInterrupt
        if state["thrust_axis_seen"] and state["thrust_norm"] <= 0.05:
            print(f"[INFO] {label}: thrust stick is low.")
            return
        time.sleep(0.25)


def send_zero_thrust_packets(cf, count=10, include_stop=False):
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


def supervisor_state_text(cf):
    try:
        states = cf.supervisor.read_state_list()
        if states:
            return ", ".join(states)
        return "no supervisor state bits set"
    except Exception as exc:
        return f"unavailable ({exc})"


def arm_for_manual_flight(cf):
    protocol_version = cf.platform.get_protocol_version()
    if protocol_version < 12:
        print(
            "[SAFETY] Props-on arming requires CRTP protocol version 12 or "
            f"later; connected Crazyflie reports version {protocol_version}."
        )
        print("[SAFETY] Update the Crazyflie firmware before a props-on run.")
        return False

    print(f"[INFO] Supervisor before arm: {supervisor_state_text(cf)}")
    send_zero_thrust_packets(cf, count=20, include_stop=False)
    try:
        print(f"[INFO] Supervisor can_be_armed={int(cf.supervisor.can_be_armed)}")
    except Exception as exc:
        print(f"[WARN] Could not read can_be_armed: {exc}")
    print(
        "[INFO] Sending supervisor arm request for manual low-level setpoints "
        f"(CRTP protocol version {protocol_version})..."
    )
    cf.supervisor.send_arming_request(True)
    send_zero_thrust_packets(cf, count=20, include_stop=False)
    for _ in range(10):
        try:
            if cf.supervisor.is_armed:
                print(f"[INFO] Supervisor after arm: {supervisor_state_text(cf)}")
                return True
        except Exception:
            break
        time.sleep(0.1)
    print(f"[WARN] Crazyflie did not report armed. Supervisor: {supervisor_state_text(cf)}")
    return False


def disarm(cf):
    try:
        if cf.platform.get_protocol_version() < 12:
            packet = CRTPPacket()
            packet.set_header(CRTPPort.PLATFORM, PLATFORM_COMMAND)
            packet.data = (PLATFORM_REQUEST_ARMING, False)
            cf.send_packet(packet)
        else:
            cf.supervisor.send_arming_request(False)
    except Exception:
        pass


def send_emergency_stop(cf):
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


def require_cflib():
    if CFLIB_IMPORT_ERROR is not None:
        raise RuntimeError(
            "cflib is not importable. Install/activate the Crazyflie Python "
            f"environment before using Crazyflie telemetry or manual-log: {CFLIB_IMPORT_ERROR}"
        )


def start_optional_mocap(args, mocap_state):
    if args.no_mocap:
        return None
    reader = MocapReader(args.mocap_host, args.rigid_body, mocap_state)
    reader.start()
    return reader


def run_controller_loop(args, logger, controller_reader, controller_state, telemetry_state, mocap_state, safety_events):
    started_at = time.time()
    last_print = 0.0
    last_loop_time = started_at
    loop_index = 0
    stop_reason = "operator_stop_or_duration"
    print("[INFO] Controller diagnostic logger is running. Press controller Start or Ctrl+C to stop.")
    while True:
        now = time.time()
        if controller_reader.error is not None:
            stop_reason = f"controller_reader_error: {controller_reader.error}"
            safety_events.add("controller_reader_error", str(controller_reader.error))
            break
        if args.duration and now - started_at >= args.duration:
            stop_reason = "duration_reached"
            break

        loop_dt = max(0.0, now - last_loop_time)
        last_loop_time = now
        control = controller_state.snapshot(args)
        if control["emergency_stop"]:
            stop_reason = "controller_start_button"
            safety_events.add("operator_stop", "controller emergency button pressed")
            break

        write_log_row(
            logger, args, "controller_log", loop_index, loop_dt, False, 0,
            control, telemetry_state, mocap_state, (0.0, 0.0, 0.0, 0),
            safety_events, radio_connected=False, stop_reason="",
        )
        if now - last_print >= PRINT_PERIOD_S:
            position, _, mocap_time, mocap_frames = mocap_state.snapshot()
            mocap_age = now - mocap_time if mocap_time else float("nan")
            mocap_text = f"mocap_age={mocap_age:.2f}s frames={mocap_frames}" if position else "mocap=no-pose"
            print(
                f"[controller-log] mapped r/p/y/t="
                f"{control['mapped_roll_deg']:+5.1f}/{control['mapped_pitch_deg']:+5.1f}/"
                f"{control['mapped_yawrate_deg_s']:+6.1f}/{control['mapped_thrust_raw']:5d} "
                f"events={control['controller_event_count']} {mocap_text}"
            )
            last_print = now
        loop_index += 1
        time.sleep(CONTROL_PERIOD_S)

    write_log_row(
        logger, args, "stop", loop_index, 0.0, False, 0,
        controller_state.snapshot(args), telemetry_state, mocap_state,
        (0.0, 0.0, 0.0, 0), safety_events, stop_reason=stop_reason,
    )


def run_manual_loop(args, logger, cf, controller_reader, controller_state, telemetry_state, mocap_state, safety_events, armed_by_script):
    started_at = time.time()
    last_print = 0.0
    last_loop_time = started_at
    loop_index = 0
    sent_thrust = 0.0
    sent_command_count = 0
    stop_reason = "operator_stop_or_duration"
    phase = "props_off" if args.props_off else "manual_log"
    print("[INFO] Manual command diagnostic logger is running. Press controller Start or Ctrl+C to stop.")
    print(f"[INFO] Hold controller button {args.deadman_button} to enable commands; release it for immediate neutral/zero thrust.")
    while True:
        now = time.time()
        if controller_reader.error is not None:
            stop_reason = f"controller_reader_error: {controller_reader.error}"
            safety_events.add("controller_reader_error", str(controller_reader.error))
            break
        if args.duration and now - started_at >= args.duration:
            stop_reason = "duration_reached"
            break

        loop_dt = max(0.0, now - last_loop_time)
        last_loop_time = now
        control = controller_state.snapshot(args)
        if control["emergency_stop"]:
            stop_reason = "controller_start_button"
            safety_events.add("operator_stop", "controller emergency button pressed")
            break

        command_enabled = bool(control["command_enabled"]) and not args.props_off
        target_thrust = control["enabled_thrust_raw"] if command_enabled else 0
        if target_thrust > sent_thrust:
            sent_thrust = slew_toward(
                sent_thrust, target_thrust, args.thrust_slew_raw_per_s, loop_dt
            )
        else:
            sent_thrust = float(target_thrust)
        sent = (
            control["enabled_roll_deg"] if command_enabled else 0.0,
            control["enabled_pitch_deg"] if command_enabled else 0.0,
            control["enabled_yawrate_deg_s"] if command_enabled else 0.0,
            int(sent_thrust),
        )
        cf.commander.send_setpoint(sent[0], sent[1], sent[2], sent[3])
        sent_command_count += 1

        write_log_row(
            logger, args, phase, loop_index, loop_dt, True, sent_command_count,
            control, telemetry_state, mocap_state, sent, safety_events,
            armed_by_script=armed_by_script, radio_connected=True,
        )
        if now - last_print >= PRINT_PERIOD_S:
            values, _, counts = telemetry_state.snapshot()
            position, _, mocap_time, mocap_frames = mocap_state.snapshot()
            mocap_age = now - mocap_time if mocap_time else float("nan")
            mocap_text = f"mocap_age={mocap_age:.2f}s frames={mocap_frames}" if position else "mocap=no-pose"
            print(
                f"[{phase}] sent r/p/y/t={sent[0]:+5.1f}/{sent[1]:+5.1f}/"
                f"{sent[2]:+6.1f}/{sent[3]:5d} target_t={target_thrust:5d} "
                f"deadman={control['deadman_pressed']} "
                f"z={values.get('stateEstimate.z', float('nan')):+.2f} "
                f"vbat={values.get('pm.vbat', float('nan')):.2f} "
                f"packets={sum(counts.values())} rate={1.0 / loop_dt if loop_dt > 0.0 else 0.0:.1f}Hz {mocap_text}"
            )
            last_print = now
        loop_index += 1
        time.sleep(CONTROL_PERIOD_S)

    write_log_row(
        logger, args, "stop", loop_index, 0.0, False, sent_command_count,
        controller_state.snapshot(args), telemetry_state, mocap_state,
        (0.0, 0.0, 0.0, 0), safety_events, armed_by_script=armed_by_script,
        radio_connected=True, stop_reason=stop_reason,
    )


def run_validate(args):
    mapping = mapping_from_args(args)
    controller_device = find_controller_device(args.controller)
    logger = CsvLogger(output_path_from_args(args))
    print_mapping(args, controller_device, mapping, logger.output_path)
    controller_state = ControllerState(mapping)
    controller_reader = ControllerReader(controller_device, controller_state)
    mocap_state = MocapState()
    mocap_reader = start_optional_mocap(args, mocap_state)
    telemetry_state = TelemetryState()
    safety_events = SafetyEvents()
    logconfigs = []
    stop_reason = "validate_complete"

    try:
        controller_reader.start()
        time.sleep(args.validate_seconds)
        if controller_reader.error is not None:
            stop_reason = f"controller_reader_error: {controller_reader.error}"
            raise RuntimeError(f"Controller reader failed: {controller_reader.error}")
        control = controller_state.snapshot(args)
        print(f"[OK] Controller opened, events={control['controller_event_count']}, thrust_axis_seen={control['thrust_axis_seen']}")
        if not args.no_mocap:
            position, _, last_update, frame_count = mocap_state.snapshot()
            if position is None:
                print("[WARN] Mocap connected check did not receive the requested rigid body yet.")
            else:
                print(f"[OK] Mocap frames={frame_count}, age={time.time() - last_update:.3f}s, pos={position}")
        if not args.skip_crazyflie:
            require_cflib()
            crtp.init_drivers()
            with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
                print("[OK] Crazyflie connected.")
                logconfigs = setup_telemetry(scf.cf, telemetry_state)
                time.sleep(args.validate_seconds)
                values, _, counts = telemetry_state.snapshot()
                print(f"[OK] Telemetry packets={sum(counts.values())}, groups={counts}")
                if values:
                    print_battery_warning(telemetry_state)
        print("[DONE] validate complete.")
    except Exception as exc:
        stop_reason = str(exc)
        safety_events.add("validate_error", str(exc))
        raise
    finally:
        write_shutdown_row(
            logger, args, "validate", controller_state, telemetry_state,
            mocap_state, safety_events, stop_reason=stop_reason,
        )
        for config in logconfigs:
            try:
                config.stop()
            except Exception:
                pass
        controller_reader.close()
        controller_reader.join(timeout=1.0)
        if mocap_reader is not None:
            mocap_reader.close()
            mocap_reader.join(timeout=1.0)
            if mocap_reader.is_alive():
                print("[WARN] Mocap reader did not stop before process shutdown.")
        logger.close()
        print(f"[DONE] Wrote log: {logger.output_path}")


def run_controller_log(args):
    mapping = mapping_from_args(args)
    controller_device = find_controller_device(args.controller)
    logger = CsvLogger(output_path_from_args(args))
    controller_state = ControllerState(mapping)
    controller_reader = ControllerReader(controller_device, controller_state)
    telemetry_state = TelemetryState()
    mocap_state = MocapState()
    mocap_reader = start_optional_mocap(args, mocap_state)
    safety_events = SafetyEvents()
    print_mapping(args, controller_device, mapping, logger.output_path)
    try:
        controller_reader.start()
        time.sleep(0.3)
        if controller_reader.error is not None:
            raise RuntimeError(f"Controller reader failed: {controller_reader.error}")
        run_controller_loop(args, logger, controller_reader, controller_state, telemetry_state, mocap_state, safety_events)
    except KeyboardInterrupt:
        safety_events.add("operator_abort", "Ctrl+C")
        write_shutdown_row(
            logger, args, "operator_abort", controller_state, telemetry_state,
            mocap_state, safety_events, stop_reason="operator_abort_ctrl_c",
        )
    finally:
        controller_reader.close()
        controller_reader.join(timeout=1.0)
        if mocap_reader is not None:
            mocap_reader.close()
            mocap_reader.join(timeout=1.0)
            if mocap_reader.is_alive():
                print("[WARN] Mocap reader did not stop before process shutdown.")
        logger.close()
        print(f"[DONE] Wrote log: {logger.output_path}")


def run_manual_log(args):
    mapping = mapping_from_args(args)
    controller_device = find_controller_device(args.controller)
    logger = CsvLogger(output_path_from_args(args))
    controller_state = ControllerState(mapping)
    controller_reader = ControllerReader(controller_device, controller_state)
    telemetry_state = TelemetryState()
    mocap_state = MocapState()
    mocap_reader = start_optional_mocap(args, mocap_state)
    safety_events = SafetyEvents()
    logconfigs = []
    cf = None
    armed_by_script = False
    print_mapping(args, controller_device, mapping, logger.output_path)
    if args.props_off:
        print("[MODE] Props-off: will not arm; may send zero-thrust setpoints for radio/logging diagnostics.")
    else:
        print("[MODE] Manual-log: script can arm and sends low-level manual setpoints only.")

    try:
        controller_reader.start()
        time.sleep(0.3)
        if controller_reader.error is not None:
            raise RuntimeError(f"Controller reader failed: {controller_reader.error}")
        wait_for_low_thrust(controller_state, args, "Before connecting")

        input("Press ENTER to connect Crazyflie, or Ctrl+C to abort...")
        require_cflib()
        crtp.init_drivers()
        with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
            cf = scf.cf
            try:
                print("[INFO] Crazyflie connected.")
                logconfigs = setup_telemetry(cf, telemetry_state)
                time.sleep(0.8)
                print_battery_warning(telemetry_state)

                if args.props_off:
                    print("[INFO] Props-off mode: not arming; sent thrust is forced to zero.")
                else:
                    wait_for_low_thrust(controller_state, args, "Immediately before arming")
                    input("Press ENTER to ARM for manual diagnostic logging, or Ctrl+C to abort...")
                    armed_by_script = arm_for_manual_flight(cf)
                    if not armed_by_script:
                        safety_events.add("arm_failed", "Props-on arming was unavailable or the Crazyflie did not report armed")
                        write_shutdown_row(
                            logger, args, "arm_failed", controller_state, telemetry_state,
                            mocap_state, safety_events, armed_by_script=False,
                            radio_connected=True, stop_reason="arm_failed",
                        )
                        return

                run_manual_loop(
                    args, logger, cf, controller_reader, controller_state,
                    telemetry_state, mocap_state, safety_events, armed_by_script,
                )
            finally:
                send_emergency_stop(cf)
                for config in logconfigs:
                    try:
                        config.stop()
                    except Exception:
                        pass
                logconfigs = []
    except KeyboardInterrupt:
        safety_events.add("operator_abort", "Ctrl+C")
        write_shutdown_row(
            logger, args, "operator_abort", controller_state, telemetry_state,
            mocap_state, safety_events, armed_by_script=armed_by_script,
            radio_connected=cf is not None, stop_reason="operator_abort_ctrl_c",
        )
    except Exception as exc:
        if is_radio_busy_error(exc):
            print("\n[SAFETY] Crazyradio is busy; close cfclient or other Crazyflie scripts.")
        else:
            print(f"\n[SAFETY] Error: {exc}")
        safety_events.add("error", str(exc))
        write_shutdown_row(
            logger, args, "error", controller_state, telemetry_state,
            mocap_state, safety_events, armed_by_script=armed_by_script,
            radio_connected=cf is not None, stop_reason=str(exc),
        )
    finally:
        for config in logconfigs:
            try:
                config.stop()
            except Exception:
                pass
        controller_reader.close()
        controller_reader.join(timeout=1.0)
        if mocap_reader is not None:
            mocap_reader.close()
            mocap_reader.join(timeout=1.0)
            if mocap_reader.is_alive():
                print("[WARN] Mocap reader did not stop before process shutdown.")
        logger.close()
        print(f"[DONE] Wrote log: {logger.output_path}")


def add_common_args(parser):
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--controller", default=DEFAULT_CONTROLLER_DEVICE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output")
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--max-roll-deg", type=float, default=DEFAULT_MAX_ROLL_DEG)
    parser.add_argument("--max-pitch-deg", type=float, default=DEFAULT_MAX_PITCH_DEG)
    parser.add_argument("--max-yawrate-deg-s", type=float, default=DEFAULT_MAX_YAWRATE_DEG_S)
    parser.add_argument("--max-thrust", type=int, default=DEFAULT_MAX_THRUST)
    parser.add_argument("--thrust-slew-raw-per-s", type=float, default=DEFAULT_THRUST_SLEW_RAW_PER_S)
    parser.add_argument("--cfclient-input-config", default=None)
    parser.add_argument("--deadman-button", type=int, default=4, help="Hold this joystick button to enable manual commands.")
    parser.add_argument("--emergency-button", type=int, default=9)
    parser.add_argument("--no-mocap", action="store_true")
    parser.add_argument("--mocap-host", default=DEFAULT_MOCAP_HOST)
    parser.add_argument("--rigid-body", default=DEFAULT_RIGID_BODY_NAME)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    validate = subparsers.add_parser("validate", help="Check controller, mocap, and optional Crazyflie telemetry.")
    add_common_args(validate)
    validate.add_argument("--skip-crazyflie", action="store_true")
    validate.add_argument("--validate-seconds", type=float, default=1.0)

    controller_log = subparsers.add_parser("controller-log", help="Log controller mapping and mocap without opening Crazyflie.")
    add_common_args(controller_log)

    manual_log = subparsers.add_parser("manual-log", help="Log controller, sent low-level commands, telemetry, and mocap.")
    add_common_args(manual_log)
    manual_log.add_argument("--props-off", action="store_true", help="Do not arm; send only zero-thrust manual setpoints for diagnostics.")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.max_thrust < 0:
        raise RuntimeError("--max-thrust must be non-negative")
    if args.thrust_slew_raw_per_s < 0.0:
        raise RuntimeError("--thrust-slew-raw-per-s must be non-negative")
    if args.deadman_button == args.emergency_button:
        raise RuntimeError("--deadman-button and --emergency-button must be different")
    if not 0 <= args.deadman_button <= 9:
        raise RuntimeError("--deadman-button must be between 0 and 9")
    if not 0 <= args.emergency_button <= 9:
        raise RuntimeError("--emergency-button must be between 0 and 9")
    if args.mode == "validate":
        run_validate(args)
    elif args.mode == "controller-log":
        run_controller_log(args)
    elif args.mode == "manual-log":
        run_manual_log(args)
    else:
        raise RuntimeError(f"Unknown mode: {args.mode}")


if __name__ == "__main__":
    main()
