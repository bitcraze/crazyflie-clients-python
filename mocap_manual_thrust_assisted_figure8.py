#!/usr/bin/env python3
"""
Manual-thrust Crazyflie flight with mocap-assisted roll, pitch, yaw, and figure-8.

This is intentionally a script you tune by editing the constants below. The
pilot owns takeoff and landing thrust. During the figure-8, the script can
add a small mocap-based thrust correction to keep the path flat. The script
commands:

- roll/pitch to hold or move the horizontal mocap X/Y target
- yawrate to hold the starting heading
- optional figure-8-only altitude hold correction on top of pilot thrust
- optional keyboard attitude trims on top of the mocap assist
- stale-mocap forced descent/abort behavior, plus safety cuts if the drone
  leaves the tight flight box, climbs too fast, or height gets too high

Recommended first flights:

1. Run this file.
2. Press R to ramp near takeoff thrust, then use Up taps into a low hover.
3. Press T to climb/hold near 3 ft, then wait for the READY indication.
4. Use A/D, W/S, and J/L only as small trims while learning the response.
5. Do not press F until it can hold near the start X/Y for several seconds.
6. Press F to start the figure-8. Press F again to return to the figure-8
   start point and land.
7. During 3ft hold or figure-8, Up/Down nudge the height target.
8. Use PgDn for normal slow descent. Space/Q are emergency cuts.
"""

import csv
import curses
import logging
import math
import os
import shutil
import subprocess
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

# Radio and mocap connection.
URI = "radio://0/80/2M"
MOCAP_HOST = "192.168.1.42:3883"
RIGID_BODY_NAME = "crazyflie_21"

# Cage corners from Motive/VRPN raw coordinates. The flight controller below
# operates in the transformed local frame, so these are transformed before use.
RAW_CAGE_CORNER_POINTS = [
    (-1.027, 1.015, 0.046),   # bottom right
    (-1.020, -0.999, 0.046),  # top right
    (1.035, -1.019, 0.033),   # top left
    (1.037, 0.981, 0.038),    # bottom left
]
CAGE_WALL_MARGIN_M = 0.12
FIGURE8_TRACKING_RESERVE_M = 0.18
CAGE_LIMIT_EXPANSION_M = 2.00
ENFORCE_CAGE_BOUNDS = True

# Keep this smaller than the full cage until mocap coverage is reliable.
# These limits are relative to the takeoff/start position.
MAX_XY_DRIFT_M = 5.50
MAX_GROUND_XY_DRIFT_M = 5.50
MAX_TARGET_ERROR_M = 0.55
FIGURE8_TARGET_ERROR_LIMIT_M = 0.85
MAX_TAKEOFF_TARGET_ERROR_M = 1.20
FIGURE8_DRIFT_SAFETY_MARGIN_M = 0.20
RETURN_HOME_TARGET_ERROR_LIMIT_M = 5.00
RETURN_HOME_LAND_ERROR_M = 0.12
RETURN_HOME_LAND_SPEED_M_S = 0.15
MAX_HEIGHT_ABOVE_START_M = 1.00
MAX_ESTIMATOR_HEIGHT_ABOVE_START_M = 1.00
ENFORCE_HEIGHT_LIMITS = False
MAX_CLIMB_RATE_M_S = 0.60
SAFETY_THRUST_RAW = 35000
ESTIMATOR_HEIGHT_SAFETY_ONLY_WHEN_MOCAP_STALE = True
MOCAP_STALE_TIMEOUT_S = 0.30
MOCAP_STALE_GRACE_S = 4.00
MOCAP_STALE_COAST_S = 1.20
MOCAP_STALE_COAST_MAX_ANGLE_DEG = 2.0
MOCAP_STALE_COAST_MAX_YAWRATE_DEG_S = 20.0
MOCAP_STALE_RESUME_FIGURE8_S = 3.50
SHUTDOWN_ON_STALE_MOCAP = True
MOCAP_STALE_FORCE_DESCENT = True
MOCAP_RELOCK_AFTER_STALE_S = 0.45
STALE_LOG_PERIOD_S = 0.10
ESTIMATOR_STALE_TIMEOUT_S = 0.50

# Manual thrust controls. Crazyflie raw thrust is 0..65535.
# The ready key (R) requests a near-liftoff target, but the actual sent thrust
# rises at THRUST_RAMP_UP_RAW_PER_S. From there, use Up for small nudges.
MAX_MANUAL_THRUST = 52000
SMALL_THRUST_UP_STEP = 100
SMALL_THRUST_DOWN_STEP = 300
BIG_THRUST_STEP = 500
TAKEOFF_READY_THRUST = 34000
THRUST_RAMP_UP_RAW_PER_S = 2500.0
THRUST_RAMP_DOWN_RAW_PER_S = 2500.0
DESCENT_RAMP_RAW_PER_S = 1400.0
SAFETY_DESCENT_RAMP_RAW_PER_S = 12000.0

# Pre-figure-8 height helper. Press T after takeoff to climb/hold about 3 ft
# before pressing F. It uses mocap height and is disabled during stale mocap.
PREFIGURE8_HEIGHT_HOLD_ENABLED = True
PREFIGURE8_HEIGHT_TARGET_M = 0.9144
PREFIGURE8_HEIGHT_MAX_TARGET_M = 1.20
PREFIGURE8_HEIGHT_MIN_TARGET_M = 0.10
PREFIGURE8_HEIGHT_READY_ERROR_M = 0.12
PREFIGURE8_HEIGHT_READY_VERTICAL_SPEED_M_S = 0.08
PREFIGURE8_BASE_THRUST_RAW = 34000
PREFIGURE8_ALTITUDE_KP_RAW_PER_M = 5200.0
PREFIGURE8_ALTITUDE_KI_RAW_PER_M_S = 650.0
PREFIGURE8_ALTITUDE_KD_RAW_PER_M_S = 3800.0
PREFIGURE8_ALTITUDE_CORRECTION_LIMIT_RAW = 1800.0
PREFIGURE8_ALTITUDE_CORRECTION_SLEW_RAW_PER_S = 2600.0

# Horizontal controller.
# VRPN position is rotated relative to the local flight frame:
# local +X <- raw -Y, local +Y <- raw +X, local +Z <- raw +Z.
LOCAL_FRAME_DESCRIPTION = "local +X <- raw -Y, local +Y <- raw +X, local +Z <- raw +Z"

# The position transform below is still required for X/Y/Z. The attitude pulse
# test showed that quaternion yaw already lines up with the Crazyflie command
# axes after that transform, so keep the extra yaw offset at 0 for X/Y assist.
ROLL_SIGN = 1.0
PITCH_SIGN = -1.0
BODY_YAW_OFFSET_DEG = 0.0
YAW_COMMAND_SIGN = -1.0

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
TAKEOFF_XY_ASSIST_START_HEIGHT_M = 0.005
TAKEOFF_XY_ASSIST_FULL_HEIGHT_M = 0.04
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

# Figure-8 target. This is a standing two-lobe path:
# top ellipse from center back to center, then bottom ellipse back to center.
# radius_x is total path width, radius_y is half of the total path height.
FIGURE8_RADIUS_X_M = 11.60
FIGURE8_RADIUS_Y_M = 3.60
FIGURE8_PERIOD_S = 48.0
FIGURE8_MAX_WIDTH_TO_HEIGHT_RATIO = 2.00
FIGURE8_MIN_RADIUS_X_M = 0.20
FIGURE8_MIN_RADIUS_Y_M = 0.12
FIGURE8_MAX_START_ERROR_M = 0.18
FIGURE8_MAX_START_HORIZONTAL_SPEED_M_S = 0.20
FIGURE8_MAX_START_VERTICAL_SPEED_M_S = 0.08

