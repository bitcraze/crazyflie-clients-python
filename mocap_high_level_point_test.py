#!/usr/bin/env python3
"""
Guarded high-level-commander point-to-point test with mocap external position.

This is a viability test for autonomous Crazyflie flight inside the cage:

    OptiTrack/Motive -> VRPN -> cf.extpos -> Kalman estimator -> HLC commands

The script takes off to a low hover, moves a small relative distance from the
start point, returns to the start point, and lands. It also has an optional
tiny figure-8 mode for later, but the default mode is the safer point test.
Tune the constants and CLI arguments before flying.
"""

import argparse
import csv
import math
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
from cflib.utils.reset_estimator import reset_estimator


# Radio and mocap connection.
DEFAULT_URI = "radio://0/80/2M"
DEFAULT_MOCAP_HOST = "192.168.1.42:3883"
DEFAULT_RIGID_BODY_NAME = "crazyflie_21"

# Conservative cage limits in raw mocap/world coordinates.
# OptiTrack center is near (0.0, 0.0, 0.03) in this cage:
# - script x = first mocap position value = cage left/right axis; left is positive
# - script y = second mocap position value = cage front/back axis; front is negative
# - script z = height; floor/base is about 0.03 m
DEFAULT_X_MIN = -1.50
DEFAULT_X_MAX = 1.50
DEFAULT_Y_MIN = -1.50
DEFAULT_Y_MAX = 1.50
DEFAULT_Z_MIN = 0.00
DEFAULT_Z_MAX = 2.00

# Flight defaults.
DEFAULT_HEIGHT_M = 0.05
DEFAULT_DX_M = 0.00
DEFAULT_DY_M = 0.00
DEFAULT_TAKEOFF_DURATION_S = 4.0
DEFAULT_MOVE_DURATION_S = 5.0
DEFAULT_HOVER_DURATION_S = 2.0
DEFAULT_LAND_DURATION_S = 5.0

# Guard defaults.
MOCAP_TIMEOUT_S = 8.0
POSE_STALE_TIMEOUT_S = 0.30
POSE_STABILITY_SECONDS = 2.0
POSE_STABILITY_MAX_RANGE_M = 0.05
ESTIMATE_MATCH_SECONDS = 2.0
ESTIMATE_STALE_TIMEOUT_S = 0.50
ESTIMATE_MAX_ERROR_M = 0.12
MAX_RADIUS_FROM_START_M = 0.25
MAX_X_FROM_START_M = 0.15
MAX_Y_FROM_START_M = 0.15
MAX_HEIGHT_ABOVE_START_M = 0.20
MAX_TARGET_ERROR_M = 0.14
MAX_TAKEOFF_TARGET_ERROR_M = 0.03
TAKEOFF_AIRBORNE_HEIGHT_M = 0.02
MAX_GROUND_TAKEOFF_TARGET_ERROR_M = 0.06
MAX_HOVER_ONLY_TARGET_ERROR_M = 0.04
EMERGENCY_ZERO_THRUST_PACKETS = 40
EMERGENCY_ZERO_THRUST_PERIOD_S = 0.01
MIN_BATTERY_V = 3.65
LOW_BATTERY_V = 3.70
LOG_PERIOD_MS = 100
MONITOR_PERIOD_S = 0.10
OUTPUT_DIR = "flight_logs"

# Start with position-only external updates. Switch to extpose only after the
# mocap quaternion/frame convention is known to be correct.
DEFAULT_POSE_MODE = "extpos"
ORIENTATION_STD_DEV = 8.0e-3
MAX_PREFLIGHT_YAW_ERROR_DEG = 20.0
MAX_EXTPOSE_YAW_JUMP_DEG = 45.0
YAW_JUMP_POSITION_GATE_M = 0.03


@dataclass(frozen=True)
class QuatSnapshot:
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class Bounds:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float
    margin: float

    def check(self, position):
        x, y, z = position
        if x < self.x_min + self.margin:
            return False, f"x={x:.3f} below usable minimum"
        if x > self.x_max - self.margin:
            return False, f"x={x:.3f} above usable maximum"
        if y < self.y_min + self.margin:
            return False, f"y={y:.3f} below usable minimum"
        if y > self.y_max - self.margin:
            return False, f"y={y:.3f} above usable maximum"
        if z < self.z_min:
            return False, f"z={z:.3f} below minimum"
        if z > self.z_max - self.margin:
            return False, f"z={z:.3f} above usable maximum"
        return True, "inside bounds"

    def require_path(self, points):
        for point in points:
            safe, reason = self.check(point)
            if not safe:
                raise RuntimeError(f"Planned path leaves bounds: {reason}")


class GuardTrip(RuntimeError):
    def __init__(self, reason, immediate_stop=False):
        super().__init__(reason)
        self.reason = reason
        self.immediate_stop = immediate_stop


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


