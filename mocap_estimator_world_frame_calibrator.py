#!/usr/bin/env python3
"""
Guided no-flight mocap local-frame and estimator position validator.

The validator captures a local origin, transforms raw VRPN positions into an
explicit Crazyflie local frame, streams only extpos, resets the Kalman
estimator, and checks stateEstimate.x/y/z against the transformed coordinates.
It then guides hand-movement tests for left/right, front/back, and up/down.
During all checks the drone must remain level and nose-front; stateEstimate yaw
must align with local +X at reset and remain near that post-reset baseline so
the local X/Y convention is not validated with an unnoticed heading change.

It never arms the Crazyflie and never sends motor or commander setpoints.
"""

import argparse
import csv
import math
import statistics
import time
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from threading import Lock, Thread


DEFAULT_URI = "radio://0/80/2M"
DEFAULT_HOST_NAME = "192.168.1.42:3883"
DEFAULT_RIGID_BODY_NAME = "crazyflie_21"
DEFAULT_OUTPUT_DIR = "flight_logs"
LOG_PERIOD_MS = 100
MOCAP_TIMEOUT_S = 8.0
POSE_STALE_TIMEOUT_S = 0.30
ESTIMATE_STALE_TIMEOUT_S = 0.50
DEFAULT_HOLD_DURATION_S = 3.0
DEFAULT_ORIGIN_HOLD_DURATION_S = 2.0
DEFAULT_RATE_HZ = 20.0
DEFAULT_MAX_ORIGIN_SPREAD_M = 0.01
DEFAULT_MIN_MOVEMENT_M = 0.08
DEFAULT_MAX_CROSS_AXIS_M = 0.05
DEFAULT_MAX_RETURN_ERROR_M = 0.05
DEFAULT_MAX_ESTIMATOR_ERROR_M = 0.05
DEFAULT_CONVERGENCE_DURATION_S = 2.0
DEFAULT_CONVERGENCE_TIMEOUT_S = 10.0
DEFAULT_ATTITUDE_BASELINE_DURATION_S = 2.0
DEFAULT_ATTITUDE_STABILITY_DURATION_S = 1.0
DEFAULT_ATTITUDE_STABILITY_TIMEOUT_S = 8.0
DEFAULT_MAX_LEVEL_ERROR_DEG = 5.0
DEFAULT_MAX_YAW_DRIFT_DEG = 5.0
DEFAULT_EXPECTED_NOSE_FRONT_YAW_DEG = 0.0
DEFAULT_MAX_YAW_ALIGNMENT_ERROR_DEG = 5.0
DEFAULT_MIN_SAMPLES = 20
ROBUST_PERCENTILE = 90.0

AXIS_NAMES = ("x", "y", "z")
AXIS_SPECS = ("pos-x", "neg-x", "pos-y", "neg-y", "pos-z", "neg-z")


@dataclass(frozen=True)
class AxisRule:
    source_index: int
    sign: float
    spec: str


@dataclass(frozen=True)
class MovementPhase:
    name: str
    description: str
    axis: int | None
    sign: int


@dataclass(frozen=True)
class AttitudeBaseline:
    yaw_deg: float
    expected_yaw_deg: float = DEFAULT_EXPECTED_NOSE_FRONT_YAW_DEG


MOVEMENT_PHASES = (
    MovementPhase("left", "move the drone physically LEFT", 1, 1),
    MovementPhase("center_after_left", "return to the captured center/origin", None, 0),
    MovementPhase("right", "move the drone physically RIGHT", 1, -1),
    MovementPhase("center_after_right", "return to the captured center/origin", None, 0),
    MovementPhase("front", "move the drone physically toward cage FRONT", 0, 1),
    MovementPhase("center_after_front", "return to the captured center/origin", None, 0),
    MovementPhase("back", "move the drone physically toward cage BACK", 0, -1),
    MovementPhase("center_after_back", "return to the captured center/origin", None, 0),
    MovementPhase("up", "move the drone physically UP", 2, 1),
    MovementPhase("center_after_up", "return to the captured center/origin", None, 0),
    MovementPhase("down", "move the drone physically DOWN below the captured origin", 2, -1),
    MovementPhase("center_after_down", "return to the captured center/origin", None, 0),
)


def load_runtime_modules():
    import cflib.crtp
    import motioncapture
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    from cflib.utils.reset_estimator import reset_estimator

    return {
        "cflib_crtp": cflib.crtp,
        "motioncapture": motioncapture,
        "Crazyflie": Crazyflie,
        "LogConfig": LogConfig,
        "SyncCrazyflie": SyncCrazyflie,
        "reset_estimator": reset_estimator,
    }


def is_finite_position(position):
    return (
        position is not None
        and len(position) == 3
        and all(isinstance(value, Real) and math.isfinite(value) for value in position)
    )


def distance_3d(left, right):
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def numeric_values(values):
    converted = []
    for value in values:
        if isinstance(value, Real) and math.isfinite(float(value)):
            converted.append(float(value))
    return converted


def median(values):
    values = numeric_values(values)
    return statistics.median(values) if values else math.nan


def percentile(values, percentile_value):
    values = sorted(numeric_values(values))
    if not values:
        return math.nan
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * percentile_value / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[lower]
    weight = rank - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def angle_error_deg(actual, expected):
    return (actual - expected + 180.0) % 360.0 - 180.0