# Figure-8 altitude hold. This only runs while figure-8 mode is active and
# mocap is fresh. Up/Down change the target height during figure-8; outside
# figure-8 they still change raw thrust.
FIGURE8_ALTITUDE_HOLD_ENABLED = True
FIGURE8_ALTITUDE_STEP_M = 0.03
FIGURE8_ALTITUDE_BIG_STEP_M = 0.08
FIGURE8_ALTITUDE_MIN_TARGET_M = 0.04
FIGURE8_ALTITUDE_MAX_TARGET_M = 1.20
FIGURE8_ALTITUDE_KP_RAW_PER_M = 6500.0
FIGURE8_ALTITUDE_KI_RAW_PER_M_S = 900.0
FIGURE8_ALTITUDE_KD_RAW_PER_M_S = 3500.0
FIGURE8_ALTITUDE_INTEGRAL_MAX_ERROR_S = 0.60
FIGURE8_ALTITUDE_CORRECTION_LIMIT_RAW = 1800.0
FIGURE8_ALTITUDE_CORRECTION_SLEW_RAW_PER_S = 3000.0

# Misc.
OUTPUT_DIR = "flight_logs"
COMMAND_PERIOD_S = 0.02
LOG_PERIOD_MS = 100
LOW_BATTERY_V = 3.70
VERY_LOW_BATTERY_V = 3.50
ENFORCE_BATTERY_LIMITS = False
EMERGENCY_ZERO_THRUST_PACKETS = 20
AUTO_START_LIVE_VISUALIZER = True
AUTO_SAVE_3D_PATH_IMAGE = True
LIVE_VISUALIZER_SCRIPT = Path(__file__).with_name("plot_crazyflie_3d_track.py")
LIVE_VISUALIZER_PREFERRED_PYTHON = "/usr/bin/python3"
LIVE_VISUALIZER_INTERVAL_MS = 200
LIVE_VISUALIZER_MAX_SAMPLES = 3000


MIN_THRUST = 0
MAX_THRUST = 65535
MOCAP_TIMEOUT_S = 8.0