class EstimateState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.yaw_deg = None
        self.battery_v = 0.0
        self.last_update = 0.0

    def update(self, x, y, z, yaw_deg, battery_v):
        with self._lock:
            self.position = (x, y, z)
            self.yaw_deg = yaw_deg
            self.battery_v = battery_v
            self.last_update = time.time()

    def snapshot(self):
        with self._lock:
            return self.position, self.yaw_deg, self.battery_v, self.last_update


class PoseStreamStats:
    def __init__(self):
        self._lock = Lock()
        self.extpose_packets = 0
        self.extpos_packets = 0
        self.rejected_extpose_orientation = 0

    def record_extpose(self):
        with self._lock:
            self.extpose_packets += 1

    def record_extpos(self):
        with self._lock:
            self.extpos_packets += 1

    def record_rejected_orientation(self):
        with self._lock:
            self.rejected_extpose_orientation += 1
            self.extpos_packets += 1

    def snapshot(self):
        with self._lock:
            return {
                "extpose_packets": self.extpose_packets,
                "extpos_packets": self.extpos_packets,
                "rejected_extpose_orientation": self.rejected_extpose_orientation,
            }


class PoseStreamer:
    def __init__(self, cf, pose_mode, max_yaw_jump_deg, yaw_jump_position_gate_m, stats):
        self.cf = cf
        self.pose_mode = pose_mode
        self.max_yaw_jump_deg = max_yaw_jump_deg
        self.yaw_jump_position_gate_m = yaw_jump_position_gate_m
        self.stats = stats
        self.last_accepted_position = None
        self.last_accepted_yaw_deg = None
        self.last_warning_at = 0.0

    def send(self, x, y, z, quat):
        position = (x, y, z)
        if self.pose_mode != "extpose":
            self.cf.extpos.send_extpos(x, y, z)
            self.stats.record_extpos()
            return

        yaw_deg = yaw_from_quat_deg(quat)
        if self.last_accepted_yaw_deg is not None:
            yaw_jump_deg = abs(wrap_degrees(yaw_deg - self.last_accepted_yaw_deg))
            position_step_m = math.dist(position, self.last_accepted_position)
            if (
                yaw_jump_deg > self.max_yaw_jump_deg
                and position_step_m < self.yaw_jump_position_gate_m
            ):
                self.stats.record_rejected_orientation()
                self.cf.extpos.send_extpos(x, y, z)
                self._warn_rejected(yaw_jump_deg, position_step_m)
                return

        self.last_accepted_position = position
        self.last_accepted_yaw_deg = yaw_deg
        self.cf.extpos.send_extpose(x, y, z, quat.x, quat.y, quat.z, quat.w)
        self.stats.record_extpose()

    def _warn_rejected(self, yaw_jump_deg, position_step_m):
        now = time.time()
        if now - self.last_warning_at < 1.0:
            return
        print(
            "[WARN] Rejected extpose orientation; "
            f"yaw jump {yaw_jump_deg:.1f} deg with position step {position_step_m:.3f}m. "
            "Sent extpos fallback."
        )
        self.last_warning_at = now


class MocapReader(Thread):
    def __init__(self, host, body_name, state):
        Thread.__init__(self)
        self.daemon = True
        self.host = host
        self.body_name = body_name
        self.state = state
        self.on_pose = None
        self.error = None
        self._stay_open = True

    def close(self):
        self._stay_open = False

    def run(self):
        try:
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
                    quat = obj.rotation
                    quat_snapshot = QuatSnapshot(quat.x, quat.y, quat.z, quat.w)
                    self.state.update((pos[0], pos[1], pos[2]), quat_snapshot)
                    if self.on_pose is not None:
                        self.on_pose(pos[0], pos[1], pos[2], quat_snapshot)
        except Exception as exc:
            self.error = exc