def circular_median_deg(values):
    values = numeric_values(values)
    if not values:
        return math.nan
    reference = values[0]
    unwrapped = [reference + angle_error_deg(value, reference) for value in values]
    return (statistics.median(unwrapped) + 180.0) % 360.0 - 180.0


def parse_axis_rule(spec):
    if spec not in AXIS_SPECS:
        raise ValueError(f"invalid axis mapping {spec!r}")
    sign_name, axis_name = spec.split("-")
    return AxisRule(
        AXIS_NAMES.index(axis_name),
        1.0 if sign_name == "pos" else -1.0,
        spec,
    )


class LocalFrameTransform:
    def __init__(self, origin, axis_specs):
        if not is_finite_position(origin):
            raise ValueError("local-frame origin must contain three finite values")
        self.origin = tuple(float(value) for value in origin)
        self.rules = tuple(parse_axis_rule(spec) for spec in axis_specs)
        source_indices = [rule.source_index for rule in self.rules]
        if len(set(source_indices)) != 3:
            raise ValueError("local-frame mappings must use each raw axis exactly once")
        matrix = [
            [
                rule.sign if rule.source_index == source_index else 0.0
                for source_index in range(3)
            ]
            for rule in self.rules
        ]
        determinant = (
            matrix[0][0] * (
                matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1]
            )
            - matrix[0][1] * (
                matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0]
            )
            + matrix[0][2] * (
                matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0]
            )
        )
        if determinant < 0.0:
            raise ValueError(
                "local-frame mapping is reflected/left-handed; determinant must be +1"
            )

    @property
    def specs(self):
        return tuple(rule.spec for rule in self.rules)

    def apply(self, raw_position):
        if not is_finite_position(raw_position):
            raise ValueError("mocap position must contain three finite values")
        delta = tuple(
            float(raw_position[index]) - self.origin[index] for index in range(3)
        )
        return tuple(rule.sign * delta[rule.source_index] for rule in self.rules)


class MocapState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.last_update = 0.0
        self.frame_count = 0
        self.stream_result = {
            "extpos_packet_sequence": 0,
            "extpos_sent_count": 0,
            "extpos_error_count": 0,
            "last_extpos_status": "not-streaming",
            "last_extpos_error": "",
            "stream_local_x": "",
            "stream_local_y": "",
            "stream_local_z": "",
        }

    def update(self, position, stream_result=None):
        with self._lock:
            self.position = tuple(float(value) for value in position)
            self.last_update = time.time()
            self.frame_count += 1
            if stream_result is not None:
                self.stream_result = dict(stream_result)

    def snapshot(self):
        with self._lock:
            return self.position, self.last_update, self.frame_count

    def snapshot_with_stream(self):
        with self._lock:
            return (
                self.position,
                self.last_update,
                self.frame_count,
                dict(self.stream_result),
            )


class EstimateState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.battery_voltage = 0.0
        self.attitude = None
        self.position_last_update = 0.0
        self.attitude_last_update = 0.0

    def update_position(self, x, y, z, battery_voltage):
        with self._lock:
            self.position = (x, y, z)
            self.battery_voltage = battery_voltage
            self.position_last_update = time.time()

    def update_attitude(self, roll, pitch, yaw):
        with self._lock:
            self.attitude = (roll, pitch, yaw)
            self.attitude_last_update = time.time()

    def snapshot(self):
        with self._lock:
            return (
                self.position,
                self.attitude,
                self.battery_voltage,
                self.position_last_update,
                self.attitude_last_update,
            )


