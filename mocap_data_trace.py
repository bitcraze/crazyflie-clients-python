#!/usr/bin/env python3
"""Trace OptiTrack/VRPN data and optional Crazyflie extpos streaming.

Default mode is receive-only: it connects to VRPN, prints/logs raw rigid-body
position and quaternion, and shows the local-frame interpretation used by the
current AIMS Lab scripts.

With --stream-extpos it also connects to the Crazyflie, sends the transformed
XYZ values through cf.extpos.send_extpos(...), and logs the exact outgoing XYZ
alongside stateEstimate telemetry. It never arms and never sends motor or
commander setpoints.
"""

import argparse
import csv
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_URI = "radio://0/80/2M"
DEFAULT_HOST = "192.168.1.42:3883"
DEFAULT_BODY = "crazyflie_21"
DEFAULT_OUTPUT_DIR = "flight_logs"
DEFAULT_PRINT_INTERVAL_S = 0.25
DEFAULT_ORIGIN_CAPTURE_DURATION_S = 2.0
DEFAULT_MAX_ORIGIN_SPREAD_M = 0.01
LOG_PERIOD_MS = 100

AXIS_NAMES = ("x", "y", "z")
AXIS_SPECS = ("pos-x", "neg-x", "pos-y", "neg-y", "pos-z", "neg-z")


@dataclass(frozen=True)
class AxisRule:
    source_index: int
    sign: float
    spec: str


@dataclass(frozen=True)
class Quat:
    x: float
    y: float
    z: float
    w: float


class LocalFrameTransform:
    def __init__(self, origin, axis_specs):
        self.origin = tuple(float(value) for value in origin)
        self.rules = tuple(parse_axis_rule(spec) for spec in axis_specs)
        source_indices = [rule.source_index for rule in self.rules]
        if len(set(source_indices)) != 3:
            raise ValueError("local-frame mappings must use each raw axis exactly once")
        if self.determinant() < 0.0:
            raise ValueError("local-frame mapping is reflected/left-handed")

    @property
    def specs(self):
        return tuple(rule.spec for rule in self.rules)

    def determinant(self):
        matrix = [
            [
                rule.sign if rule.source_index == source_index else 0.0
                for source_index in range(3)
            ]
            for rule in self.rules
        ]
        return (
            matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
            - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
            + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
        )

    def apply(self, raw_position):
        delta = tuple(float(raw_position[index]) - self.origin[index] for index in range(3))
        return tuple(rule.sign * delta[rule.source_index] for rule in self.rules)


class EstimateState:
    def __init__(self):
        self.values = {}
        self.last_update = 0.0

    def update(self, values):
        self.values.update(values)
        self.last_update = time.time()

    def snapshot(self):
        return dict(self.values), self.last_update


class ExtposSender:
    def __init__(self, cf):
        self.cf = cf
        self.sent_count = 0
        self.error_count = 0
        self.last_error = ""

    def send(self, local_position):
        try:
            self.cf.extpos.send_extpos(*local_position)
        except Exception as exc:
            self.error_count += 1
            self.last_error = str(exc)
            raise
        self.sent_count += 1
        self.last_error = ""

    def snapshot(self):
        return {
            "extpos_sent_count": self.sent_count,
            "extpos_error_count": self.error_count,
            "extpos_last_error": self.last_error,
        }


def parse_axis_rule(spec):
    if spec not in AXIS_SPECS:
        raise ValueError(f"invalid axis mapping {spec!r}")
    sign_name, axis_name = spec.split("-")
    return AxisRule(
        AXIS_NAMES.index(axis_name),
        1.0 if sign_name == "pos" else -1.0,
        spec,
    )