class CsvLogger:
    FIELDNAMES = [
        "wall_time_s",
        "elapsed_s",
        "mode",
        "phase",
        "target_x",
        "target_y",
        "target_z",
        "mocap_x",
        "mocap_y",
        "mocap_z",
        "mocap_age_s",
        "mocap_frame_count",
        "estimate_x",
        "estimate_y",
        "estimate_z",
        "estimate_age_s",
        "estimate_error_m",
        "mocap_yaw_deg",
        "estimate_yaw_deg",
        "yaw_error_deg",
        "extpose_packets",
        "extpos_packets",
        "rejected_extpose_orientation",
        "battery_v",
        "height_above_start_m",
        "radius_from_start_m",
        "target_error_m",
        "stop_reason",
    ]

    def __init__(self, mode):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.output_path = Path(OUTPUT_DIR) / f"mocap-hlc-{mode}-{timestamp}.csv"
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output_path.open("w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        self._writer.writeheader()
        self.started_at = time.time()
        self.mode = mode
        self.pose_stats = None

    def write(self, row):
        now = time.time()
        full_row = {
            "wall_time_s": now,
            "elapsed_s": now - self.started_at,
            "mode": self.mode,
        }
        full_row.update(row)
        if self.pose_stats is not None:
            full_row.update(self.pose_stats.snapshot())
        else:
            full_row.setdefault("extpose_packets", "")
            full_row.setdefault("extpos_packets", "")
            full_row.setdefault("rejected_extpose_orientation", "")
        self._writer.writerow(full_row)
        self._file.flush()

    def close(self):
        self._file.close()


def distance_2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def wrap_degrees(angle_deg):
    while angle_deg > 180.0:
        angle_deg -= 360.0
    while angle_deg < -180.0:
        angle_deg += 360.0
    return angle_deg


def yaw_from_quat_deg(quat):
    siny_cosp = 2.0 * (quat.w * quat.z + quat.x * quat.y)
    cosy_cosp = 1.0 - 2.0 * (quat.y * quat.y + quat.z * quat.z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def pose_age(mocap_state):
    _, _, last_update, _ = mocap_state.snapshot()
    if last_update == 0.0:
        return float("inf")
    return time.time() - last_update


def estimate_age(estimate_state):
    _, _, _, last_update = estimate_state.snapshot()
    if last_update == 0.0:
        return float("inf")
    return time.time() - last_update


def send_extpose_or_extpos(cf, pose_mode, x, y, z, quat):
    if pose_mode == "extpose":
        cf.extpos.send_extpose(x, y, z, quat.x, quat.y, quat.z, quat.w)
    else:
        cf.extpos.send_extpos(x, y, z)


def setup_estimate_logger(cf, estimate_state):
    logconf = LogConfig(name="Estimate", period_in_ms=LOG_PERIOD_MS)
    logconf.add_variable("stateEstimate.x", "float")
    logconf.add_variable("stateEstimate.y", "float")
    logconf.add_variable("stateEstimate.z", "float")
    logconf.add_variable("stateEstimate.yaw", "float")
    logconf.add_variable("pm.vbat", "float")

    def on_data(timestamp, data, logconf):
        del timestamp, logconf
        estimate_state.update(
            data["stateEstimate.x"],
            data["stateEstimate.y"],
            data["stateEstimate.z"],
            data["stateEstimate.yaw"],
            data["pm.vbat"],
        )

    def on_error(logconf, msg):
        print(f"[WARN] Logger error from {logconf.name}: {msg}")

    cf.log.add_config(logconf)
    logconf.data_received_cb.add_callback(on_data)
    logconf.error_cb.add_callback(on_error)
    logconf.start()
    return logconf


def wait_for_fresh_pose(mocap_state, mocap_reader):
    print("[INFO] Waiting for fresh mocap pose...")
    deadline = time.time() + MOCAP_TIMEOUT_S
    while time.time() < deadline:
        if mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        if pose_age(mocap_state) <= POSE_STALE_TIMEOUT_S:
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


def require_stable_pose(mocap_state):
    print(f"[INFO] Checking pose stability for {POSE_STABILITY_SECONDS:.1f}s...")
    samples = []
    started_at = time.time()
    while time.time() - started_at < POSE_STABILITY_SECONDS:
        if pose_age(mocap_state) > POSE_STALE_TIMEOUT_S:
            raise RuntimeError("Mocap pose became stale during stability check")
        position, _, _, _ = mocap_state.snapshot()
        if position is not None:
            samples.append(position)
        time.sleep(0.05)
    if len(samples) < 5:
        raise RuntimeError("Not enough mocap samples for stability check")
    ranges = []
    for axis in range(3):
        values = [sample[axis] for sample in samples]
        ranges.append(max(values) - min(values))
    print(
        "[INFO] Pose range: "
        f"dx={ranges[0]:.3f}, dy={ranges[1]:.3f}, dz={ranges[2]:.3f}"
    )
    if any(axis_range > POSE_STABILITY_MAX_RANGE_M for axis_range in ranges):
        raise RuntimeError(
            f"Mocap pose is not stable enough; limit is {POSE_STABILITY_MAX_RANGE_M:.3f}m"
        )


def require_battery(estimate_state):
    _, _, battery_v, _ = estimate_state.snapshot()
    print(f"[INFO] Battery: {battery_v:.2f} V")
    if battery_v <= 0.0:
        raise RuntimeError("Battery voltage was not logged")
    if battery_v < MIN_BATTERY_V:
        raise RuntimeError(f"Battery {battery_v:.2f}V is below {MIN_BATTERY_V:.2f}V")
    if battery_v < LOW_BATTERY_V:
        print("[WARN] Battery is low; use a fresh pack if possible.")


def require_yaw_agreement(mocap_state, estimate_state, max_error_deg):
    print(f"[INFO] Checking yaw agreement; limit {max_error_deg:.1f} deg...")
    max_abs_error = 0.0
    started_at = time.time()
    while time.time() - started_at < ESTIMATE_MATCH_SECONDS:
        if pose_age(mocap_state) > POSE_STALE_TIMEOUT_S:
            raise RuntimeError("Mocap pose became stale during yaw check")
        if estimate_age(estimate_state) > ESTIMATE_STALE_TIMEOUT_S:
            raise RuntimeError("Estimator telemetry became stale during yaw check")

        _, quat, _, _ = mocap_state.snapshot()
        _, estimate_yaw_deg, _, _ = estimate_state.snapshot()
        if quat is not None and estimate_yaw_deg is not None:
            mocap_yaw_deg = yaw_from_quat_deg(quat)
            yaw_error_deg = wrap_degrees(estimate_yaw_deg - mocap_yaw_deg)
            max_abs_error = max(max_abs_error, abs(yaw_error_deg))
            if abs(yaw_error_deg) > max_error_deg:
                raise RuntimeError(
                    f"Estimator/mocap yaw mismatch {yaw_error_deg:+.1f} deg exceeds "
                    f"{max_error_deg:.1f} deg. Do not fly HLC until yaw/frame convention is fixed."
                )
        time.sleep(0.05)
    print(f"[INFO] Yaw agreement OK; max abs error {max_abs_error:.1f} deg")


def require_estimator_agreement(mocap_state, estimate_state):
    print(f"[INFO] Checking estimator agreement for {ESTIMATE_MATCH_SECONDS:.1f}s...")
    max_error = 0.0
    started_at = time.time()
    while time.time() - started_at < ESTIMATE_MATCH_SECONDS:
        if pose_age(mocap_state) > POSE_STALE_TIMEOUT_S:
            raise RuntimeError("Mocap pose became stale during estimator check")
        if estimate_age(estimate_state) > ESTIMATE_STALE_TIMEOUT_S:
            raise RuntimeError("Estimator telemetry became stale during estimator check")

        mocap_position, _, _, _ = mocap_state.snapshot()
        estimate_position, _, _, _ = estimate_state.snapshot()
        if mocap_position is not None and estimate_position is not None:
            error = math.dist(mocap_position, estimate_position)
            max_error = max(max_error, error)
            if error > ESTIMATE_MAX_ERROR_M:
                raise RuntimeError(
                    f"Estimator/mocap mismatch {error:.3f}m exceeds {ESTIMATE_MAX_ERROR_M:.3f}m"
                )
        time.sleep(0.05)
    print(f"[INFO] Estimator agreement OK; max error {max_error:.3f}m")


def log_monitor_row(logger, mocap_state, estimate_state, start_position, target, phase, stop_reason=""):
    now = time.time()
    mocap_position, quat, last_pose, frame_count = mocap_state.snapshot()
    estimate_position, estimate_yaw_deg, battery_v, last_estimate = estimate_state.snapshot()
    mocap_age = now - last_pose if last_pose else float("inf")
    est_age = now - last_estimate if last_estimate else float("inf")
    estimate_error = ""
    mocap_yaw_deg = ""
    yaw_error_deg = ""
    if quat is not None:
        mocap_yaw_deg = yaw_from_quat_deg(quat)
    if mocap_position is not None and estimate_position is not None:
        estimate_error = math.dist(mocap_position, estimate_position)
    if mocap_yaw_deg != "" and estimate_yaw_deg is not None:
        yaw_error_deg = wrap_degrees(estimate_yaw_deg - mocap_yaw_deg)
    logger.write({
        "phase": phase,
        "target_x": target[0],
        "target_y": target[1],
        "target_z": target[2],
        "mocap_x": mocap_position[0] if mocap_position else "",
        "mocap_y": mocap_position[1] if mocap_position else "",
        "mocap_z": mocap_position[2] if mocap_position else "",
        "mocap_age_s": mocap_age,
        "mocap_frame_count": frame_count,
        "estimate_x": estimate_position[0] if estimate_position else "",
        "estimate_y": estimate_position[1] if estimate_position else "",
        "estimate_z": estimate_position[2] if estimate_position else "",
        "estimate_age_s": est_age,
        "estimate_error_m": estimate_error,
        "mocap_yaw_deg": mocap_yaw_deg,
        "estimate_yaw_deg": estimate_yaw_deg if estimate_yaw_deg is not None else "",
        "yaw_error_deg": yaw_error_deg,
        "battery_v": battery_v,
        "height_above_start_m": mocap_position[2] - start_position[2] if mocap_position else "",
        "radius_from_start_m": distance_2d(mocap_position, start_position) if mocap_position else "",
        "target_error_m": distance_2d(mocap_position, target) if mocap_position else "",
        "stop_reason": stop_reason,
    })


def check_flight_guards(mocap_state, estimate_state, start_position, target, bounds, phase, hover_only):
    if pose_age(mocap_state) > POSE_STALE_TIMEOUT_S:
        raise GuardTrip("mocap pose is stale")
    if estimate_age(estimate_state) > ESTIMATE_STALE_TIMEOUT_S:
        raise GuardTrip("estimator telemetry is stale")

    mocap_position, _, _, _ = mocap_state.snapshot()
    estimate_position, _, battery_v, _ = estimate_state.snapshot()
    safe, reason = bounds.check(mocap_position)
    if not safe:
        raise GuardTrip(reason)
    if mocap_position[2] - start_position[2] > MAX_HEIGHT_ABOVE_START_M:
        raise GuardTrip("height above start exceeded")
    if abs(mocap_position[0] - start_position[0]) > MAX_X_FROM_START_M:
        raise GuardTrip("x drift from start exceeded")
    if abs(mocap_position[1] - start_position[1]) > MAX_Y_FROM_START_M:
        raise GuardTrip("y drift from start exceeded")
    if distance_2d(mocap_position, start_position) > MAX_RADIUS_FROM_START_M:
        raise GuardTrip("radius from start exceeded")

    target_error = distance_2d(mocap_position, target)
    height_above_start = mocap_position[2] - start_position[2]
    if phase == "takeoff":
        if height_above_start < TAKEOFF_AIRBORNE_HEIGHT_M:
            if target_error > MAX_GROUND_TAKEOFF_TARGET_ERROR_M:
                raise GuardTrip("ground takeoff slide exceeded", immediate_stop=True)
        elif target_error > MAX_TAKEOFF_TARGET_ERROR_M:
            raise GuardTrip("takeoff horizontal drift exceeded", immediate_stop=True)
    airborne = height_above_start >= TAKEOFF_AIRBORNE_HEIGHT_M
    if phase == "hover" and hover_only and not airborne:
        raise GuardTrip("takeoff did not become airborne", immediate_stop=True)
    if hover_only and airborne and target_error > MAX_HOVER_ONLY_TARGET_ERROR_M:
        raise GuardTrip("hover-only horizontal drift exceeded", immediate_stop=True)
    if target_error > MAX_TARGET_ERROR_M:
        raise GuardTrip("horizontal target error exceeded")
    if estimate_position is not None and math.dist(mocap_position, estimate_position) > ESTIMATE_MAX_ERROR_M:
        raise GuardTrip("estimator/mocap mismatch exceeded")
    if battery_v and battery_v < MIN_BATTERY_V:
        raise GuardTrip("battery below minimum")


def monitor(
    logger,
    mocap_state,
    estimate_state,
    start_position,
    target,
    bounds,
    phase,
    duration,
    hover_only=False,
):
    started_at = time.time()
    last_print = 0.0
    while time.time() - started_at < duration:
        check_flight_guards(
            mocap_state,
            estimate_state,
            start_position,
            target,
            bounds,
            phase,
            hover_only,
        )
        log_monitor_row(logger, mocap_state, estimate_state, start_position, target, phase)
        now = time.time()
        if now - last_print >= 0.5:
            position, _, _, _ = mocap_state.snapshot()
            print(
                f"[{phase}] pos=({position[0]:+.3f}, {position[1]:+.3f}, {position[2]:+.3f}) "
                f"xy_target_error={distance_2d(position, target):.3f}m"
            )
            last_print = now
        time.sleep(MONITOR_PERIOD_S)


def run_estimator_validation(args, logger, mocap_state, estimate_state, start_position):
    print(
        f"[VALIDATE] Logging mocap vs stateEstimate for {args.validate_duration:.1f}s. "
        "Move the drone by hand with props off."
    )
    target = start_position
    started_at = time.time()
    last_print = 0.0
    while time.time() - started_at < args.validate_duration:
        if pose_age(mocap_state) > POSE_STALE_TIMEOUT_S:
            raise RuntimeError("Mocap pose became stale during estimator validation")
        if estimate_age(estimate_state) > ESTIMATE_STALE_TIMEOUT_S:
            raise RuntimeError("Estimator telemetry became stale during estimator validation")
        log_monitor_row(logger, mocap_state, estimate_state, start_position, target, "validate")
        now = time.time()
        if now - last_print >= 0.5:
            mocap_position, quat, _, _ = mocap_state.snapshot()
            estimate_position, estimate_yaw_deg, _, _ = estimate_state.snapshot()
            error = math.dist(mocap_position, estimate_position) if estimate_position else float("nan")
            mocap_yaw_deg = yaw_from_quat_deg(quat) if quat else float("nan")
            yaw_error_deg = (
                wrap_degrees(estimate_yaw_deg - mocap_yaw_deg)
                if estimate_yaw_deg is not None
                else float("nan")
            )
            print(
                f"[validate] mocap=({mocap_position[0]:+.3f}, {mocap_position[1]:+.3f}, {mocap_position[2]:+.3f}) "
                f"estimate=({estimate_position[0]:+.3f}, {estimate_position[1]:+.3f}, {estimate_position[2]:+.3f}) "
                f"error={error:.3f}m yaw_mocap={mocap_yaw_deg:+.1f} "
                f"yaw_est={estimate_yaw_deg:+.1f} yaw_err={yaw_error_deg:+.1f}"
            )
            last_print = now
        time.sleep(MONITOR_PERIOD_S)


def figure8_points(start_position, height, radius_x, radius_y, period_s, count):
    points = []
    z = start_position[2] + height
    for index in range(count):
        phase = 2.0 * math.pi * index / count
        points.append((
            start_position[0] + radius_x * math.sin(phase),
            start_position[1] + radius_y * math.sin(phase) * math.cos(phase),
            z,
        ))
    return points


def planned_points(args, start_position):
    z = start_position[2] + args.height
    hover = (start_position[0], start_position[1], z)
    if args.mode == "point":
        if abs(args.dx) < 1.0e-6 and abs(args.dy) < 1.0e-6:
            return [hover]
        target = (start_position[0] + args.dx, start_position[1] + args.dy, z)
        return [hover, target, hover]
    return [hover] + figure8_points(
        start_position,
        args.height,
        args.figure8_radius_x,
        args.figure8_radius_y,
        args.figure8_period,
        args.figure8_points,
    ) + [hover]


def validate_planned_path(args, start_position, bounds):
    points = planned_points(args, start_position)
    bounds.require_path(points)
    for point in points:
        if point[2] - start_position[2] > MAX_HEIGHT_ABOVE_START_M:
            raise RuntimeError("Planned path exceeds max height above start")
        if abs(point[0] - start_position[0]) > MAX_X_FROM_START_M:
            raise RuntimeError("Planned path exceeds max x offset from start")
        if abs(point[1] - start_position[1]) > MAX_Y_FROM_START_M:
            raise RuntimeError("Planned path exceeds max y offset from start")
        if distance_2d(point, start_position) > MAX_RADIUS_FROM_START_M:
            raise RuntimeError("Planned path exceeds max radius from start")
    return points


def emergency_motor_cut(cf):
    print("[SAFETY] Emergency motor cut: disarm, stop, zero thrust, then cleanup.")
    try:
        cf.platform.send_arming_request(False)
    except Exception:
        pass
    try:
        cf.high_level_commander.stop()
    except Exception:
        pass
    try:
        cf.commander.send_stop_setpoint()
    except Exception:
        pass
    for _ in range(EMERGENCY_ZERO_THRUST_PACKETS):
        try:
            cf.commander.send_setpoint(0.0, 0.0, 0.0, 0)
        except Exception:
            pass
        try:
            cf.commander.send_stop_setpoint()
        except Exception:
            pass
        time.sleep(EMERGENCY_ZERO_THRUST_PERIOD_S)
    try:
        cf.param.set_value("commander.enHighLevel", "0")
    except Exception:
        pass
    try:
        cf.platform.send_arming_request(False)
    except Exception:
        pass


def guarded_land_or_stop(cf, args, start_position, immediate_stop=False):
    try:
        if immediate_stop:
            emergency_motor_cut(cf)
            return
        print("[SAFETY] Landing to start z...")
        cf.high_level_commander.land(start_position[2], args.land_duration)
        time.sleep(args.land_duration + 0.5)
        cf.high_level_commander.stop()
    except Exception as exc:
        print(f"[WARN] Landing/stop failed: {exc}")
        try:
            cf.high_level_commander.stop()
        except Exception:
            pass
        try:
            cf.commander.send_stop_setpoint()
        except Exception:
            pass
    finally:
        try:
            cf.platform.send_arming_request(False)
        except Exception:
            pass


def run_cut_test(cf):
    print("[CUT-TEST] Props off only. Arming; press Ctrl+C to test emergency cut.")
    cf.platform.send_arming_request(True)
    while True:
        time.sleep(0.25)


def run_flight(cf, args, logger, mocap_state, estimate_state, start_position, bounds):
    points = planned_points(args, start_position)
    hover = points[0]
    hover_only = len(points) == 1

    print(f"[FLIGHT] Takeoff to z={hover[2]:.3f}")
    cf.high_level_commander.takeoff(hover[2], args.takeoff_duration)
    monitor(
        logger,
        mocap_state,
        estimate_state,
        start_position,
        hover,
        bounds,
        "takeoff",
        args.takeoff_duration + 0.5,
        hover_only=hover_only,
    )

    print(f"[FLIGHT] Hover for {args.hover_duration:.1f}s")
    monitor(
        logger,
        mocap_state,
        estimate_state,
        start_position,
        hover,
        bounds,
        "hover",
        args.hover_duration,
        hover_only=hover_only,
    )

    for index, target in enumerate(points[1:], start=1):
        segment_duration = args.move_duration
        if args.mode == "figure8":
            segment_duration = max(0.5, args.figure8_period / args.figure8_points)
        print(
            f"[FLIGHT] go_to {index}/{len(points) - 1}: "
            f"x={target[0]:.3f}, y={target[1]:.3f}, z={target[2]:.3f}"
        )
        cf.high_level_commander.go_to(
            target[0],
            target[1],
            target[2],
            0.0,
            segment_duration,
            relative=False,
        )
        monitor(
            logger,
            mocap_state,
            estimate_state,
            start_position,
            target,
            bounds,
            "go_to",
            segment_duration + 0.2,
            hover_only=hover_only,
        )

    guarded_land_or_stop(cf, args, start_position)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--mocap-host", default=DEFAULT_MOCAP_HOST)
    parser.add_argument("--rigid-body", default=DEFAULT_RIGID_BODY_NAME)
    parser.add_argument("--pose-mode", choices=("extpos", "extpose"), default=DEFAULT_POSE_MODE)
    parser.add_argument("--mode", choices=("validate", "cut-test", "point", "figure8"), default="point")
    parser.add_argument("--height", type=float, default=DEFAULT_HEIGHT_M)
    parser.add_argument("--dx", type=float, default=DEFAULT_DX_M)
    parser.add_argument("--dy", type=float, default=DEFAULT_DY_M)
    parser.add_argument("--takeoff-duration", type=float, default=DEFAULT_TAKEOFF_DURATION_S)
    parser.add_argument("--move-duration", type=float, default=DEFAULT_MOVE_DURATION_S)
    parser.add_argument("--hover-duration", type=float, default=DEFAULT_HOVER_DURATION_S)
    parser.add_argument("--land-duration", type=float, default=DEFAULT_LAND_DURATION_S)
    parser.add_argument("--figure8-radius-x", type=float, default=0.04)
    parser.add_argument("--figure8-radius-y", type=float, default=0.03)
    parser.add_argument("--figure8-period", type=float, default=32.0)
    parser.add_argument("--figure8-points", type=int, default=16)
    parser.add_argument("--validate-duration", type=float, default=20.0)
    parser.add_argument("--x-min", type=float, default=DEFAULT_X_MIN)
    parser.add_argument("--x-max", type=float, default=DEFAULT_X_MAX)
    parser.add_argument("--y-min", type=float, default=DEFAULT_Y_MIN)
    parser.add_argument("--y-max", type=float, default=DEFAULT_Y_MAX)
    parser.add_argument("--z-min", type=float, default=DEFAULT_Z_MIN)
    parser.add_argument("--z-max", type=float, default=DEFAULT_Z_MAX)
    parser.add_argument("--safety-margin", type=float, default=0.20)
    parser.add_argument("--max-yaw-error-deg", type=float, default=MAX_PREFLIGHT_YAW_ERROR_DEG)
    parser.add_argument("--max-extpose-yaw-jump-deg", type=float, default=MAX_EXTPOSE_YAW_JUMP_DEG)
    parser.add_argument("--yaw-jump-position-gate", type=float, default=YAW_JUMP_POSITION_GATE_M)
    parser.add_argument(
        "--allow-extpos-point",
        action="store_true",
        help="Allow point flight with position-only extpos after yaw agreement check.",
    )
    parser.add_argument(
        "--skip-yaw-check",
        action="store_true",
        help="Skip preflight yaw agreement check. Unsafe; validation/debug only.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.mode == "figure8":
        raise RuntimeError("Figure-8 mode is disabled until point mode is proven stable")
    if args.mode == "point" and args.pose_mode == "extpos" and not args.allow_extpos_point:
        raise RuntimeError(
            "Point mode with --pose-mode extpos is blocked by default because yaw is not "
            "externally constrained. Run yaw validation first, then use --pose-mode extpose "
            "after quaternion validation or pass --allow-extpos-point for a guarded debug test."
        )

    bounds = Bounds(
        args.x_min,
        args.x_max,
        args.y_min,
        args.y_max,
        args.z_min,
        args.z_max,
        args.safety_margin,
    )
    logger = CsvLogger(args.mode)
    mocap_state = MocapState()
    estimate_state = EstimateState()
    mocap_reader = MocapReader(args.mocap_host, args.rigid_body, mocap_state)
    pose_stats = PoseStreamStats()
    logger.pose_stats = pose_stats
    estimate_logconf = None
    cf = None
    start_position = None

    print("=" * 72)
    print("MOCAP HIGH-LEVEL COMMANDER POINT TEST")
    print("=" * 72)
    print(f"URI: {args.uri}")
    print(f"Mocap: {args.rigid_body}@{args.mocap_host}")
    print(f"Mode: {args.mode}, pose streaming: {args.pose_mode}")
    print(f"Default point move: dx={args.dx:.3f}m, dy={args.dy:.3f}m, height={args.height:.3f}m")
    print("Close cfclient first. Keep a physical power-off option ready.")
    print("=" * 72)

    try:
        mocap_reader.start()
        start_position = wait_for_fresh_pose(mocap_state, mocap_reader)
        require_stable_pose(mocap_state)
        safe, reason = bounds.check(start_position)
        if not safe:
            raise RuntimeError(f"Start position is not safe: {reason}")
        if args.mode == "point":
            path = validate_planned_path(args, start_position, bounds)
            print(f"[INFO] Planned path validated with {len(path)} points.")
        elif args.mode == "cut-test":
            print("[INFO] Emergency cut test mode: props off, no flight commands.")
        else:
            print("[INFO] Estimator validation mode: no arming or flight commands.")

        input("Press ENTER to connect Crazyflie, or Ctrl+C to abort...")
        cflib.crtp.init_drivers()
        with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
            cf = scf.cf
            print("[INFO] Crazyflie connected.")
            estimate_logconf = setup_estimate_logger(cf, estimate_state)
            time.sleep(0.8)
            require_battery(estimate_state)

            pose_streamer = PoseStreamer(
                cf,
                args.pose_mode,
                args.max_extpose_yaw_jump_deg,
                args.yaw_jump_position_gate,
                pose_stats,
            )
            mocap_reader.on_pose = pose_streamer.send

            print("[INFO] Configuring estimator and high-level commander...")
            cf.param.set_value("stabilizer.estimator", "2")
            cf.param.set_value("commander.enHighLevel", "1")
            if args.pose_mode == "extpose":
                cf.param.set_value("locSrv.extQuatStdDev", ORIENTATION_STD_DEV)
            time.sleep(0.5)

            print("[INFO] Resetting estimator while mocap is streaming...")
            reset_estimator(cf)
            time.sleep(1.0)
            require_estimator_agreement(mocap_state, estimate_state)
            if args.mode == "point" and not args.skip_yaw_check:
                require_yaw_agreement(mocap_state, estimate_state, args.max_yaw_error_deg)
            elif args.mode == "point":
                print("[WARN] Preflight yaw check skipped by operator request.")

            try:
                if args.mode == "validate":
                    run_estimator_validation(args, logger, mocap_state, estimate_state, start_position)
                    print("[DONE] Estimator validation complete. No arming command was sent.")
                elif args.mode == "cut-test":
                    input("PROPS OFF. Press ENTER to arm for emergency-cut test, then press Ctrl+C...")
                    run_cut_test(cf)
                else:
                    input("Press ENTER to arm and fly the guarded hover test, or Ctrl+C to abort...")
                    cf.platform.send_arming_request(True)
                    time.sleep(0.5)
                    run_flight(cf, args, logger, mocap_state, estimate_state, start_position, bounds)
                    print("[DONE] Flight sequence complete.")
            except KeyboardInterrupt:
                print("\n[SAFETY] Operator abort inside active Crazyflie link.")
                guarded_land_or_stop(cf, args, start_position, immediate_stop=True)
                logger.write({"phase": "abort", "stop_reason": "operator_abort"})
                return
            except GuardTrip as exc:
                print(f"\n[SAFETY] Guard tripped inside active Crazyflie link: {exc.reason}")
                guarded_land_or_stop(cf, args, start_position, immediate_stop=exc.immediate_stop)
                log_monitor_row(
                    logger,
                    mocap_state,
                    estimate_state,
                    start_position,
                    start_position,
                    "guard",
                    exc.reason,
                )
                return
    except KeyboardInterrupt:
        print("\n[SAFETY] Operator abort.")
        if cf is not None and start_position is not None:
            guarded_land_or_stop(cf, args, start_position, immediate_stop=True)
        logger.write({"phase": "abort", "stop_reason": "operator_abort"})
    except GuardTrip as exc:
        print(f"\n[SAFETY] Guard tripped: {exc.reason}")
        if cf is not None and start_position is not None:
            guarded_land_or_stop(cf, args, start_position, immediate_stop=exc.immediate_stop)
        if start_position is not None:
            log_monitor_row(
                logger,
                mocap_state,
                estimate_state,
                start_position,
                start_position,
                "guard",
                exc.reason,
            )
        else:
            logger.write({"phase": "guard", "stop_reason": exc.reason})
    except Exception as exc:
        print(f"\n[SAFETY] Error: {exc}")
        if cf is not None and start_position is not None:
            guarded_land_or_stop(cf, args, start_position)
        logger.write({"phase": "error", "stop_reason": str(exc)})
        raise
    finally:
        if estimate_logconf is not None:
            try:
                estimate_logconf.stop()
            except Exception:
                pass
        mocap_reader.close()
        stats = pose_stats.snapshot()
        logger.close()
        print(
            "[DONE] Pose stream: "
            f"extpose={stats['extpose_packets']}, "
            f"extpos={stats['extpos_packets']}, "
            f"rejected_orientation={stats['rejected_extpose_orientation']}"
        )
        print(f"[DONE] Wrote log: {logger.output_path}")


if __name__ == "__main__":
    main()