@dataclass(frozen=True)
class Quat:
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class Figure8Profile:
    radius_x: float
    radius_y: float
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    margin_m: float
    shrunk: bool
    message: str


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
        "hold_target_frozen",
        "mocap_status",
        "mocap_stale_for_s",
        "mocap_stale_coast_active",
        "key_code",
        "key_name",
        "base_thrust_raw",
        "thrust_raw",
        "target_thrust_raw",
        "thrust_percent",
        "roll_cmd_deg",
        "pitch_cmd_deg",
        "yawrate_cmd_deg_s",
        "roll_sign",
        "pitch_sign",
        "yaw_command_sign",
        "manual_roll_trim_deg",
        "manual_pitch_trim_deg",
        "manual_yaw_offset_deg",
        "target_x",
        "target_y",
        "target_error_x_m",
        "target_error_y_m",
        "target_error_m",
        "figure8_active",
        "return_land_active",
        "return_home_error_m",
        "figure8_elapsed_s",
        "figure8_requested_radius_x_m",
        "figure8_requested_radius_y_m",
        "figure8_radius_x_m",
        "figure8_radius_y_m",
        "figure8_width_m",
        "figure8_height_m",
        "figure8_path_min_x",
        "figure8_path_max_x",
        "figure8_path_min_y",
        "figure8_path_max_y",
        "figure8_wall_margin_m",
        "figure8_shrunk_to_cage",
        "figure8_altitude_hold_active",
        "figure8_target_height_m",
        "figure8_height_error_m",
        "figure8_altitude_integral_error_s",
        "figure8_altitude_correction_raw",
        "height_assist_mode",
        "height_assist_active",
        "prefigure8_height_hold_active",
        "prefigure8_target_height_m",
        "prefigure8_height_ready",
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
        "message",
        "stop_reason",
    ]

    def __init__(self):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.output_path = Path(OUTPUT_DIR) / f"mocap-assisted-figure8-{timestamp}.csv"
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output_path.open("w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        self._writer.writeheader()
        self._file.flush()

    def write(self, row):
        self._writer.writerow(row)
        self._file.flush()

    def close(self):
        self._file.close()


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def visualizer_python():
    candidates = []
    if LIVE_VISUALIZER_PREFERRED_PYTHON:
        candidates.append(LIVE_VISUALIZER_PREFERRED_PYTHON)
    candidates.append(sys.executable)
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path and path not in candidates:
            candidates.append(path)
    for path in ("/usr/bin/python3", "/bin/python3", "/usr/local/bin/python3"):
        if Path(path).exists() and path not in candidates:
            candidates.append(path)

    for candidate in candidates:
        if not Path(candidate).exists() and not shutil.which(candidate):
            continue
        try:
            result = subprocess.run(
                [candidate, "-c", "import matplotlib.pyplot"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return candidate

    return None


def start_live_visualizer(log_path):
    if not AUTO_START_LIVE_VISUALIZER:
        return None
    if not LIVE_VISUALIZER_SCRIPT.exists():
        print(f"[VISUAL] Live viewer not found: {LIVE_VISUALIZER_SCRIPT}")
        return None
    python = visualizer_python()
    if python is None:
        print("[VISUAL] Could not start live 3D viewer: matplotlib is not installed.")
        return None

    command = [
        python,
        str(LIVE_VISUALIZER_SCRIPT),
        str(log_path),
        "--live",
        "--interval-ms",
        str(LIVE_VISUALIZER_INTERVAL_MS),
        "--max-samples",
        str(LIVE_VISUALIZER_MAX_SAMPLES),
    ]
    try:
        process = subprocess.Popen(command, start_new_session=True)
    except OSError as exc:
        print(f"[VISUAL] Could not start live 3D viewer: {exc}")
        return None

    print(
        "[VISUAL] Live 3D viewer started "
        f"(pid {process.pid}): {' '.join(command)}"
    )
    return process


def saved_3d_path_image_path(log_path):
    return log_path.with_name(f"{log_path.stem}-3d-path.png")


def save_3d_path_image(log_path):
    if not AUTO_SAVE_3D_PATH_IMAGE:
        return None
    if not LIVE_VISUALIZER_SCRIPT.exists():
        print(f"[VISUAL] Static plotter not found: {LIVE_VISUALIZER_SCRIPT}")
        return None
    python = visualizer_python()
    if python is None:
        print("[VISUAL] Could not save 3D path image: matplotlib is not installed.")
        return None

    image_path = saved_3d_path_image_path(log_path)
    command = [
        python,
        str(LIVE_VISUALIZER_SCRIPT),
        str(log_path),
        "--save",
        str(image_path),
        "--max-samples",
        str(LIVE_VISUALIZER_MAX_SAMPLES),
    ]
    try:
        env = os.environ.copy()
        env.setdefault("MPLBACKEND", "Agg")
        subprocess.run(command, check=True, env=env)
    except subprocess.CalledProcessError as exc:
        print(f"[VISUAL] Could not save 3D path image; plotter exited {exc.returncode}.")
        return None
    except OSError as exc:
        print(f"[VISUAL] Could not save 3D path image: {exc}")
        return None

    return image_path


def raw_position_to_local(raw_position):
    raw_x, raw_y, raw_z = (float(value) for value in raw_position)
    return (-raw_y, raw_x, raw_z)


def local_cage_corner_points():
    return [raw_position_to_local(point) for point in RAW_CAGE_CORNER_POINTS]


def bounds_from_points(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "y_max": max(ys),
    }


def cage_bounds(margin=0.0):
    bounds = bounds_from_points(local_cage_corner_points())
    return {
        "x_min": bounds["x_min"] - CAGE_LIMIT_EXPANSION_M + margin,
        "x_max": bounds["x_max"] + CAGE_LIMIT_EXPANSION_M - margin,
        "y_min": bounds["y_min"] - CAGE_LIMIT_EXPANSION_M + margin,
        "y_max": bounds["y_max"] + CAGE_LIMIT_EXPANSION_M - margin,
    }


def figure8_extents(center_x, center_y, radius_x, radius_y):
    half_x = 0.5 * radius_x
    return {
        "min_x": center_x - half_x,
        "max_x": center_x + half_x,
        "min_y": center_y - radius_y,
        "max_y": center_y + radius_y,
    }


def bounds_margin(extents, bounds):
    return min(
        extents["min_x"] - bounds["x_min"],
        bounds["x_max"] - extents["max_x"],
        extents["min_y"] - bounds["y_min"],
        bounds["y_max"] - extents["max_y"],
    )


def figure8_max_distance_from_center(radius_x, radius_y):
    half_x = 0.5 * abs(radius_x)
    radius_y = abs(radius_y)
    return math.hypot(half_x, radius_y)


def cage_violation_reason(x, y):
    bounds = cage_bounds(CAGE_WALL_MARGIN_M)
    if x < bounds["x_min"]:
        return f"Cage X min {x:.3f}m < {bounds['x_min']:.3f}m"
    if x > bounds["x_max"]:
        return f"Cage X max {x:.3f}m > {bounds['x_max']:.3f}m"
    if y < bounds["y_min"]:
        return f"Cage Y min {y:.3f}m < {bounds['y_min']:.3f}m"
    if y > bounds["y_max"]:
        return f"Cage Y max {y:.3f}m > {bounds['y_max']:.3f}m"
    return ""


def make_figure8_profile(center_x, center_y):
    planning_bounds = cage_bounds(CAGE_WALL_MARGIN_M + FIGURE8_TRACKING_RESERVE_M)
    hard_bounds = cage_bounds(CAGE_WALL_MARGIN_M)

    max_radius_x = 2.0 * min(
        center_x - planning_bounds["x_min"],
        planning_bounds["x_max"] - center_x,
    )
    max_radius_y = min(
        center_y - planning_bounds["y_min"],
        planning_bounds["y_max"] - center_y,
    )

    if max_radius_x < FIGURE8_MIN_RADIUS_X_M or max_radius_y < FIGURE8_MIN_RADIUS_Y_M:
        return None

    radius_y = min(FIGURE8_RADIUS_Y_M, max_radius_y)
    max_aspect_width = FIGURE8_MAX_WIDTH_TO_HEIGHT_RATIO * 2.0 * radius_y
    radius_x = min(FIGURE8_RADIUS_X_M, max_radius_x, max_aspect_width)
    if radius_x < FIGURE8_MIN_RADIUS_X_M or radius_y < FIGURE8_MIN_RADIUS_Y_M:
        return None
    extents = figure8_extents(center_x, center_y, radius_x, radius_y)
    margin = bounds_margin(extents, hard_bounds)
    shrunk = radius_x < FIGURE8_RADIUS_X_M or radius_y < FIGURE8_RADIUS_Y_M

    if shrunk:
        message = (
            f"Figure-8 shrunk to {radius_x:.2f}m x {2.0 * radius_y:.2f}m; "
            f"wall margin {margin:.2f}m."
        )
    else:
        message = (
            f"Figure-8 {radius_x:.2f}m x {2.0 * radius_y:.2f}m; "
            f"wall margin {margin:.2f}m."
        )

    return Figure8Profile(
        radius_x=radius_x,
        radius_y=radius_y,
        min_x=extents["min_x"],
        max_x=extents["max_x"],
        min_y=extents["min_y"],
        max_y=extents["max_y"],
        margin_m=margin,
        shrunk=shrunk,
        message=message,
    )


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


def low_altitude_angle_limit(height_above_start):
    if height_above_start <= 0.0:
        return GROUND_MAX_ANGLE_DEG
    if height_above_start >= FULL_AUTHORITY_HEIGHT_M:
        return MAX_ANGLE_DEG
    fraction = clamp(height_above_start / FULL_AUTHORITY_HEIGHT_M, 0.0, 1.0)
    return GROUND_MAX_ANGLE_DEG + fraction * (
        MAX_ANGLE_DEG - GROUND_MAX_ANGLE_DEG
    )


def figure8_target(center_x, center_y, elapsed_s, radius_x, radius_y):
    # Wrap the phase so every cycle repeats top lobe, then bottom lobe.
    phase = 2.0 * math.pi * ((elapsed_s % FIGURE8_PERIOD_S) / FIGURE8_PERIOD_S)
    if phase < math.pi:
        lobe_phase = 2.0 * phase
        y_sign = 1.0
    else:
        lobe_phase = 2.0 * (phase - math.pi)
        y_sign = -1.0

    half_x = 0.5 * radius_x
    return (
        center_x + half_x * math.sin(lobe_phase),
        center_y + y_sign * 0.5 * radius_y * (1.0 - math.cos(lobe_phase)),
    )


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
    if state["figure8_active"]:
        figure8_status = "ON"
    elif state["return_land_active"]:
        figure8_status = "RETURN"
    elif state["figure8_ready"]:
        figure8_status = "READY"
    else:
        figure8_status = "off"
    add_line(stdscr, 0, 0, "Manual Thrust + Mocap Assisted Figure-8")
    add_line(
        stdscr,
        2,
        0,
        "Controls: R ready | T 3ft hold | Up/Down thrust or Z target | PgDn descent",
    )
    add_line(stdscr, 3, 0, "Trim: W/S pitch +/- | A/D roll -/+ | J/L yaw target -/+ | C clear")
    add_line(stdscr, 4, 0, "F start figure-8 / return+land | H lock X/Y | Space cut | Q/Esc cut+quit")
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
    add_line(
        stdscr,
        16,
        0,
        f"Figure-8: {figure8_status} "
        f"| elapsed={state['figure8_elapsed']:.1f}s "
        f"| target offset=({state['figure8_target_dx']:+.3f}, {state['figure8_target_dy']:+.3f})",
    )
    add_line(
        stdscr,
        17,
        0,
        f"Path: {state['figure8_width']:.2f}m x {state['figure8_height']:.2f}m "
        f"| wall margin={state['figure8_wall_margin']:.2f}m "
        f"| shrunk={state['figure8_shrunk']}",
    )
    add_line(
        stdscr,
        18,
        0,
        f"Z hold: {'ON' if state['altitude_hold_active'] else 'off'} "
        f"| mode={state['height_assist_mode'] or '-'} "
        f"| target={state['altitude_target']:+.3f}m "
        f"| err={state['altitude_error']:+.3f}m "
        f"| corr={state['altitude_correction']:+.0f} raw",
    )
    add_line(
        stdscr,
        19,
        0,
        f"3ft ready: {'YES' if state['prefigure8_height_ready'] else 'no'} "
        f"| hold={'ON' if state['prefigure8_height_hold_active'] else 'off'}",
    )
    add_line(stdscr, 21, 0, "Normal landing: PgDn. Emergency: Space or Q.")
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
    hold_target_frozen = True

    thrust = 0.0
    target_thrust = 0.0
    descent_active = False
    safety_descent_active = False
    safety_descent_reason = ""
    figure8_active = False
    figure8_started_at = None
    figure8_profile = None
    figure8_target_height = None
    prefigure8_height_hold_active = False
    prefigure8_target_height = PREFIGURE8_HEIGHT_TARGET_M
    altitude_hold_correction = 0.0
    altitude_integral = 0.0
    return_land_active = False
    return_land_descent_started = False
    message = "Neutral takeoff: raise thrust manually, X/Y assist fades in after lift."
    started_at = time.time()
    last_loop_at = started_at
    last_draw_at = 0.0
    last_logged_frame = None
    last_stale_log_at = 0.0
    previous_sample = None
    stale_started_at = None
    stale_saved_figure8_active = False
    stale_saved_figure8_started_at = None
    stale_saved_figure8_profile = None
    stale_saved_figure8_target_height = None
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
    last_fresh_roll_cmd = 0.0
    last_fresh_pitch_cmd = 0.0
    last_fresh_yawrate_cmd = 0.0
    stop_reason = ""

    def start_safety_descent(reason):
        nonlocal target_thrust
        nonlocal descent_active, safety_descent_active, safety_descent_reason
        nonlocal figure8_active, figure8_started_at, figure8_profile
        nonlocal figure8_target_height, altitude_hold_correction, altitude_integral
        nonlocal prefigure8_height_hold_active
        nonlocal return_land_active, return_land_descent_started
        nonlocal integral_x, integral_y
        if not safety_descent_active:
            safety_descent_reason = reason
        target_thrust = min(target_thrust, thrust)
        safety_descent_active = True
        descent_active = True
        figure8_active = False
        figure8_started_at = None
        figure8_profile = None
        figure8_target_height = None
        prefigure8_height_hold_active = False
        altitude_hold_correction = 0.0
        altitude_integral = 0.0
        return_land_active = False
        return_land_descent_started = False
        integral_x = 0.0
        integral_y = 0.0

    def clamp_figure8_height_target(value):
        if ENFORCE_HEIGHT_LIMITS:
            upper = min(FIGURE8_ALTITUDE_MAX_TARGET_M, MAX_HEIGHT_ABOVE_START_M - 0.10)
        else:
            upper = FIGURE8_ALTITUDE_MAX_TARGET_M
        upper = max(FIGURE8_ALTITUDE_MIN_TARGET_M, upper)
        return clamp(value, FIGURE8_ALTITUDE_MIN_TARGET_M, upper)

    def clamp_prefigure8_height_target(value):
        return clamp(
            value,
            PREFIGURE8_HEIGHT_MIN_TARGET_M,
            PREFIGURE8_HEIGHT_MAX_TARGET_M,
        )

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
        current_height = position[2] - start_z
        stale_for = 0.0
        mocap_stale_coast_active = False

        if mocap_stale:
            if stale_started_at is None:
                stale_started_at = now
                stale_saved_figure8_active = figure8_active
                stale_saved_figure8_started_at = figure8_started_at
                stale_saved_figure8_profile = figure8_profile
                stale_saved_figure8_target_height = figure8_target_height
                prefigure8_height_hold_active = False
                figure8_active = False
                figure8_started_at = None
                figure8_profile = None
                figure8_target_height = None
                altitude_hold_correction = 0.0
                altitude_integral = 0.0
                return_land_active = False
                return_land_descent_started = False
                previous_sample = None
                velocity_x = 0.0
                velocity_y = 0.0
                velocity_z = 0.0
                yawrate_measured = 0.0
                integral_x = 0.0
                integral_y = 0.0
                message = "Mocap stale: leveling roll/pitch/yaw. Use PgDn or Space if needed."
            stale_for = now - stale_started_at
            mocap_stale_coast_active = (
                stale_for <= MOCAP_STALE_COAST_S
                and not safety_descent_active
                and not descent_active
            )
            if mocap_stale_coast_active:
                message = (
                    f"Mocap stale {stale_for:.2f}s: coasting last attitude "
                    f"for up to {MOCAP_STALE_COAST_S:.2f}s."
                )
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
            if (
                stale_saved_figure8_active
                and stale_for <= MOCAP_STALE_RESUME_FIGURE8_S
                and stale_saved_figure8_profile is not None
            ):
                figure8_active = True
                figure8_started_at = stale_saved_figure8_started_at
                figure8_profile = stale_saved_figure8_profile
                figure8_target_height = stale_saved_figure8_target_height
                return_land_active = False
                return_land_descent_started = False
                message = f"Mocap reacquired after {stale_for:.1f}s; resuming figure-8."
            elif stale_for >= MOCAP_RELOCK_AFTER_STALE_S:
                hold_x, hold_y = position[0], position[1]
                target_x, target_y = hold_x, hold_y
                hold_target_frozen = True
                figure8_active = False
                figure8_started_at = None
                figure8_profile = None
                figure8_target_height = None
                altitude_hold_correction = 0.0
                altitude_integral = 0.0
                return_land_active = False
                return_land_descent_started = False
                message = f"Mocap reacquired after {stale_for:.1f}s; re-locked current X/Y."
            else:
                message = "Mocap reacquired; continuing hold."
            stale_saved_figure8_active = False
            stale_saved_figure8_started_at = None
            stale_saved_figure8_profile = None
            stale_saved_figure8_target_height = None

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
            figure8_target_height = None
            prefigure8_height_hold_active = False
            altitude_hold_correction = 0.0
            altitude_integral = 0.0
            return_land_active = False
            return_land_descent_started = False
            send_zero_thrust(cf, count=EMERGENCY_ZERO_THRUST_PACKETS, send_stop=False)
            message = "Emergency zero thrust sent immediately."
        elif key == curses.KEY_UP:
            if safety_descent_active:
                message = "Safety descent active; thrust increase ignored."
            elif figure8_active and FIGURE8_ALTITUDE_HOLD_ENABLED:
                if figure8_target_height is None:
                    figure8_target_height = clamp_figure8_height_target(current_height)
                figure8_target_height = clamp_figure8_height_target(
                    figure8_target_height + FIGURE8_ALTITUDE_STEP_M
                )
                message = f"Figure-8 height target {figure8_target_height:.2f}m."
            elif prefigure8_height_hold_active and PREFIGURE8_HEIGHT_HOLD_ENABLED:
                prefigure8_target_height = clamp_prefigure8_height_target(
                    prefigure8_target_height + FIGURE8_ALTITUDE_STEP_M
                )
                message = f"3ft height target {prefigure8_target_height:.2f}m."
            else:
                target_thrust = int(clamp(target_thrust + SMALL_THRUST_UP_STEP, MIN_THRUST, MAX_MANUAL_THRUST))
                descent_active = False
                message = f"Target thrust +{SMALL_THRUST_UP_STEP}; ramping up."
        elif key == curses.KEY_DOWN:
            if figure8_active and FIGURE8_ALTITUDE_HOLD_ENABLED:
                if figure8_target_height is None:
                    figure8_target_height = clamp_figure8_height_target(current_height)
                figure8_target_height = clamp_figure8_height_target(
                    figure8_target_height - FIGURE8_ALTITUDE_STEP_M
                )
                message = f"Figure-8 height target {figure8_target_height:.2f}m."
            elif prefigure8_height_hold_active and PREFIGURE8_HEIGHT_HOLD_ENABLED:
                prefigure8_target_height = clamp_prefigure8_height_target(
                    prefigure8_target_height - FIGURE8_ALTITUDE_STEP_M
                )
                message = f"3ft height target {prefigure8_target_height:.2f}m."
            else:
                target_thrust = int(clamp(target_thrust - SMALL_THRUST_DOWN_STEP, MIN_THRUST, MAX_MANUAL_THRUST))
                descent_active = False
                message = f"Target thrust -{SMALL_THRUST_DOWN_STEP}; ramping down."
        elif key == curses.KEY_PPAGE:
            if safety_descent_active:
                message = "Safety descent active; thrust increase ignored."
            elif figure8_active and FIGURE8_ALTITUDE_HOLD_ENABLED:
                if figure8_target_height is None:
                    figure8_target_height = clamp_figure8_height_target(current_height)
                figure8_target_height = clamp_figure8_height_target(
                    figure8_target_height + FIGURE8_ALTITUDE_BIG_STEP_M
                )
                message = f"Figure-8 height target {figure8_target_height:.2f}m."
            elif prefigure8_height_hold_active and PREFIGURE8_HEIGHT_HOLD_ENABLED:
                prefigure8_target_height = clamp_prefigure8_height_target(
                    prefigure8_target_height + FIGURE8_ALTITUDE_BIG_STEP_M
                )
                message = f"3ft height target {prefigure8_target_height:.2f}m."
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
        elif key in (ord("t"), ord("T")):
            if safety_descent_active:
                message = "Safety descent active; 3ft height hold ignored."
            elif mocap_stale:
                message = "Cannot start 3ft height hold while mocap is stale."
            elif figure8_active or return_land_active:
                message = "3ft height hold is only for before figure-8."
            elif prefigure8_height_hold_active:
                prefigure8_height_hold_active = False
                altitude_hold_correction = 0.0
                altitude_integral = 0.0
                message = "3ft height hold off; manual thrust control."
            else:
                prefigure8_target_height = clamp_prefigure8_height_target(
                    PREFIGURE8_HEIGHT_TARGET_M
                )
                prefigure8_height_hold_active = True
                target_thrust = int(
                    max(target_thrust, PREFIGURE8_BASE_THRUST_RAW)
                )
                descent_active = False
                altitude_hold_correction = 0.0
                altitude_integral = 0.0
                message = (
                    f"3ft height hold on: target {prefigure8_target_height:.2f}m. "
                    "Press F once vertical speed settles."
                )
        elif key == curses.KEY_NPAGE:
            prefigure8_height_hold_active = False
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
                figure8_profile = None
                figure8_target_height = None
                prefigure8_height_hold_active = False
                altitude_hold_correction = 0.0
                altitude_integral = 0.0
                return_land_active = False
                return_land_descent_started = False
                integral_x = 0.0
                integral_y = 0.0
                message = "Locked current X/Y as new hold target."
        elif key in (ord("f"), ord("F")):
            if mocap_stale:
                message = "Cannot start figure-8 while mocap is stale."
            elif figure8_active:
                figure8_active = False
                figure8_started_at = None
                figure8_profile = None
                figure8_target_height = None
                prefigure8_height_hold_active = False
                altitude_hold_correction = 0.0
                altitude_integral = 0.0
                target_x, target_y = hold_x, hold_y
                return_land_active = True
                return_land_descent_started = False
                descent_active = False
                integral_x = 0.0
                integral_y = 0.0
                message = "Returning to figure-8 start; landing when close."
            elif return_land_active:
                hold_x, hold_y = position[0], position[1]
                target_x, target_y = hold_x, hold_y
                return_land_active = False
                return_land_descent_started = False
                descent_active = False
                figure8_target_height = None
                prefigure8_height_hold_active = False
                altitude_hold_correction = 0.0
                altitude_integral = 0.0
                integral_x = 0.0
                integral_y = 0.0
                message = "Return/landing canceled; holding current X/Y."
            else:
                error_to_hold = math.hypot(position[0] - hold_x, position[1] - hold_y)
                horizontal_start_speed = math.hypot(velocity_x, velocity_y)
                requested_profile = make_figure8_profile(position[0], position[1])
                if abs(velocity_z) > FIGURE8_MAX_START_VERTICAL_SPEED_M_S:
                    message = (
                        f"Figure-8 rejected: vertical speed {velocity_z:+.2f}m/s "
                        f"exceeds {FIGURE8_MAX_START_VERTICAL_SPEED_M_S:.2f}m/s."
                    )
                elif horizontal_start_speed > FIGURE8_MAX_START_HORIZONTAL_SPEED_M_S:
                    message = (
                        f"Figure-8 rejected: XY speed {horizontal_start_speed:.2f}m/s "
                        f"exceeds {FIGURE8_MAX_START_HORIZONTAL_SPEED_M_S:.2f}m/s."
                    )
                elif error_to_hold > FIGURE8_MAX_START_ERROR_M:
                    message = (
                        f"Figure-8 rejected: hold error {error_to_hold:.3f}m "
                        f"exceeds {FIGURE8_MAX_START_ERROR_M:.3f}m."
                    )
                elif requested_profile is None:
                    message = "Figure-8 rejected: hold point is too close to the cage wall."
                else:
                    hold_x, hold_y = position[0], position[1]
                    target_x, target_y = hold_x, hold_y
                    hold_target_frozen = True
                    figure8_active = True
                    figure8_started_at = now
                    figure8_profile = requested_profile
                    figure8_target_height = clamp_figure8_height_target(current_height)
                    prefigure8_height_hold_active = False
                    altitude_hold_correction = 0.0
                    altitude_integral = 0.0
                    return_land_active = False
                    return_land_descent_started = False
                    integral_x = 0.0
                    integral_y = 0.0
                    if FIGURE8_ALTITUDE_HOLD_ENABLED:
                        message = (
                            f"{figure8_profile.message} Z hold target "
                            f"{figure8_target_height:.2f}m."
                        )
                    else:
                        message = f"{figure8_profile.message} Keep altitude with thrust."

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
                elif return_land_active:
                    stop_reason = "return_home_landing_complete"
                    target_thrust = 0
                    thrust = 0
                    exit_after_log = True
                    message = "Return landing reached zero thrust."
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

        height = current_height
        height_assist_mode = ""
        height_assist_target = None
        altitude_kp = FIGURE8_ALTITUDE_KP_RAW_PER_M
        altitude_ki = FIGURE8_ALTITUDE_KI_RAW_PER_M_S
        altitude_kd = FIGURE8_ALTITUDE_KD_RAW_PER_M_S
        altitude_correction_limit = FIGURE8_ALTITUDE_CORRECTION_LIMIT_RAW
        altitude_correction_slew = FIGURE8_ALTITUDE_CORRECTION_SLEW_RAW_PER_S
        if (
            FIGURE8_ALTITUDE_HOLD_ENABLED
            and figure8_active
            and not mocap_stale
            and not safety_descent_active
            and not descent_active
            and figure8_target_height is not None
        ):
            height_assist_mode = "figure8"
            figure8_target_height = clamp_figure8_height_target(figure8_target_height)
            height_assist_target = figure8_target_height
        elif (
            PREFIGURE8_HEIGHT_HOLD_ENABLED
            and prefigure8_height_hold_active
            and not mocap_stale
            and not safety_descent_active
            and not descent_active
            and not return_land_active
        ):
            height_assist_mode = "prefigure8"
            prefigure8_target_height = clamp_prefigure8_height_target(
                prefigure8_target_height
            )
            height_assist_target = prefigure8_target_height
            target_thrust = max(target_thrust, PREFIGURE8_BASE_THRUST_RAW)
            altitude_kp = PREFIGURE8_ALTITUDE_KP_RAW_PER_M
            altitude_ki = PREFIGURE8_ALTITUDE_KI_RAW_PER_M_S
            altitude_kd = PREFIGURE8_ALTITUDE_KD_RAW_PER_M_S
            altitude_correction_limit = PREFIGURE8_ALTITUDE_CORRECTION_LIMIT_RAW
            altitude_correction_slew = PREFIGURE8_ALTITUDE_CORRECTION_SLEW_RAW_PER_S
        altitude_hold_active = height_assist_target is not None
        if altitude_hold_active:
            altitude_height_error = height_assist_target - height
            altitude_integral = clamp(
                altitude_integral + altitude_height_error * dt,
                -FIGURE8_ALTITUDE_INTEGRAL_MAX_ERROR_S,
                FIGURE8_ALTITUDE_INTEGRAL_MAX_ERROR_S,
            )
            target_altitude_correction = (
                altitude_kp * altitude_height_error
                + altitude_ki * altitude_integral
                - altitude_kd * velocity_z
            )
            target_altitude_correction = clamp(
                target_altitude_correction,
                -altitude_correction_limit,
                altitude_correction_limit,
            )
            altitude_hold_correction = slew_toward(
                altitude_hold_correction,
                target_altitude_correction,
                altitude_correction_slew,
                altitude_correction_slew,
                dt,
            )
        else:
            altitude_height_error = 0.0
            altitude_hold_correction = 0.0
            altitude_integral = 0.0

        command_thrust = int(
            clamp(
                thrust + altitude_hold_correction,
                MIN_THRUST,
                MAX_MANUAL_THRUST,
            )
        )

        battery_v, estimate_z, estimator_age = telemetry.snapshot()
        estimator_height = estimate_z - start_estimate_z
        if command_thrust > SAFETY_THRUST_RAW and estimator_age > ESTIMATOR_STALE_TIMEOUT_S:
            start_safety_descent(
                f"Estimator height telemetry stale for {estimator_age:.2f}s "
                f"while thrust is {command_thrust}"
            )
        if mocap_stale:
            assist_blend = 0.0
        else:
            height_blend_span = max(
                0.01,
                TAKEOFF_XY_ASSIST_FULL_HEIGHT_M - TAKEOFF_XY_ASSIST_START_HEIGHT_M,
            )
            height_blend = clamp(
                (height - TAKEOFF_XY_ASSIST_START_HEIGHT_M) / height_blend_span,
                0.0,
                1.0,
            )
            assist_blend = height_blend

        # Keep the flight-start X/Y as the takeoff hold target. Roll/pitch
        # remains neutral until the assist fade-in starts, but early floor
        # slide is no longer silently accepted as the new center.

        drift_x = position[0] - start_x
        drift_y = position[1] - start_y
        drift = math.hypot(drift_x, drift_y)
        speed = math.hypot(velocity_x, velocity_y)

        estimator_height_safety_active = (
            not ESTIMATOR_HEIGHT_SAFETY_ONLY_WHEN_MOCAP_STALE
            or mocap_stale
        )
        if (
            ENFORCE_HEIGHT_LIMITS
            and estimator_height_safety_active
            and estimator_height > MAX_ESTIMATOR_HEIGHT_ABOVE_START_M
        ):
            start_safety_descent(
                f"Estimator height {estimator_height:.3f}m exceeded "
                f"{MAX_ESTIMATOR_HEIGHT_ABOVE_START_M:.3f}m"
            )
        if (
            not mocap_stale
            and command_thrust > SAFETY_THRUST_RAW
            and height > 0.03
            and velocity_z > MAX_CLIMB_RATE_M_S
        ):
            start_safety_descent(
                f"Mocap climb rate {velocity_z:.3f}m/s exceeded "
                f"{MAX_CLIMB_RATE_M_S:.3f}m/s"
            )

        if not mocap_stale:
            if ENFORCE_HEIGHT_LIMITS and height > MAX_HEIGHT_ABOVE_START_M:
                start_safety_descent(
                    f"Mocap height {height:.3f}m exceeded {MAX_HEIGHT_ABOVE_START_M:.3f}m"
                )
            xy_drift_limit = (
                MAX_XY_DRIFT_M
                if height >= FULL_AUTHORITY_HEIGHT_M
                else MAX_GROUND_XY_DRIFT_M
            )
            if figure8_active and figure8_profile is not None:
                figure8_center_offset = math.hypot(
                    hold_x - start_x,
                    hold_y - start_y,
                )
                figure8_drift_limit = (
                    figure8_center_offset
                    + figure8_max_distance_from_center(
                        figure8_profile.radius_x,
                        figure8_profile.radius_y,
                    )
                    + FIGURE8_DRIFT_SAFETY_MARGIN_M
                )
                xy_drift_limit = max(xy_drift_limit, figure8_drift_limit)
            if drift > xy_drift_limit:
                start_safety_descent(
                    f"XY drift {drift:.3f}m exceeded {xy_drift_limit:.3f}m"
                )
            if ENFORCE_CAGE_BOUNDS:
                cage_reason = cage_violation_reason(position[0], position[1])
                if cage_reason:
                    start_safety_descent(cage_reason)

        if safety_descent_active:
            target_x, target_y = hold_x, hold_y
            phase = "safety-descent"
        elif mocap_stale:
            target_x, target_y = hold_x, hold_y
            phase = "mocap-stale"
        elif return_land_active:
            target_x, target_y = hold_x, hold_y
            phase = (
                "return-descent"
                if descent_active or return_land_descent_started
                else "return-home"
            )
        elif (
            figure8_active
            and figure8_started_at is not None
            and figure8_profile is not None
        ):
            target_x, target_y = figure8_target(
                hold_x,
                hold_y,
                now - figure8_started_at,
                figure8_profile.radius_x,
                figure8_profile.radius_y,
            )
            phase = "figure8"
        else:
            target_x, target_y = hold_x, hold_y
            if assist_blend <= 0.0:
                phase = "takeoff-neutral"
            elif assist_blend < 1.0:
                phase = "xy-assist-blend"
            elif prefigure8_height_hold_active:
                phase = "height-hold"
            else:
                phase = "xy-hold"
            if descent_active:
                phase = "descent"

        if figure8_active and figure8_started_at is not None:
            figure8_elapsed = now - figure8_started_at
        else:
            figure8_elapsed = 0.0

        error_x = target_x - position[0]
        error_y = target_y - position[1]
        target_error = math.hypot(error_x, error_y)
        return_home_error = math.hypot(hold_x - position[0], hold_y - position[1])
        prefigure8_height_error = prefigure8_target_height - height
        prefigure8_height_ready = (
            not mocap_stale
            and abs(prefigure8_height_error) <= PREFIGURE8_HEIGHT_READY_ERROR_M
            and abs(velocity_z) <= PREFIGURE8_HEIGHT_READY_VERTICAL_SPEED_M_S
        )
        if (
            prefigure8_height_hold_active
            and not safety_descent_active
            and not descent_active
            and not figure8_active
            and not return_land_active
            and not mocap_stale
            and key == -1
        ):
            if prefigure8_height_ready:
                message = "3ft height ready; press F to start figure-8."
            else:
                message = (
                    f"3ft height hold: {prefigure8_height_error:+.2f}m "
                    "from target."
                )
        if (
            return_land_active
            and not descent_active
            and not safety_descent_active
            and not mocap_stale
        ):
            if (
                return_home_error <= RETURN_HOME_LAND_ERROR_M
                and speed <= RETURN_HOME_LAND_SPEED_M_S
            ):
                descent_active = True
                return_land_descent_started = True
                target_thrust = min(target_thrust, thrust)
                message = "At figure-8 start; slow landing ramp active."
            else:
                message = (
                    f"Returning to figure-8 start: {return_home_error:.2f}m away. "
                    "Landing when close."
                )
        if figure8_active:
            prospective_figure8_profile = figure8_profile
        else:
            prospective_figure8_profile = make_figure8_profile(position[0], position[1])
        figure8_ready = (
            not mocap_stale
            and not safety_descent_active
            and not figure8_active
            and not return_land_active
            and prospective_figure8_profile is not None
            and speed <= FIGURE8_MAX_START_HORIZONTAL_SPEED_M_S
            and abs(velocity_z) <= FIGURE8_MAX_START_VERTICAL_SPEED_M_S
            and target_error <= FIGURE8_MAX_START_ERROR_M
        )
        displayed_figure8_profile = (
            figure8_profile
            if figure8_profile is not None
            else prospective_figure8_profile
        )
        if displayed_figure8_profile is None:
            figure8_radius_x = 0.0
            figure8_radius_y = 0.0
            figure8_path_min_x = 0.0
            figure8_path_max_x = 0.0
            figure8_path_min_y = 0.0
            figure8_path_max_y = 0.0
            figure8_wall_margin = 0.0
            figure8_shrunk = 0
        else:
            figure8_radius_x = displayed_figure8_profile.radius_x
            figure8_radius_y = displayed_figure8_profile.radius_y
            figure8_path_min_x = displayed_figure8_profile.min_x
            figure8_path_max_x = displayed_figure8_profile.max_x
            figure8_path_min_y = displayed_figure8_profile.min_y
            figure8_path_max_y = displayed_figure8_profile.max_y
            figure8_wall_margin = displayed_figure8_profile.margin_m
            figure8_shrunk = int(displayed_figure8_profile.shrunk)
        if return_land_active:
            target_error_limit = RETURN_HOME_TARGET_ERROR_LIMIT_M
        elif figure8_active and figure8_profile is not None:
            target_error_limit = FIGURE8_TARGET_ERROR_LIMIT_M
        else:
            target_error_limit = (
                MAX_TARGET_ERROR_M
                if height >= FULL_AUTHORITY_HEIGHT_M
                else MAX_TAKEOFF_TARGET_ERROR_M
            )
        if (
            not mocap_stale
            and assist_blend >= 1.0
            and target_error > target_error_limit
        ):
            start_safety_descent(
                f"Target error {target_error:.3f}m exceeded {target_error_limit:.3f}m"
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

            airborne = command_thrust > 22000 or height > 0.03
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

            yaw_active = command_thrust >= YAW_HOLD_MIN_THRUST or height >= YAW_HOLD_MIN_HEIGHT_M
            if yaw_active:
                raw_yawrate_cmd = (
                    YAW_KP * math.degrees(yaw_error)
                    - YAW_KD * math.degrees(yawrate_measured)
                )
                yawrate_limit = MAX_YAWRATE_DEG_S if height >= YAW_HOLD_MIN_HEIGHT_M else GROUND_MAX_YAWRATE_DEG_S
                yawrate_limit *= assist_blend
                yawrate_cmd = YAW_COMMAND_SIGN * clamp(
                    raw_yawrate_cmd * assist_blend,
                    -yawrate_limit,
                    yawrate_limit,
                )
            else:
                yawrate_cmd = 0.0

        if mocap_stale_coast_active:
            roll_cmd = clamp(
                last_fresh_roll_cmd,
                -MOCAP_STALE_COAST_MAX_ANGLE_DEG,
                MOCAP_STALE_COAST_MAX_ANGLE_DEG,
            )
            pitch_cmd = clamp(
                last_fresh_pitch_cmd,
                -MOCAP_STALE_COAST_MAX_ANGLE_DEG,
                MOCAP_STALE_COAST_MAX_ANGLE_DEG,
            )
            yawrate_cmd = clamp(
                last_fresh_yawrate_cmd,
                -MOCAP_STALE_COAST_MAX_YAWRATE_DEG_S,
                MOCAP_STALE_COAST_MAX_YAWRATE_DEG_S,
            )
        elif not mocap_stale:
            last_fresh_roll_cmd = roll_cmd
            last_fresh_pitch_cmd = pitch_cmd
            last_fresh_yawrate_cmd = yawrate_cmd

        cf.commander.send_setpoint(roll_cmd, pitch_cmd, yawrate_cmd, command_thrust)

        if ENFORCE_BATTERY_LIMITS and battery_v and battery_v < VERY_LOW_BATTERY_V:
            start_safety_descent("battery is very low")

        should_log = frame_count != last_logged_frame
        if key != -1:
            should_log = True
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
                "mocap_stale_for_s": stale_for,
                "mocap_stale_coast_active": int(mocap_stale_coast_active),
                "key_code": key_code,
                "key_name": key_name,
                "base_thrust_raw": thrust,
                "thrust_raw": command_thrust,
                "target_thrust_raw": int(target_thrust),
                "thrust_percent": 100.0 * command_thrust / MAX_THRUST,
                "roll_cmd_deg": roll_cmd,
                "pitch_cmd_deg": pitch_cmd,
                "yawrate_cmd_deg_s": yawrate_cmd,
                "roll_sign": ROLL_SIGN,
                "pitch_sign": PITCH_SIGN,
                "yaw_command_sign": YAW_COMMAND_SIGN,
                "manual_roll_trim_deg": manual_roll_trim,
                "manual_pitch_trim_deg": manual_pitch_trim,
                "manual_yaw_offset_deg": math.degrees(manual_yaw_offset),
                "target_x": target_x,
                "target_y": target_y,
                "target_error_x_m": error_x,
                "target_error_y_m": error_y,
                "target_error_m": target_error,
                "figure8_active": int(figure8_active),
                "return_land_active": int(return_land_active),
                "return_home_error_m": return_home_error,
                "figure8_elapsed_s": figure8_elapsed,
                "figure8_requested_radius_x_m": FIGURE8_RADIUS_X_M,
                "figure8_requested_radius_y_m": FIGURE8_RADIUS_Y_M,
                "figure8_radius_x_m": figure8_radius_x,
                "figure8_radius_y_m": figure8_radius_y,
                "figure8_width_m": figure8_radius_x,
                "figure8_height_m": 2.0 * figure8_radius_y,
                "figure8_path_min_x": figure8_path_min_x,
                "figure8_path_max_x": figure8_path_max_x,
                "figure8_path_min_y": figure8_path_min_y,
                "figure8_path_max_y": figure8_path_max_y,
                "figure8_wall_margin_m": figure8_wall_margin,
                "figure8_shrunk_to_cage": figure8_shrunk,
                "figure8_altitude_hold_active": int(altitude_hold_active),
                "figure8_target_height_m": (
                    figure8_target_height
                    if figure8_target_height is not None
                    else ""
                ),
                "figure8_height_error_m": altitude_height_error,
                "figure8_altitude_integral_error_s": altitude_integral,
                "figure8_altitude_correction_raw": altitude_hold_correction,
                "height_assist_mode": height_assist_mode,
                "height_assist_active": int(altitude_hold_active),
                "prefigure8_height_hold_active": int(prefigure8_height_hold_active),
                "prefigure8_target_height_m": prefigure8_target_height,
                "prefigure8_height_ready": int(prefigure8_height_ready),
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
                "message": message,
                "stop_reason": stop_reason,
            })
            last_logged_frame = frame_count

        if now - last_draw_at >= 0.10:
            draw(stdscr, {
                "phase": phase,
                "message": message,
                "thrust": command_thrust,
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
                "figure8_active": figure8_active,
                "return_land_active": return_land_active,
                "return_home_error": return_home_error,
                "figure8_ready": figure8_ready,
                "figure8_elapsed": figure8_elapsed,
                "figure8_target_dx": target_x - hold_x,
                "figure8_target_dy": target_y - hold_y,
                "figure8_width": figure8_radius_x,
                "figure8_height": 2.0 * figure8_radius_y,
                "figure8_wall_margin": figure8_wall_margin,
                "figure8_shrunk": figure8_shrunk,
                "altitude_hold_active": altitude_hold_active,
                "altitude_target": (
                    figure8_target_height
                    if figure8_target_height is not None
                    else 0.0
                ),
                "altitude_error": altitude_height_error,
                "altitude_correction": altitude_hold_correction,
                "height_assist_mode": height_assist_mode,
                "prefigure8_height_hold_active": prefigure8_height_hold_active,
                "prefigure8_height_ready": prefigure8_height_ready,
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
        f"Thrust keys: Up +{SMALL_THRUST_UP_STEP}, "
        f"Down -{SMALL_THRUST_DOWN_STEP}, PgUp +{BIG_THRUST_STEP}; "
        "during 3ft/figure-8 hold these nudge the Z target"
    )
    print(
        f"3ft helper: T toggles target {PREFIGURE8_HEIGHT_TARGET_M:.2f}m "
        f"({PREFIGURE8_HEIGHT_TARGET_M * 3.28084:.1f}ft), "
        f"ready within +/-{PREFIGURE8_HEIGHT_READY_ERROR_M:.2f}m"
    )
    print(
        f"Thrust ramp: up {THRUST_RAMP_UP_RAW_PER_S:.0f} raw/s, "
        f"down {THRUST_RAMP_DOWN_RAW_PER_S:.0f} raw/s, "
        f"PgDn {DESCENT_RAMP_RAW_PER_S:.0f} raw/s"
    )
    print(
        f"Safety box: airborne drift <= {MAX_XY_DRIFT_M:.2f}m, "
        f"ground drift <= {MAX_GROUND_XY_DRIFT_M:.2f}m, "
        "height limit disabled"
    )
    measured_bounds = bounds_from_points(local_cage_corner_points())
    raw_bounds = cage_bounds(0.0)
    flight_bounds = cage_bounds(CAGE_WALL_MARGIN_M)
    planning_bounds = cage_bounds(CAGE_WALL_MARGIN_M + FIGURE8_TRACKING_RESERVE_M)
    print(
        f"Measured local cage bounds: X[{measured_bounds['x_min']:.2f}, "
        f"{measured_bounds['x_max']:.2f}], "
        f"Y[{measured_bounds['y_min']:.2f}, {measured_bounds['y_max']:.2f}]"
    )
    print(
        f"Software cage expansion: +{CAGE_LIMIT_EXPANSION_M:.2f}m beyond measured bounds"
    )
    print(
        f"Expanded software bounds: X[{raw_bounds['x_min']:.2f}, {raw_bounds['x_max']:.2f}], "
        f"Y[{raw_bounds['y_min']:.2f}, {raw_bounds['y_max']:.2f}]"
    )
    print(
        f"Cage flight bounds: X[{flight_bounds['x_min']:.2f}, {flight_bounds['x_max']:.2f}], "
        f"Y[{flight_bounds['y_min']:.2f}, {flight_bounds['y_max']:.2f}], "
        f"planning reserve bounds X[{planning_bounds['x_min']:.2f}, {planning_bounds['x_max']:.2f}]"
    )
    print(
        f"Hard stops: climb <= {MAX_CLIMB_RATE_M_S:.2f}m/s, "
        f"estimator age <= {ESTIMATOR_STALE_TIMEOUT_S:.2f}s above thrust {SAFETY_THRUST_RAW}, "
        f"stale mocap shutdown={SHUTDOWN_ON_STALE_MOCAP}, "
        f"grace={MOCAP_STALE_GRACE_S:.2f}s, coast={MOCAP_STALE_COAST_S:.2f}s"
    )
    print(f"XY gains: kp={KP_XY}, kd={KD_XY}, ki={KI_XY}, signs roll={ROLL_SIGN}, pitch={PITCH_SIGN}")
    print(f"Mocap frame: {LOCAL_FRAME_DESCRIPTION}")
    print(f"Body yaw offset for X/Y assist: {BODY_YAW_OFFSET_DEG:+.1f} deg")
    print(
        f"Keyboard trim: roll/pitch step={ROLL_TRIM_STEP_DEG:.1f}/{PITCH_TRIM_STEP_DEG:.1f} deg, "
        f"max=+/-{MAX_ROLL_PITCH_TRIM_DEG:.1f} deg, yaw step={YAW_TARGET_STEP_DEG:.1f} deg"
    )
    print(
        f"Figure-8 request: width {FIGURE8_RADIUS_X_M:.2f}m x "
        f"height {2.0 * FIGURE8_RADIUS_Y_M:.2f}m, period {FIGURE8_PERIOD_S:.1f}s; "
        "auto-shrinks if the hold point is too close to a wall"
    )
    print(
        f"Figure-8 Z hold: enabled={FIGURE8_ALTITUDE_HOLD_ENABLED}, "
        f"step={FIGURE8_ALTITUDE_STEP_M:.2f}m, "
        f"correction <= +/-{FIGURE8_ALTITUDE_CORRECTION_LIMIT_RAW:.0f} raw"
    )
    print("Close cfclient first. Keep a physical power-off option ready.")
    print("=" * 72)
    input("Press ENTER to connect mocap and Crazyflie, or Ctrl+C to abort...")

    mocap_state = MocapState()
    mocap_reader = MocapReader(mocap_state)
    telemetry = Telemetry()
    logger = CsvLogger()
    visualizer_process = start_live_visualizer(logger.output_path)
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
                mocap_reader,
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
        image_path = save_3d_path_image(logger.output_path)
        if image_path is not None:
            print(f"[DONE] Wrote 3D path image: {image_path}")
        if visualizer_process is not None:
            visualizer_status = visualizer_process.poll()
            if visualizer_status is None:
                print(
                    "[VISUAL] Live 3D viewer is still open "
                    f"(pid {visualizer_process.pid}); close it when done."
                )
            else:
                print(f"[VISUAL] Live 3D viewer exited with code {visualizer_status}.")
        if clean_exit:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)


if __name__ == "__main__":
    main()