def yaw_from_quat_deg(quat):
    siny_cosp = 2.0 * (quat.w * quat.z + quat.x * quat.y)
    cosy_cosp = 1.0 - 2.0 * (quat.y * quat.y + quat.z * quat.z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def distance(left, right):
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def finite_position(values):
    return (
        values is not None
        and len(values) == 3
        and all(value is not None and math.isfinite(float(value)) for value in values)
    )


def read_pose(mocap, body_name):
    mocap.waitForNextFrame()
    body = mocap.rigidBodies.get(body_name)
    if body is None:
        return None, None
    position = tuple(float(value) for value in body.position)
    rotation = body.rotation
    quat = Quat(float(rotation.x), float(rotation.y), float(rotation.z), float(rotation.w))
    return position, quat


def capture_origin(mocap, body_name, duration_s, max_spread_m):
    print(
        "[ORIGIN] Hold the drone still at the local zero/start pose "
        f"for {duration_s:.1f}s..."
    )
    samples = []
    deadline = time.time() + duration_s
    while time.time() < deadline:
        position, _ = read_pose(mocap, body_name)
        if position is not None:
            samples.append(position)
    if not samples:
        raise RuntimeError("no VRPN samples received during origin capture")
    ranges = [
        max(sample[index] for sample in samples) - min(sample[index] for sample in samples)
        for index in range(3)
    ]
    if max(ranges) > max_spread_m:
        raise RuntimeError(
            "origin moved too much during capture: "
            f"range=({ranges[0]:.4f}, {ranges[1]:.4f}, {ranges[2]:.4f})m"
        )
    origin = tuple(statistics.median(sample[index] for sample in samples) for index in range(3))
    print(f"[ORIGIN] raw=({origin[0]:+.4f}, {origin[1]:+.4f}, {origin[2]:+.4f})")
    return origin


def setup_estimate_logger(cf, LogConfig, estimate_state):
    logconf = LogConfig(name="TraceEstimate", period_in_ms=LOG_PERIOD_MS)
    for variable in (
        "stateEstimate.x",
        "stateEstimate.y",
        "stateEstimate.z",
        "stateEstimate.yaw",
        "pm.vbat",
    ):
        logconf.add_variable(variable, "float")

    def on_data(timestamp, data, logconf):
        del timestamp, logconf
        estimate_state.update(data)

    def on_error(logconf, message):
        print(f"[WARN] Logger error from {logconf.name}: {message}")

    cf.log.add_config(logconf)
    logconf.data_received_cb.add_callback(on_data)
    logconf.error_cb.add_callback(on_error)
    logconf.start()
    return logconf


def make_output_path(output):
    if output:
        path = Path(output)
    else:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        path = Path(DEFAULT_OUTPUT_DIR) / f"mocap-data-trace-{timestamp}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def release_connection(connection):
    for name in ("close", "disconnect", "shutdown"):
        method = getattr(connection, name, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass
            return


def make_row(
    started_at,
    frame_count,
    raw_position,
    quat,
    local_position,
    transform,
    sent_position,
    sender,
    estimate_state,
):
    now = time.time()
    estimate, estimate_time = estimate_state.snapshot() if estimate_state else ({}, 0.0)
    estimate_position = (
        estimate.get("stateEstimate.x"),
        estimate.get("stateEstimate.y"),
        estimate.get("stateEstimate.z"),
    )
    estimate_error = (
        distance(local_position, estimate_position)
        if finite_position(local_position) and finite_position(estimate_position)
        else ""
    )
    row = {
        "wall_time_s": now,
        "elapsed_s": now - started_at,
        "frame_count": frame_count,
        "raw_mocap_x": raw_position[0],
        "raw_mocap_y": raw_position[1],
        "raw_mocap_z": raw_position[2],
        "mocap_qx": quat.x,
        "mocap_qy": quat.y,
        "mocap_qz": quat.z,
        "mocap_qw": quat.w,
        "mocap_yaw_deg": yaw_from_quat_deg(quat),
        "origin_raw_x": transform.origin[0],
        "origin_raw_y": transform.origin[1],
        "origin_raw_z": transform.origin[2],
        "local_x_from": transform.specs[0],
        "local_y_from": transform.specs[1],
        "local_z_from": transform.specs[2],
        "local_mocap_x": local_position[0],
        "local_mocap_y": local_position[1],
        "local_mocap_z": local_position[2],
        "sent_extpos_x": sent_position[0] if sent_position is not None else "",
        "sent_extpos_y": sent_position[1] if sent_position is not None else "",
        "sent_extpos_z": sent_position[2] if sent_position is not None else "",
        "stateEstimate.x": estimate.get("stateEstimate.x", ""),
        "stateEstimate.y": estimate.get("stateEstimate.y", ""),
        "stateEstimate.z": estimate.get("stateEstimate.z", ""),
        "stateEstimate.yaw": estimate.get("stateEstimate.yaw", ""),
        "pm.vbat": estimate.get("pm.vbat", ""),
        "estimate_age_s": now - estimate_time if estimate_time else "",
        "estimate_local_error_m": estimate_error,
    }
    row.update(
        sender.snapshot()
        if sender is not None
        else {"extpos_sent_count": 0, "extpos_error_count": 0, "extpos_last_error": ""}
    )
    return row


FIELDNAMES = [
    "wall_time_s",
    "elapsed_s",
    "frame_count",
    "raw_mocap_x",
    "raw_mocap_y",
    "raw_mocap_z",
    "mocap_qx",
    "mocap_qy",
    "mocap_qz",
    "mocap_qw",
    "mocap_yaw_deg",
    "origin_raw_x",
    "origin_raw_y",
    "origin_raw_z",
    "local_x_from",
    "local_y_from",
    "local_z_from",
    "local_mocap_x",
    "local_mocap_y",
    "local_mocap_z",
    "sent_extpos_x",
    "sent_extpos_y",
    "sent_extpos_z",
    "extpos_sent_count",
    "extpos_error_count",
    "extpos_last_error",
    "stateEstimate.x",
    "stateEstimate.y",
    "stateEstimate.z",
    "stateEstimate.yaw",
    "pm.vbat",
    "estimate_age_s",
    "estimate_local_error_m",
]


def print_row(row):
    sent = (
        "not-streaming"
        if row["sent_extpos_x"] == ""
        else (
            f"sent=({row['sent_extpos_x']:+.3f}, "
            f"{row['sent_extpos_y']:+.3f}, {row['sent_extpos_z']:+.3f})"
        )
    )
    estimate = (
        "estimate=no-data"
        if row["stateEstimate.x"] == ""
        else (
            f"estimate=({row['stateEstimate.x']:+.3f}, "
            f"{row['stateEstimate.y']:+.3f}, {row['stateEstimate.z']:+.3f}) "
            f"err={row['estimate_local_error_m']:.3f}m"
        )
    )
    print(
        f"raw=({row['raw_mocap_x']:+.3f}, {row['raw_mocap_y']:+.3f}, "
        f"{row['raw_mocap_z']:+.3f}) "
        f"quat=({row['mocap_qx']:+.3f}, {row['mocap_qy']:+.3f}, "
        f"{row['mocap_qz']:+.3f}, {row['mocap_qw']:+.3f}) "
        f"local=({row['local_mocap_x']:+.3f}, {row['local_mocap_y']:+.3f}, "
        f"{row['local_mocap_z']:+.3f}) {sent} {estimate}"
    )


def pulse_estimator_reset(cf):
    cf.param.set_value("kalman.resetEstimation", "1")
    time.sleep(0.1)
    cf.param.set_value("kalman.resetEstimation", "0")


def run_trace(args, mocap, cf=None, LogConfig=None):
    if args.capture_origin:
        origin = capture_origin(
            mocap, args.body, args.origin_capture_duration, args.max_origin_spread_m
        )
    else:
        origin = tuple(args.origin)
    transform = LocalFrameTransform(
        origin, (args.local_x_from, args.local_y_from, args.local_z_from)
    )

    output_path = make_output_path(args.output)
    estimate_state = EstimateState() if cf is not None else None
    sender = ExtposSender(cf) if cf is not None else None
    logconf = None
    estimator_reset = False

    print(f"[TRACE] Output: {output_path}")
    print(
        "[TRACE] Mapping: "
        f"local +X <- {args.local_x_from}, "
        f"local +Y <- {args.local_y_from}, local +Z <- {args.local_z_from}"
    )
    print(
        f"[TRACE] Origin raw=({origin[0]:+.4f}, {origin[1]:+.4f}, {origin[2]:+.4f})"
    )
    if cf is None:
        print("[TRACE] Receive-only mode; no Crazyflie packets will be sent.")
    else:
        print("[TRACE] Streaming cf.extpos.send_extpos(local_x, local_y, local_z).")
        print("[TRACE] This script never arms and never sends motor/commander setpoints.")
        logconf = setup_estimate_logger(cf, LogConfig, estimate_state)
        cf.param.set_value("stabilizer.estimator", "2")
        time.sleep(0.5)

    started_at = time.time()
    frame_count = 0
    last_print = 0.0
    deadline = started_at + args.duration if args.duration > 0.0 else None

    try:
        with output_path.open("w", newline="", encoding="ascii") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
            writer.writeheader()
            while deadline is None or time.time() < deadline:
                raw_position, quat = read_pose(mocap, args.body)
                if raw_position is None:
                    continue
                frame_count += 1
                local_position = transform.apply(raw_position)
                sent_position = None
                if sender is not None:
                    try:
                        sender.send(local_position)
                        sent_position = local_position
                        if args.reset_estimator and not estimator_reset and sender.sent_count >= 10:
                            print("[TRACE] Pulsing Kalman estimator reset after initial extpos packets...")
                            pulse_estimator_reset(cf)
                            estimator_reset = True
                    except Exception as exc:
                        print(f"[WARN] extpos send failed: {exc}")
                row = make_row(
                    started_at,
                    frame_count,
                    raw_position,
                    quat,
                    local_position,
                    transform,
                    sent_position,
                    sender,
                    estimate_state,
                )
                writer.writerow(row)
                output_file.flush()
                if time.time() - last_print >= args.print_interval:
                    print_row(row)
                    last_print = time.time()
    except KeyboardInterrupt:
        print("\n[TRACE] Stopped by operator.")
    finally:
        if logconf is not None:
            try:
                logconf.stop()
            except Exception:
                pass
    print(f"[TRACE] Done. Rows: {frame_count}. Log: {output_path}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--body", default=DEFAULT_BODY)
    parser.add_argument("--output")
    parser.add_argument("--duration", type=float, default=0.0, help="seconds; 0 means until Ctrl+C")
    parser.add_argument("--print-interval", type=float, default=DEFAULT_PRINT_INTERVAL_S)
    parser.add_argument("--origin", nargs=3, type=float, default=(0.0, 0.0, 0.0))
    parser.add_argument("--capture-origin", action="store_true")
    parser.add_argument(
        "--origin-capture-duration",
        type=float,
        default=DEFAULT_ORIGIN_CAPTURE_DURATION_S,
    )
    parser.add_argument("--max-origin-spread-m", type=float, default=DEFAULT_MAX_ORIGIN_SPREAD_M)
    parser.add_argument("--local-x-from", choices=AXIS_SPECS, default="neg-y")
    parser.add_argument("--local-y-from", choices=AXIS_SPECS, default="pos-x")
    parser.add_argument("--local-z-from", choices=AXIS_SPECS, default="pos-z")
    parser.add_argument(
        "--stream-extpos",
        action="store_true",
        help="connect to Crazyflie and send transformed XYZ through cf.extpos.send_extpos",
    )
    parser.add_argument(
        "--reset-estimator",
        action="store_true",
        help="after a few extpos packets, reset the Kalman estimator and log stateEstimate",
    )
    args = parser.parse_args(argv)

    LocalFrameTransform(
        (0.0, 0.0, 0.0),
        (args.local_x_from, args.local_y_from, args.local_z_from),
    )
    if args.duration < 0.0:
        raise ValueError("--duration must be non-negative")
    if args.print_interval <= 0.0:
        raise ValueError("--print-interval must be positive")
    if args.origin_capture_duration <= 0.0:
        raise ValueError("--origin-capture-duration must be positive")
    if args.max_origin_spread_m <= 0.0:
        raise ValueError("--max-origin-spread-m must be positive")
    if args.reset_estimator and not args.stream_extpos:
        raise ValueError("--reset-estimator requires --stream-extpos")
    return args


def main():
    args = parse_args()
    import motioncapture

    print(f"[TRACE] Connecting to VRPN at {args.host}, body {args.body!r}...")
    mocap = motioncapture.connect("vrpn", {"hostname": args.host})
    print("[TRACE] VRPN connected.")

    try:
        if not args.stream_extpos:
            run_trace(args, mocap)
            return

        import cflib.crtp
        from cflib.crazyflie import Crazyflie
        from cflib.crazyflie.log import LogConfig
        from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

        cflib.crtp.init_drivers()
        print(f"[TRACE] Connecting to Crazyflie at {args.uri}...")
        with SyncCrazyflie(args.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
            print("[TRACE] Crazyflie connected.")
            run_trace(args, mocap, scf.cf, LogConfig)
    finally:
        release_connection(mocap)


if __name__ == "__main__":
    main()