class MocapReader(Thread):
    def __init__(self, motioncapture_module, host_name, body_name, state):
        super().__init__(daemon=True)
        self.motioncapture = motioncapture_module
        self.host_name = host_name
        self.body_name = body_name
        self.state = state
        self.on_position = None
        self.error = None
        self._stay_open = True
        self._mc = None
        self._mc_lock = Lock()

    @staticmethod
    def _release_connection(mc):
        if mc is None:
            return
        for method_name in ("close", "disconnect", "shutdown"):
            method = getattr(mc, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

    def close(self):
        self._stay_open = False
        self.on_position = None
        with self._mc_lock:
            mc = self._mc
            self._mc = None
        self._release_connection(mc)

    def run(self):
        mc = None
        try:
            mc = self.motioncapture.connect("vrpn", {"hostname": self.host_name})
            with self._mc_lock:
                self._mc = mc
            print(f"[INFO] Mocap connected, looking for '{self.body_name}'")
            announced = False
            while self._stay_open:
                mc.waitForNextFrame()
                body = mc.rigidBodies.get(self.body_name)
                if body is None:
                    continue
                if not announced:
                    print(f"[INFO] Found and tracking rigid body: {self.body_name}")
                    announced = True
                position = tuple(float(value) for value in body.position)
                callback = self.on_position
                stream_result = None
                if callback is not None:
                    callback(*position)
                    owner = getattr(callback, "__self__", None)
                    snapshot = getattr(owner, "snapshot", None)
                    if callable(snapshot):
                        stream_result = snapshot()
                self.state.update(position, stream_result)
                body = None
        except Exception as exc:
            if self._stay_open:
                self.error = exc
        finally:
            with self._mc_lock:
                if self._mc is mc:
                    self._mc = None
                    release_connection = True
                else:
                    release_connection = False
            if release_connection:
                self._release_connection(mc)
            mc = None


class ExtposSender:
    def __init__(self, cf, transform):
        self.cf = cf
        self.transform = transform
        self._lock = Lock()
        self.packet_sequence = 0
        self.sent_count = 0
        self.error_count = 0
        self.last_status = "not-streaming"
        self.last_error = ""
        self.last_local = None

    def send(self, x, y, z):
        with self._lock:
            self.packet_sequence += 1
            try:
                local = self.transform.apply((x, y, z))
                self.cf.extpos.send_extpos(*local)
            except Exception as exc:
                self.error_count += 1
                self.last_status = "error"
                self.last_error = str(exc)
                raise
            self.sent_count += 1
            self.last_status = "sent"
            self.last_error = ""
            self.last_local = local
            return local

    def snapshot(self):
        with self._lock:
            return {
                "extpos_packet_sequence": self.packet_sequence,
                "extpos_sent_count": self.sent_count,
                "extpos_error_count": self.error_count,
                "last_extpos_status": self.last_status,
                "last_extpos_error": self.last_error,
                "stream_local_x": self.last_local[0] if self.last_local is not None else "",
                "stream_local_y": self.last_local[1] if self.last_local is not None else "",
                "stream_local_z": self.last_local[2] if self.last_local is not None else "",
            }


class CsvLogger:
    FIELDNAMES = [
        "wall_time_s", "elapsed_s", "phase", "phase_elapsed_s", "command",
        "expected_axis", "expected_sign",
        "raw_mocap_x", "raw_mocap_y", "raw_mocap_z",
        "local_mocap_x", "local_mocap_y", "local_mocap_z",
        "mocap_age_s", "mocap_frame_count",
        "origin_raw_x", "origin_raw_y", "origin_raw_z",
        "local_x_from", "local_y_from", "local_z_from",
        "extpos_packet_sequence", "extpos_sent_count", "extpos_error_count",
        "last_extpos_status", "last_extpos_error",
        "stream_local_x", "stream_local_y", "stream_local_z",
        "estimate_x", "estimate_y", "estimate_z", "estimate_age_s",
        "estimate_roll_deg", "estimate_pitch_deg", "estimate_yaw_deg",
        "estimate_attitude_age_s", "yaw_baseline_deg", "yaw_drift_deg",
        "expected_nose_front_yaw_deg", "yaw_alignment_error_deg",
        "estimate_error_m", "estimate_error_x_m", "estimate_error_y_m",
        "estimate_error_z_m", "battery_v",
    ]

    def __init__(self, output_path):
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output_path.open("w", newline="")
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


def setup_estimate_loggers(cf, LogConfig, estimate_state):
    position_log = LogConfig(name="EstimatorPosition", period_in_ms=LOG_PERIOD_MS)
    position_log.add_variable("pm.vbat", "float")
    position_log.add_variable("stateEstimate.x", "float")
    position_log.add_variable("stateEstimate.y", "float")
    position_log.add_variable("stateEstimate.z", "float")

    attitude_log = LogConfig(name="EstimatorAttitude", period_in_ms=LOG_PERIOD_MS)
    attitude_log.add_variable("stateEstimate.roll", "float")
    attitude_log.add_variable("stateEstimate.pitch", "float")
    attitude_log.add_variable("stateEstimate.yaw", "float")

    def on_position(timestamp, data, config):
        del timestamp, config
        estimate_state.update_position(
            data["stateEstimate.x"],
            data["stateEstimate.y"],
            data["stateEstimate.z"],
            data["pm.vbat"],
        )

    def on_attitude(timestamp, data, config):
        del timestamp, config
        estimate_state.update_attitude(
            data["stateEstimate.roll"],
            data["stateEstimate.pitch"],
            data["stateEstimate.yaw"],
        )

    def on_error(config, message):
        print(f"[WARN] Logger error from {config.name}: {message}")

    position_log.data_received_cb.add_callback(on_position)
    attitude_log.data_received_cb.add_callback(on_attitude)
    for logconf in (position_log, attitude_log):
        logconf.error_cb.add_callback(on_error)
        cf.log.add_config(logconf)
        logconf.start()
    return [position_log, attitude_log]


def wait_for_mocap(mocap_state, mocap_reader, timeout=MOCAP_TIMEOUT_S):
    print("[INFO] Waiting for fresh mocap position...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        position, last_update, frames = mocap_state.snapshot()
        if is_finite_position(position) and time.time() - last_update <= POSE_STALE_TIMEOUT_S:
            print(
                "[MOCAP] Fresh position: "
                f"({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) "
                f"frames={frames}"
            )
            return
        time.sleep(0.05)
    raise RuntimeError("No fresh mocap position received before timeout")


def wait_for_estimate(estimate_state, timeout=MOCAP_TIMEOUT_S):
    print("[INFO] Waiting for stateEstimate position and attitude data...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        position, attitude, battery, position_time, attitude_time = (
            estimate_state.snapshot()
        )
        now = time.time()
        if (
            is_finite_position(position)
            and is_finite_position(attitude)
            and now - position_time <= ESTIMATE_STALE_TIMEOUT_S
            and now - attitude_time <= ESTIMATE_STALE_TIMEOUT_S
        ):
            print(
                "[ESTIMATE] Fresh position: "
                f"({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) "
                f"attitude=({attitude[0]:.1f}, {attitude[1]:.1f}, "
                f"{attitude[2]:.1f})deg battery={battery:.2f}V"
            )
            return
        time.sleep(0.05)
    raise RuntimeError(
        "No fresh stateEstimate position and attitude received before timeout"
    )


def capture_origin(args, mocap_state, mocap_reader):
    print("")
    print("=" * 72)
    print("[ORIGIN] Hold the drone at cage center at a comfortable MID-HEIGHT.")
    print("[ORIGIN] Keep it physically LEVEL with its NOSE pointing cage FRONT.")
    print("[ORIGIN] Leave enough room to move it both upward and downward.")
    print(
        "[SAFETY] This Z=0 is validator-only. Never copy it into autonomous "
        "takeoff/landing code."
    )
    input("[ORIGIN] Once it is still, press ENTER to capture the local origin...")
    samples = []
    deadline = time.time() + args.origin_hold_duration
    while time.time() < deadline:
        if mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        position, last_update, _ = mocap_state.snapshot()
        if not is_finite_position(position) or time.time() - last_update > args.pose_stale_timeout:
            raise RuntimeError("Mocap became stale while capturing the local origin")
        samples.append(position)
        time.sleep(1.0 / args.rate_hz)
    if len(samples) < args.min_samples:
        raise RuntimeError(f"Only {len(samples)} origin samples; need {args.min_samples}")
    ranges = tuple(
        max(row[index] for row in samples) - min(row[index] for row in samples)
        for index in range(3)
    )
    if max(ranges) > args.max_origin_spread_m:
        raise RuntimeError(
            f"Origin moved too much: ranges={ranges[0]:.3f}/"
            f"{ranges[1]:.3f}/{ranges[2]:.3f}m"
        )
    origin = tuple(statistics.median(row[index] for row in samples) for index in range(3))
    print(
        f"[ORIGIN] Captured raw origin=({origin[0]:.3f}, "
        f"{origin[1]:.3f}, {origin[2]:.3f})"
    )
    return origin


def capture_post_reset_attitude_baseline(
    args, estimate_state, mocap_reader=None,
    clock=time.monotonic, sleep=time.sleep,
):
    print(
        "[FRAME] Keep the drone physically LEVEL and NOSE-FRONT while the "
        "post-reset yaw baseline is measured."
    )
    samples = []
    deadline = clock() + args.attitude_baseline_duration
    while clock() < deadline:
        if mocap_reader is not None and mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        _, attitude, _, _, attitude_time = estimate_state.snapshot()
        if (
            not is_finite_position(attitude)
            or time.time() - attitude_time > ESTIMATE_STALE_TIMEOUT_S
        ):
            raise RuntimeError(
                "Estimator attitude became stale while capturing yaw baseline"
        )
        samples.append(attitude)
        sleep(1.0 / args.rate_hz)
    if len(samples) < args.min_samples:
        raise RuntimeError(
            f"Only {len(samples)} attitude baseline samples; need {args.min_samples}"
        )
    roll_error = percentile(
        (abs(sample[0]) for sample in samples), ROBUST_PERCENTILE
    )
    pitch_error = percentile(
        (abs(sample[1]) for sample in samples), ROBUST_PERCENTILE
    )
    if max(roll_error, pitch_error) > args.max_level_error_deg:
        raise RuntimeError(
            "Drone was not level during post-reset baseline: "
            f"p90 roll/pitch={roll_error:.1f}/{pitch_error:.1f}deg"
        )
    yaw_baseline = circular_median_deg(sample[2] for sample in samples)
    yaw_spread = percentile(
        (abs(angle_error_deg(sample[2], yaw_baseline)) for sample in samples),
        ROBUST_PERCENTILE,
    )
    if yaw_spread > args.max_yaw_drift_deg:
        raise RuntimeError(
            f"Post-reset yaw was unstable: p90 drift={yaw_spread:.1f}deg"
        )
    alignment_error = abs(angle_error_deg(
        yaw_baseline, args.expected_nose_front_yaw_deg
    ))
    if alignment_error > args.max_yaw_alignment_error_deg:
        raise RuntimeError(
            f"Nose-front yaw baseline {yaw_baseline:.1f}deg is not aligned "
            f"with local +X expectation {args.expected_nose_front_yaw_deg:.1f}deg; "
            f"error={alignment_error:.1f}deg"
        )
    print(
        f"[FRAME] Post-reset nose-front yaw baseline={yaw_baseline:.1f}deg; "
        f"alignment error={alignment_error:.1f}deg; p90 drift={yaw_spread:.1f}deg"
    )
    return AttitudeBaseline(yaw_baseline, args.expected_nose_front_yaw_deg)


def require_attitude_stability(
    args, estimate_state, baseline, mocap_reader=None,
    clock=time.monotonic, sleep=time.sleep,
):
    print(
        f"[VERIFY] Requiring level attitude and yaw within "
        f"{args.max_yaw_drift_deg:.1f}deg of the post-reset baseline for "
        f"{args.attitude_stability_duration:.1f}s"
    )
    deadline = clock() + args.attitude_stability_timeout
    stable_since = None
    last_detail = "stale/unavailable"
    while clock() < deadline:
        if mocap_reader is not None and mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        _, attitude, _, _, attitude_time = estimate_state.snapshot()
        fresh = (
            is_finite_position(attitude)
            and time.time() - attitude_time <= ESTIMATE_STALE_TIMEOUT_S
        )
        if fresh:
            roll, pitch, yaw = attitude
            yaw_drift = abs(angle_error_deg(yaw, baseline.yaw_deg))
            last_detail = (
                f"roll={roll:.1f}deg pitch={pitch:.1f}deg "
                f"yaw_drift={yaw_drift:.1f}deg"
            )
            stable = (
                abs(roll) <= args.max_level_error_deg
                and abs(pitch) <= args.max_level_error_deg
                and yaw_drift <= args.max_yaw_drift_deg
            )
        else:
            stable = False
        if stable:
            if stable_since is None:
                stable_since = clock()
            if clock() - stable_since >= args.attitude_stability_duration:
                print(f"[VERIFY] Attitude stable; {last_detail}")
                return
        else:
            stable_since = None
        sleep(0.05)
    raise RuntimeError(
        "Drone did not remain level/nose-front relative to the post-reset yaw "
        f"baseline; last {last_detail}"
    )


def make_row(
    started_at, phase, phase_started_at, command, expected_axis, expected_sign,
    mocap_state, estimate_state, transform, attitude_baseline,
):
    now = time.time()
    raw, mocap_time, frame_count, stream_result = mocap_state.snapshot_with_stream()
    estimate, attitude, battery, estimate_time, attitude_time = (
        estimate_state.snapshot()
    )
    local = transform.apply(raw) if is_finite_position(raw) else None
    error = (
        distance_3d(local, estimate)
        if local is not None and is_finite_position(estimate) else ""
    )
    error_components = (
        tuple(estimate[index] - local[index] for index in range(3))
        if error != "" else ("", "", "")
    )
    row = {
        "wall_time_s": now,
        "elapsed_s": now - started_at,
        "phase": phase,
        "phase_elapsed_s": now - phase_started_at,
        "command": command,
        "expected_axis": AXIS_NAMES[expected_axis] if expected_axis is not None else "origin",
        "expected_sign": expected_sign,
        "raw_mocap_x": raw[0] if raw is not None else "",
        "raw_mocap_y": raw[1] if raw is not None else "",
        "raw_mocap_z": raw[2] if raw is not None else "",
        "local_mocap_x": local[0] if local is not None else "",
        "local_mocap_y": local[1] if local is not None else "",
        "local_mocap_z": local[2] if local is not None else "",
        "mocap_age_s": now - mocap_time if mocap_time else "",
        "mocap_frame_count": frame_count,
        "origin_raw_x": transform.origin[0],
        "origin_raw_y": transform.origin[1],
        "origin_raw_z": transform.origin[2],
        "local_x_from": transform.specs[0],
        "local_y_from": transform.specs[1],
        "local_z_from": transform.specs[2],
        "estimate_x": estimate[0] if estimate is not None else "",
        "estimate_y": estimate[1] if estimate is not None else "",
        "estimate_z": estimate[2] if estimate is not None else "",
        "estimate_age_s": now - estimate_time if estimate_time else "",
        "estimate_roll_deg": attitude[0] if attitude is not None else "",
        "estimate_pitch_deg": attitude[1] if attitude is not None else "",
        "estimate_yaw_deg": attitude[2] if attitude is not None else "",
        "estimate_attitude_age_s": now - attitude_time if attitude_time else "",
        "yaw_baseline_deg": attitude_baseline.yaw_deg,
        "yaw_drift_deg": (
            abs(angle_error_deg(attitude[2], attitude_baseline.yaw_deg))
            if attitude is not None else ""
        ),
        "expected_nose_front_yaw_deg": attitude_baseline.expected_yaw_deg,
        "yaw_alignment_error_deg": abs(angle_error_deg(
            attitude_baseline.yaw_deg, attitude_baseline.expected_yaw_deg
        )),
        "estimate_error_m": error,
        "estimate_error_x_m": error_components[0],
        "estimate_error_y_m": error_components[1],
        "estimate_error_z_m": error_components[2],
        "battery_v": battery,
    }
    row.update(stream_result)
    return row


def require_position_convergence(
    args, mocap_state, estimate_state, transform, mocap_reader=None,
    clock=time.monotonic, sleep=time.sleep,
):
    print(
        f"[VERIFY] Requiring estimator/transformed-mocap error below "
        f"{args.max_estimator_error_m:.3f}m continuously for "
        f"{args.convergence_duration:.1f}s"
    )
    deadline = clock() + args.convergence_timeout
    stable_since = None
    last_error = math.inf
    while clock() < deadline:
        if mocap_reader is not None and mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        now = time.time()
        raw, mocap_time, _ = mocap_state.snapshot()
        estimate, _, _, estimate_time, _ = estimate_state.snapshot()
        fresh = (
            is_finite_position(raw)
            and is_finite_position(estimate)
            and now - mocap_time <= args.pose_stale_timeout
            and now - estimate_time <= ESTIMATE_STALE_TIMEOUT_S
        )
        last_error = distance_3d(transform.apply(raw), estimate) if fresh else math.inf
        if last_error < args.max_estimator_error_m:
            if stable_since is None:
                stable_since = clock()
            if clock() - stable_since >= args.convergence_duration:
                print(f"[VERIFY] Position converged; current error={last_error:.3f}m")
                return
        else:
            stable_since = None
        sleep(0.05)
    error_text = f"{last_error:.3f}m" if math.isfinite(last_error) else "stale/unavailable"
    raise RuntimeError(
        "Estimator did not converge to transformed mocap coordinates; "
        f"last error={error_text}"
    )


def validate_phase(rows, phase, args):
    fresh = [
        row for row in rows
        if isinstance(row.get("mocap_age_s"), Real)
        and row["mocap_age_s"] <= args.pose_stale_timeout
        and isinstance(row.get("estimate_age_s"), Real)
        and row["estimate_age_s"] <= ESTIMATE_STALE_TIMEOUT_S
        and isinstance(row.get("estimate_attitude_age_s"), Real)
        and row["estimate_attitude_age_s"] <= ESTIMATE_STALE_TIMEOUT_S
    ]
    if len(fresh) < args.min_samples:
        raise RuntimeError(
            f"{phase.name}: only {len(fresh)} fresh samples; need {args.min_samples}"
        )
    p90_error = percentile(
        (row["estimate_error_m"] for row in fresh), ROBUST_PERCENTILE
    )
    if p90_error > args.max_estimator_error_m:
        raise RuntimeError(
            f"{phase.name}: estimator/transformed-mocap p90 error "
            f"{p90_error:.3f}m exceeds {args.max_estimator_error_m:.3f}m"
        )
    roll_error = percentile(
        (abs(row["estimate_roll_deg"]) for row in fresh), ROBUST_PERCENTILE
    )
    pitch_error = percentile(
        (abs(row["estimate_pitch_deg"]) for row in fresh), ROBUST_PERCENTILE
    )
    yaw_drift = percentile(
        (row["yaw_drift_deg"] for row in fresh), ROBUST_PERCENTILE
    )
    if max(roll_error, pitch_error) > args.max_level_error_deg:
        raise RuntimeError(
            f"{phase.name}: drone was not level; p90 roll/pitch="
            f"{roll_error:.1f}/{pitch_error:.1f}deg"
        )
    if yaw_drift > args.max_yaw_drift_deg:
        raise RuntimeError(
            f"{phase.name}: yaw drift {yaw_drift:.1f}deg exceeds "
            f"{args.max_yaw_drift_deg:.1f}deg"
        )
    local_medians = tuple(
        median(row[f"local_mocap_{axis}"] for row in fresh) for axis in AXIS_NAMES
    )
    estimate_medians = tuple(
        median(row[f"estimate_{axis}"] for row in fresh) for axis in AXIS_NAMES
    )
    if phase.axis is None:
        local_radius = distance_3d(local_medians, (0.0, 0.0, 0.0))
        estimate_radius = distance_3d(estimate_medians, (0.0, 0.0, 0.0))
        if max(local_radius, estimate_radius) > args.max_return_error_m:
            raise RuntimeError(
                f"{phase.name}: return-to-origin error "
                f"mocap={local_radius:.3f}m estimate={estimate_radius:.3f}m"
            )
    else:
        local_primary = phase.sign * local_medians[phase.axis]
        estimate_primary = phase.sign * estimate_medians[phase.axis]
        if min(local_primary, estimate_primary) < args.min_movement_m:
            raise RuntimeError(
                f"{phase.name}: movement on local {AXIS_NAMES[phase.axis]} "
                f"was too small or had the wrong sign "
                f"(mocap={local_medians[phase.axis]:+.3f}m, "
                f"estimate={estimate_medians[phase.axis]:+.3f}m)"
            )
        cross_axes = [index for index in range(3) if index != phase.axis]
        cross_error = max(abs(local_medians[index]) for index in cross_axes)
        if cross_error > args.max_cross_axis_m:
            raise RuntimeError(
                f"{phase.name}: cross-axis mocap movement {cross_error:.3f}m "
                f"exceeds {args.max_cross_axis_m:.3f}m"
            )
    print(
        f"[PASS] {phase.name}: local=({local_medians[0]:+.3f}, "
        f"{local_medians[1]:+.3f}, {local_medians[2]:+.3f}) "
        f"estimate=({estimate_medians[0]:+.3f}, {estimate_medians[1]:+.3f}, "
        f"{estimate_medians[2]:+.3f}) p90_error={p90_error:.3f}m "
        f"p90_yaw_drift={yaw_drift:.1f}deg"
    )


def run_phase(
    args, logger, started_at, phase, mocap_state, estimate_state, transform,
    attitude_baseline, mocap_reader,
):
    print("")
    print("=" * 72)
    print(f"[MOVE] {phase.description}.")
    print("[MOVE] Keep the drone physically LEVEL and NOSE-FRONT.")
    if phase.axis is not None:
        print(
            f"[MOVE] Move at least {args.min_movement_m:.2f}m while minimizing "
            "motion on the other two axes."
        )
    input("[MOVE] Once it is still, press ENTER to verify and record...")
    require_position_convergence(
        args, mocap_state, estimate_state, transform, mocap_reader
    )
    require_attitude_stability(
        args, estimate_state, attitude_baseline, mocap_reader
    )
    print(f"[RECORD] {phase.name}: holding for {args.hold_duration:.1f}s")
    phase_started_at = time.time()
    rows = []
    next_sample = phase_started_at
    while time.time() - phase_started_at < args.hold_duration:
        if mocap_reader.error is not None:
            raise RuntimeError(f"Mocap reader failed: {mocap_reader.error}")
        now = time.time()
        if now < next_sample:
            time.sleep(min(0.01, next_sample - now))
            continue
        row = make_row(
            started_at, phase.name, phase_started_at, "hold-still",
            phase.axis, phase.sign, mocap_state, estimate_state, transform,
            attitude_baseline,
        )
        logger.write(row)
        rows.append(row)
        next_sample += 1.0 / args.rate_hz
    validate_phase(rows, phase, args)
    return rows


def run_movement_phases(
    args, logger, started_at, mocap_state, estimate_state, transform,
    attitude_baseline, mocap_reader,
):
    for phase in MOVEMENT_PHASES:
        run_phase(
            args, logger, started_at, phase, mocap_state, estimate_state,
            transform, attitude_baseline, mocap_reader,
        )


def shutdown_mocap_reader(reader, timeout=2.0):
    reader.on_position = None
    reader.close()
    if reader.ident is None:
        return
    reader.join(timeout=timeout)
    if reader.is_alive():
        raise RuntimeError("Mocap reader did not stop cleanly")


def make_output_path(output):
    if output:
        path = Path(output)
    else:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        path = Path(DEFAULT_OUTPUT_DIR) / f"mocap-local-frame-validator-{timestamp}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run(args):
    runtime = load_runtime_modules()
    runtime["cflib_crtp"].init_drivers()
    output_path = make_output_path(args.output)
    mocap_state = MocapState()
    estimate_state = EstimateState()
    reader = MocapReader(runtime["motioncapture"], args.host, args.body, mocap_state)
    logger = CsvLogger(output_path)
    estimate_logconfs = []

    print("=" * 72)
    print("NO-FLIGHT MOCAP POSITION-ONLY LOCAL-FRAME VALIDATOR")
    print("=" * 72)
    print(f"URI: {args.uri}")
    print(f"Rigid body: {args.body}@{args.host}")
    print(
        f"Mapping: local +X <- {args.local_x_from}, "
        f"local +Y <- {args.local_y_from}, local +Z <- {args.local_z_from}"
    )
    print(f"Output: {output_path}")
    print("This script streams extpos only. It never arms or commands motors.")
    print(
        "[SAFETY] Captured local Z=0 is mid-height and validator-only; "
        "flight must use a floor/start-referenced Z origin."
    )
    print("=" * 72)

    try:
        input("Press ENTER to connect mocap, or Ctrl+C to abort...")
        reader.start()
        wait_for_mocap(mocap_state, reader)
        origin = capture_origin(args, mocap_state, reader)
        transform = LocalFrameTransform(
            origin, (args.local_x_from, args.local_y_from, args.local_z_from)
        )

        input("Press ENTER to connect Crazyflie, or Ctrl+C to abort...")
        with runtime["SyncCrazyflie"](
            args.uri, cf=runtime["Crazyflie"](rw_cache="./cache")
        ) as scf:
            cf = scf.cf
            print("[INFO] Crazyflie connected.")
            estimate_logconfs = setup_estimate_loggers(
                cf, runtime["LogConfig"], estimate_state
            )
            sender = ExtposSender(cf, transform)
            reader.on_position = sender.send
            cf.param.set_value("stabilizer.estimator", "2")
            time.sleep(0.5)
            input(
                "[FRAME] Keep the drone LEVEL and NOSE-FRONT, then press "
                "ENTER to reset the estimator..."
            )
            print("[INFO] Resetting Kalman estimator while local extpos is streaming...")
            runtime["reset_estimator"](cf)
            time.sleep(args.settle_duration)
            wait_for_estimate(estimate_state)
            attitude_baseline = capture_post_reset_attitude_baseline(
                args, estimate_state, reader
            )
            require_position_convergence(
                args, mocap_state, estimate_state, transform, reader
            )
            require_attitude_stability(
                args, estimate_state, attitude_baseline, reader
            )

            started_at = time.time()
            origin_phase = MovementPhase(
                "origin_validation", "hold at the captured center/origin", None, 0
            )
            run_phase(
                args, logger, started_at, origin_phase, mocap_state,
                estimate_state, transform, attitude_baseline, reader,
            )
            run_movement_phases(
                args, logger, started_at, mocap_state, estimate_state,
                transform, attitude_baseline, reader,
            )
            print("")
            print(
                "[VALIDATION] PASS: all position axes/directions verified "
                "with stable level/nose-front yaw"
            )
    finally:
        for estimate_logconf in estimate_logconfs:
            try:
                estimate_logconf.stop()
            except Exception:
                pass
        try:
            shutdown_mocap_reader(reader)
        finally:
            logger.close()

    print("=" * 72)
    print("[DONE]")
    print(f"log: {output_path}")
    print(f"rows: {logger.rows}")
    print("=" * 72)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--host", default=DEFAULT_HOST_NAME)
    parser.add_argument("--body", default=DEFAULT_RIGID_BODY_NAME)
    parser.add_argument("--output")
    parser.add_argument("--local-x-from", choices=AXIS_SPECS, default="neg-y")
    parser.add_argument("--local-y-from", choices=AXIS_SPECS, default="pos-x")
    parser.add_argument("--local-z-from", choices=AXIS_SPECS, default="pos-z")
    parser.add_argument("--hold-duration", type=float, default=DEFAULT_HOLD_DURATION_S)
    parser.add_argument(
        "--origin-hold-duration", type=float,
        default=DEFAULT_ORIGIN_HOLD_DURATION_S,
    )
    parser.add_argument("--settle-duration", type=float, default=2.0)
    parser.add_argument("--rate-hz", type=float, default=DEFAULT_RATE_HZ)
    parser.add_argument(
        "--pose-stale-timeout", type=float, default=POSE_STALE_TIMEOUT_S
    )
    parser.add_argument(
        "--max-origin-spread-m", type=float, default=DEFAULT_MAX_ORIGIN_SPREAD_M
    )
    parser.add_argument("--min-movement-m", type=float, default=DEFAULT_MIN_MOVEMENT_M)
    parser.add_argument(
        "--max-cross-axis-m", type=float, default=DEFAULT_MAX_CROSS_AXIS_M
    )
    parser.add_argument(
        "--max-return-error-m", type=float, default=DEFAULT_MAX_RETURN_ERROR_M
    )
    parser.add_argument(
        "--max-estimator-error-m", type=float,
        default=DEFAULT_MAX_ESTIMATOR_ERROR_M,
    )
    parser.add_argument(
        "--convergence-duration", type=float,
        default=DEFAULT_CONVERGENCE_DURATION_S,
    )
    parser.add_argument(
        "--convergence-timeout", type=float,
        default=DEFAULT_CONVERGENCE_TIMEOUT_S,
    )
    parser.add_argument(
        "--attitude-baseline-duration", type=float,
        default=DEFAULT_ATTITUDE_BASELINE_DURATION_S,
    )
    parser.add_argument(
        "--attitude-stability-duration", type=float,
        default=DEFAULT_ATTITUDE_STABILITY_DURATION_S,
    )
    parser.add_argument(
        "--attitude-stability-timeout", type=float,
        default=DEFAULT_ATTITUDE_STABILITY_TIMEOUT_S,
    )
    parser.add_argument(
        "--max-level-error-deg", type=float,
        default=DEFAULT_MAX_LEVEL_ERROR_DEG,
    )
    parser.add_argument(
        "--max-yaw-drift-deg", type=float,
        default=DEFAULT_MAX_YAW_DRIFT_DEG,
    )
    parser.add_argument(
        "--expected-nose-front-yaw-deg", type=float,
        default=DEFAULT_EXPECTED_NOSE_FRONT_YAW_DEG,
    )
    parser.add_argument(
        "--max-yaw-alignment-error-deg", type=float,
        default=DEFAULT_MAX_YAW_ALIGNMENT_ERROR_DEG,
    )
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    args = parser.parse_args(argv)

    LocalFrameTransform(
        (0.0, 0.0, 0.0),
        (args.local_x_from, args.local_y_from, args.local_z_from),
    )
    positive_values = (
        ("--hold-duration", args.hold_duration),
        ("--origin-hold-duration", args.origin_hold_duration),
        ("--rate-hz", args.rate_hz),
        ("--pose-stale-timeout", args.pose_stale_timeout),
        ("--max-origin-spread-m", args.max_origin_spread_m),
        ("--min-movement-m", args.min_movement_m),
        ("--max-cross-axis-m", args.max_cross_axis_m),
        ("--max-return-error-m", args.max_return_error_m),
        ("--max-estimator-error-m", args.max_estimator_error_m),
        ("--convergence-duration", args.convergence_duration),
        ("--convergence-timeout", args.convergence_timeout),
        ("--attitude-baseline-duration", args.attitude_baseline_duration),
        ("--attitude-stability-duration", args.attitude_stability_duration),
        ("--attitude-stability-timeout", args.attitude_stability_timeout),
        ("--max-level-error-deg", args.max_level_error_deg),
        ("--max-yaw-drift-deg", args.max_yaw_drift_deg),
        ("--max-yaw-alignment-error-deg", args.max_yaw_alignment_error_deg),
    )
    for name, value in positive_values:
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
    if not math.isfinite(args.expected_nose_front_yaw_deg):
        raise ValueError("--expected-nose-front-yaw-deg must be finite")
    if args.settle_duration < 0.0:
        raise ValueError("--settle-duration must be non-negative")
    if args.convergence_timeout < args.convergence_duration:
        raise ValueError("--convergence-timeout must cover --convergence-duration")
    if args.attitude_stability_timeout < args.attitude_stability_duration:
        raise ValueError(
            "--attitude-stability-timeout must cover "
            "--attitude-stability-duration"
        )
    if args.min_samples <= 0:
        raise ValueError("--min-samples must be positive")
    if math.floor(args.hold_duration * args.rate_hz) < args.min_samples:
        raise ValueError(
            "--hold-duration and --rate-hz must allow at least --min-samples"
        )
    if math.floor(args.origin_hold_duration * args.rate_hz) < args.min_samples:
        raise ValueError(
            "--origin-hold-duration and --rate-hz must allow at least --min-samples"
        )
    if math.floor(args.attitude_baseline_duration * args.rate_hz) < args.min_samples:
        raise ValueError(
            "--attitude-baseline-duration and --rate-hz must allow at least "
            "--min-samples"
        )
    return args


if __name__ == "__main__":
    run(parse_args())
