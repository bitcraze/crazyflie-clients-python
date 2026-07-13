#
# ,---------,       ____  _ __
# |  ,-^-,  |      / __ )(_) /_______________ _____  ___
# | (  O  ) |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# | / ,--'  |    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#    +------`   /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Copyright (C) 2023 Bitcraze AB
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, in version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
Example of how to connect to a motion capture system and feed the position to a
Crazyflie, using the motioncapture library. The motioncapture library supports all major mocap systems and provides
a generalized API regardless of system type.
The script uses the high level commander to upload a trajectory to fly a figure 8
within a flight cage (configurable size, default 0.6m x 0.6m) at 50cm height.

Set the uri to the radio settings of the Crazyflie and modify the
mocap setting matching your system.

================================================================================
EXPERIMENTABLE VARIABLES - Look for "EXPERIMENT:" comments throughout the code:
================================================================================
1. Connection Settings (lines ~44-54):
   - uri: Crazyflie radio URI
   - host_name: Mocap system IP/port
   - mocap_system_type: Type of mocap system
   - rigid_body_name: Name of rigid body in mocap

2. Cage Configuration (lines ~66-76):
   - CAGE_BOUNDS: Physical cage dimensions
   - SAFETY_MARGIN: Distance to keep from walls

3. Flight Parameters (lines ~78-80):
   - FLIGHT_HEIGHT: Altitude to fly at
   - FIGURE8_AMPLITUDE: Size of figure-8 pattern

4. Trajectory Parameters (lines ~174-189):
   - num_segments: Number of trajectory segments (smoothness)
   - total_duration: Time to complete one figure-8

5. Timing Parameters (throughout):
   - Various time.sleep() values for takeoff, landing, etc.
   - check_interval: Boundary monitoring frequency
   - Trajectory timescale in start_trajectory()
"""
import csv
import time
from pathlib import Path
from threading import Thread
import numpy as np
import motioncapture
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.mem import MemoryElement
from cflib.crazyflie.mem import Poly4D
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.utils import uri_helper
from cflib.utils.reset_estimator import reset_estimator

# ========== CONNECTION SETTINGS - EXPERIMENT HERE ==========
# URI to the Crazyflie to connect to
uri = uri_helper.uri_from_env(default='radio://0/80/2M/E7E7E7E7E7')

# The host name or ip address of the mocap system
host_name = '192.168.1.42:3883'  # EXPERIMENT: Change to your mocap system IP/port

# The type of the mocap system
# Valid options are: 'vicon', 'optitrack', 'optitrack_closed_source', 'qualisys', 'nokov', 'vrpn', 'motionanalysis'
mocap_system_type = 'vrpn'  # EXPERIMENT: Change to match your mocap system type

# The name of the rigid body that represents the Crazyflie
rigid_body_name = 'crazyflie_21'  # EXPERIMENT: Change to your rigid body name in mocap

# True: send position and orientation; False: send position only.
# Full pose made takeoff drift worse with the current rigid-body orientation,
# so keep the hover diagnostic on position-only mocap for now.
send_full_pose = False

# When using full pose, the estimator can be sensitive to noise in the orientation data when yaw is close to +/- 90
# degrees. If this is a problem, increase orientation_std_dev a bit. The default value in the firmware is 4.5e-3.
orientation_std_dev = 8.0e-3  # EXPERIMENT: Increase if orientation noise is an issue (default: 4.5e-3)

# ========== CAGE BOUNDARY CONFIGURATION - EXPERIMENT HERE ==========
# Define your flight area using four corner points (from motive-stream measurements)
# Corner points are measured on the ground - z coordinates are ignored for boundaries
# In this OptiTrack frame, physical right is X-min and physical left is X-max.
CORNER_POINTS = [
    (-1.027, 1.015, 0.046),  # bottom right (index 0)
    (-1.020, -0.999, 0.046), # top right (index 1)
    (1.035, -1.019, 0.033),  # top left (index 2)
    (1.037, 0.981, 0.038),   # bottom left (index 3)
]

# Safety margin - how far from the walls to stay (in meters)
SAFETY_MARGIN = 0.1  # EXPERIMENT: Increase for more safety buffer, decrease to use more space (meters)
SAFE_X_MIN_OVERRIDE = -2.7  # Allow starting closer to the physical right wall for testing.
SAFE_Y_MARGIN_OVERRIDE = 0.05  # Use None to fall back to SAFETY_MARGIN for Y walls.

# Pattern center - None = auto-calculate from corners, or specify (x, y) tuple for manual center
PATTERN_CENTER = None  # Relative trajectories use the live takeoff position.

# Takeoff corner - which corner to use as starting point (0-3, default: 0 = bottom right)
TAKEOFF_CORNER = 0  # EXPERIMENT: 0=bottom right, 1=top right, 2=top left, 3=bottom left

# Calculated boundaries (will be computed from CORNER_POINTS)
CAGE_BOUNDS = None  # Will be set by calculate_bounds_from_corners()

# ========== FLIGHT PARAMETERS - EXPERIMENT HERE ==========
# Flight height - how high the drone flies (in meters)
FLIGHT_HEIGHT = 0.6  # EXPERIMENT: Change flight altitude (0.5m = 50cm, max recommended: 1.5m for 2m ceiling)

# Hover pause time - pause at key points in the figure-8 for smoother, less frantic movement (seconds)
# NOTE: Currently not implemented in trajectory - reserved for future use
HOVER_PAUSE_TIME = 0.5  # EXPERIMENT: Increase for longer pauses (try 0.5-1.5s), set to 0.0 to disable pauses

# Figure-8 amplitude - size of the figure-8 pattern (in meters)
# The actual pattern will be ~2x this value in each dimension
# For a 0.6m cage (X: -0.3 to 0.3) with 0.05m safety margin, safe range is -0.25 to 0.25
# Maximum safe amplitude = 0.25m (to stay within safe bounds)
FIGURE8_AMPLITUDE = 0.05  # EXPERIMENT: For 0.6m cage with 0.05m margin, use 0.2-0.25m max

# Crazyflie trajectory time factor: >1.0 is slower, <1.0 is faster.
TRAJECTORY_TIME_SCALE = 3.0
START_POSITION_TOLERANCE = 0.15  # Refuse flight unless within 15 cm of the trajectory start.
START_FIGURE8_AT_CURRENT_POSITION = True  # Offset the path from the takeoff position, like mocap-extpose-example.py.
HOVER_ONLY_TEST = True  # Keep True until mocap/estimator frames are verified.
HOVER_TEST_DURATION = 5.0
HOVER_DIAGNOSTIC_CSV = Path('logs/hover-diagnostic.csv')
TAKEOFF_HEIGHT_TOLERANCE = 0.08
TAKEOFF_SETTLE_TIMEOUT = 6.0
MAX_TAKEOFF_DRIFT = 0.12
MAX_CENTER_DRIFT = 0.14  # Just above the intended figure-eight radius; abort unexpected motion early.

# Conservative PID position-controller limits for this flight session. They
# bound lateral correction without reducing the thrust required to hold height.
APPLY_CONSERVATIVE_FLIGHT_LIMITS = False
MAX_ROLL_PITCH_DEGREES = 8.0
MAX_HORIZONTAL_SPEED = 0.15  # m/s in the Crazyflie's body-yaw-aligned frame

# Generated by mocap-path-to-waypoints.py and uav_trajectories. This path is
# local to the takeoff setpoint, so its Z coordinates must remain at zero.
USE_GENERATED_POLYNOMIAL_TRAJECTORY = True
POLYNOMIAL_TRAJECTORY_CSV = Path('logs/desired-figure8-relative-polynomial.csv')
POLYNOMIAL_TRAJECTORY_XY_SCALE = 0.1

# Current position tracking (for boundary checking)
current_position = {'x': 0.0, 'y': 0.0, 'z': 0.0}
last_mocap_update = None
state_estimate = {'x': None, 'y': None, 'z': None}
last_state_estimate_update = None
MOCAP_STALE_TIMEOUT = 1.0


class MocapWrapper(Thread):
    def __init__(self, body_name):
        Thread.__init__(self)

        self.body_name = body_name
        self.on_pose = None
        self._stay_open = True
        self.daemon = True

        self.start()

    def close(self):
        self._stay_open = False
        self.join(timeout=1.0)

    def run(self):
        global last_mocap_update

        mc = motioncapture.connect(mocap_system_type, {'hostname': host_name})
        print(f"[INFO] Mocap connected, looking for '{self.body_name}'")
        found_body = False
        while self._stay_open:
            mc.waitForNextFrame()
            for name, obj in mc.rigidBodies.items():
                if name == self.body_name:
                    if not found_body:
                        print(f"[INFO] Found and tracking rigid body: {name}")
                        found_body = True
                    if self.on_pose:
                        pos = obj.position
                        # Update global position for boundary checking
                        current_position['x'] = pos[0]
                        current_position['y'] = pos[1]
                        current_position['z'] = pos[2]
                        last_mocap_update = time.monotonic()
                        self.on_pose([pos[0], pos[1], pos[2], obj.rotation])


def send_extpose_quat(cf, x, y, z, quat):
    """
    Send the current Crazyflie X, Y, Z position and attitude as a quaternion.
    This is going to be forwarded to the Crazyflie's position estimator.
    """
    if send_full_pose:
        cf.extpos.send_extpose(x, y, z, quat.x, quat.y, quat.z, quat.w)
    else:
        cf.extpos.send_extpos(x, y, z)


def adjust_orientation_sensitivity(cf):
    cf.param.set_value('locSrv.extQuatStdDev', orientation_std_dev)


def activate_kalman_estimator(cf):
    cf.param.set_value('stabilizer.estimator', '2')


def enable_high_level_commander(cf):
    cf.param.set_value('commander.enHighLevel', '1')


def apply_conservative_flight_limits(cf):
    """Apply temporary lateral PID limits and return the previous values."""
    requested_limits = {
        'posCtlPid.rLimit': MAX_ROLL_PITCH_DEGREES,
        'posCtlPid.pLimit': MAX_ROLL_PITCH_DEGREES,
        'posCtlPid.xVelMax': MAX_HORIZONTAL_SPEED,
        'posCtlPid.yVelMax': MAX_HORIZONTAL_SPEED,
    }
    previous_limits = {}
    for name, value in requested_limits.items():
        previous_limits[name] = cf.param.get_value(name)
        cf.param.set_value(name, str(value))
    return previous_limits


def restore_flight_limits(cf, previous_limits):
    """Restore the PID limits that were active before this script ran."""
    for name, value in previous_limits.items():
        cf.param.set_value(name, value)


def calculate_bounds_from_corners(corners, z_min=0.0, z_max=2.0):
    """
    Calculate min/max bounds from corner points.
    Returns dict with x_min, x_max, y_min, y_max, z_min, z_max.
    z_min and z_max are configurable (not from corners, since corners are ground measurements).
    """
    x_coords = [corner[0] for corner in corners]
    y_coords = [corner[1] for corner in corners]
    
    return {
        'x_min': min(x_coords),
        'x_max': max(x_coords),
        'y_min': min(y_coords),
        'y_max': max(y_coords),
        'z_min': z_min,
        'z_max': z_max,
    }


def calculate_center_from_corners(corners):
    """
    Calculate center point from corner points (x, y only).
    Returns (center_x, center_y) tuple.
    """
    bounds = calculate_bounds_from_corners(corners)
    center_x = (bounds['x_min'] + bounds['x_max']) / 2.0
    center_y = (bounds['y_min'] + bounds['y_max']) / 2.0
    return (center_x, center_y)


def calculate_takeoff_position(corner_index, corners, bounds, safety_margin):
    """
    Calculate safe takeoff position from selected corner.
    Adjusts corner position inward by safety margin to ensure safe takeoff.
    Returns (x, y) tuple.
    """
    if corner_index < 0 or corner_index >= len(corners):
        raise ValueError(f"Invalid corner index {corner_index}. Must be 0-{len(corners)-1}")
    
    corner = corners[corner_index]
    corner_x, corner_y = corner[0], corner[1]
    
    # Determine which boundaries this corner is closest to
    # and adjust inward by safety margin
    x_min_safe = bounds['x_min'] + safety_margin
    x_max_safe = bounds['x_max'] - safety_margin
    y_min_safe = bounds['y_min'] + safety_margin
    y_max_safe = bounds['y_max'] - safety_margin
    
    # Adjust position inward from corner. In this cage, physical right is X-min
    # and physical left is X-max.
    # For bottom right (index 0): move +x and -y (toward center)
    # For top right (index 1): move +x and +y
    # For top left (index 2): move -x and +y
    # For bottom left (index 3): move -x and -y
    
    if corner_index == 0:  # bottom right
        takeoff_x = min(corner_x + safety_margin, x_max_safe)
        takeoff_y = min(corner_y + safety_margin, y_max_safe)
    elif corner_index == 1:  # top right
        takeoff_x = min(corner_x + safety_margin, x_max_safe)
        takeoff_y = max(corner_y - safety_margin, y_min_safe)
    elif corner_index == 2:  # top left
        takeoff_x = max(corner_x - safety_margin, x_min_safe)
        takeoff_y = max(corner_y - safety_margin, y_min_safe)
    else:  # bottom left (index 3)
        takeoff_x = max(corner_x - safety_margin, x_min_safe)
        takeoff_y = min(corner_y + safety_margin, y_max_safe)
    
    return (takeoff_x, takeoff_y)


def check_position_safe(x, y, z, bounds=None):
    """
    Check if a position is within safe boundaries.
    Returns (is_safe, reason)
    
    Args:
        x, y, z: Position coordinates
        bounds: Optional bounds dict. If None, uses global CAGE_BOUNDS.
    """
    if bounds is None:
        bounds = CAGE_BOUNDS
    
    if bounds is None:
        return False, "Bounds not initialized"
    
    safe_x_min = (
        SAFE_X_MIN_OVERRIDE
        if SAFE_X_MIN_OVERRIDE is not None
        else bounds['x_min'] + SAFETY_MARGIN
    )
    safe_y_margin = (
        SAFE_Y_MARGIN_OVERRIDE
        if SAFE_Y_MARGIN_OVERRIDE is not None
        else SAFETY_MARGIN
    )

    if x < safe_x_min:
        return False, f"Too close to physical right wall / X min boundary ({x:.2f}m)"
    if x > bounds['x_max'] - SAFETY_MARGIN:
        return False, f"Too close to physical left wall / X max boundary ({x:.2f}m)"
    if y < bounds['y_min'] + safe_y_margin:
        return False, f"Too close to Y min boundary ({y:.2f}m)"
    if y > bounds['y_max'] - safe_y_margin:
        return False, f"Too close to Y max boundary ({y:.2f}m)"
    if z < bounds['z_min'] + SAFETY_MARGIN:
        return False, f"Too close to floor ({z:.2f}m)"
    if z > bounds['z_max'] - SAFETY_MARGIN:
        return False, f"Too close to ceiling ({z:.2f}m)"
    return True, "Safe"


def generate_figure8_trajectory(center_x=0.0, center_y=0.0, relative_to_start=False):
    """
    Generate polynomial trajectory coefficients for a small figure-8 pattern.
    The figure-8 (lemniscate) is parameterized as:
    - x(t) = center_x + A * sin(t)
    - y(t) = center_y + A * sin(t) * cos(t) = center_y + A * sin(2*t) / 2
    - z(t) = FLIGHT_HEIGHT (constant)
    - yaw(t) = 0 (constant)
    
    Args:
        center_x: X coordinate of pattern center (default: 0.0)
        center_y: Y coordinate of pattern center (default: 0.0)
    
    Returns trajectory in format: [duration, x^0...x^7, y^0...y^7, z^0...z^7, yaw^0...yaw^7]
    """
    # For a small figure-8, we'll create multiple segments to form a smooth path
    # Each segment is a polynomial that connects waypoints along the figure-8
    
    # Generate waypoints along the figure-8 path
    A = FIGURE8_AMPLITUDE
    num_segments = 16  # EXPERIMENT: More segments = smoother path but more computation (try: 8, 12, 16, 24)
    t_values = np.linspace(0, 2 * np.pi, num_segments + 1)
    
    waypoints = []
    for t in t_values:
        x = center_x + A * np.sin(t)
        y = center_y + A * np.sin(t) * np.cos(t)
        # Relative trajectories are offset in Z as well as X/Y. Keep local Z at zero.
        z = 0.0 if relative_to_start else FLIGHT_HEIGHT
        waypoints.append((x, y, z))
    
    # For each segment, create a polynomial that smoothly connects waypoints
    # This is a simplified approach - in practice, you'd use optimization tools
    # like uav_trajectories for optimal polynomial generation
    
    trajectory = []
    total_duration = 20.0  # EXPERIMENT: Total time for one complete figure-8 (seconds) - increase for slower, decrease for faster
    segment_duration = total_duration / num_segments
    
    # Calculate parametric speed (radians per second)
    param_speed = (2 * np.pi) / total_duration
    
    for i in range(num_segments):
        # Start and end waypoints for this segment
        t_start = t_values[i]
        t_end = t_values[i + 1]
        start = waypoints[i]
        end = waypoints[i + 1]
        
        # Calculate velocities at waypoints using parametric derivatives
        # dx/dt = A * cos(t)
        # dy/dt = A * (cos^2(t) - sin^2(t)) = A * cos(2*t)
        if i == 0:
            # First segment: start from rest (smooth start)
            vx_start, vy_start = 0.0, 0.0
        else:
            # Calculate velocity from parametric derivative
            vx_start = A * np.cos(t_start) * param_speed
            vy_start = A * np.cos(2 * t_start) * param_speed
        
        if i == num_segments - 1:
            # Last segment: end at rest (smooth stop)
            vx_end, vy_end = 0.0, 0.0
        else:
            # Calculate velocity from parametric derivative
            vx_end = A * np.cos(t_end) * param_speed
            vy_end = A * np.cos(2 * t_end) * param_speed
        
        # Create a simple cubic polynomial for x and y
        # p(t) = a0 + a1*t + a2*t^2 + a3*t^3
        # We'll extend to 7th order by setting higher coefficients to 0
        
        # For x
        x0, x1 = start[0], end[0]
        vx0, vx1 = vx_start, vx_end
        T = segment_duration
        
        # Cubic polynomial coefficients (we'll pad to 7th order)
        # Solving: p(0)=x0, p(T)=x1, p'(0)=vx0, p'(T)=vx1
        a0_x = x0
        a1_x = vx0
        a2_x = (3*(x1 - x0) - T*(2*vx0 + vx1)) / (T*T)
        a3_x = (2*(x0 - x1) + T*(vx0 + vx1)) / (T*T*T)
        
        # For y
        y0, y1 = start[1], end[1]
        vy0, vy1 = vy_start, vy_end
        
        a0_y = y0
        a1_y = vy0
        a2_y = (3*(y1 - y0) - T*(2*vy0 + vy1)) / (T*T)
        a3_y = (2*(y0 - y1) + T*(vy0 + vy1)) / (T*T*T)
        
        # For z (constant)
        z_coeffs = [z, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        
        # For yaw (constant)
        yaw_coeffs = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        
        # Pad x and y to 7th order (set higher order terms to 0)
        x_coeffs = [a0_x, a1_x, a2_x, a3_x, 0.0, 0.0, 0.0, 0.0]
        y_coeffs = [a0_y, a1_y, a2_y, a3_y, 0.0, 0.0, 0.0, 0.0]
        
        # Format: [duration, x^0...x^7, y^0...y^7, z^0...z^7, yaw^0...yaw^7]
        segment = [segment_duration] + x_coeffs + y_coeffs + z_coeffs + yaw_coeffs
        trajectory.append(segment)
    
    return trajectory


def validate_trajectory(trajectory, origin=(0.0, 0.0, 0.0)):
    """
    Validate that all waypoints in the trajectory are within safe boundaries.
    Returns (is_valid, error_message)
    """
    # Sample points along the trajectory to check
    for i, segment in enumerate(trajectory):
        duration = segment[0]
        x_poly = segment[1:9]
        y_poly = segment[9:17]
        z_poly = segment[17:25]
        
        # Sample through each cubic segment; checking only its endpoints can miss
        # a curve that briefly bows outside the cage.
        for t in np.linspace(0.0, duration, 11):
            # Evaluate polynomial at time t
            x = origin[0] + sum(x_poly[j] * (t ** j) for j in range(8))
            y = origin[1] + sum(y_poly[j] * (t ** j) for j in range(8))
            z = origin[2] + sum(z_poly[j] * (t ** j) for j in range(8))
            
            is_safe, reason = check_position_safe(x, y, z)
            if not is_safe:
                return False, f"Segment {i+1} at t={t:.2f}s: {reason}"
    
    return True, "All waypoints are safe"


def center_drift_from_pattern(pattern_center):
    return ((current_position["x"] - pattern_center[0])**2 +
            (current_position["y"] - pattern_center[1])**2)**0.5


def reset_hover_diagnostic_log():
    HOVER_DIAGNOSTIC_CSV.parent.mkdir(parents=True, exist_ok=True)
    with HOVER_DIAGNOSTIC_CSV.open('w', newline='', encoding='ascii') as log_file:
        writer = csv.writer(log_file)
        writer.writerow([
            'wall_time',
            'phase',
            'mocap_x',
            'mocap_y',
            'mocap_z',
            'mocap_age_s',
            'estimate_x',
            'estimate_y',
            'estimate_z',
            'estimate_age_s',
            'drift_m',
            'note',
        ])


def append_hover_diagnostic_sample(phase, pattern_center=None, note=''):
    mocap_age = (
        ''
        if last_mocap_update is None
        else f'{time.monotonic() - last_mocap_update:.3f}'
    )
    estimate_age = (
        ''
        if last_state_estimate_update is None
        else f'{time.monotonic() - last_state_estimate_update:.3f}'
    )
    drift = '' if pattern_center is None else f'{center_drift_from_pattern(pattern_center):.3f}'

    with HOVER_DIAGNOSTIC_CSV.open('a', newline='', encoding='ascii') as log_file:
        writer = csv.writer(log_file)
        writer.writerow([
            f'{time.time():.3f}',
            phase,
            f'{current_position["x"]:.3f}',
            f'{current_position["y"]:.3f}',
            f'{current_position["z"]:.3f}',
            mocap_age,
            '' if state_estimate['x'] is None else f'{state_estimate["x"]:.3f}',
            '' if state_estimate['y'] is None else f'{state_estimate["y"]:.3f}',
            '' if state_estimate['z'] is None else f'{state_estimate["z"]:.3f}',
            estimate_age,
            drift,
            note,
        ])


def mocap_is_fresh():
    if last_mocap_update is None:
        return False, 'No mocap pose has been received'

    age = time.monotonic() - last_mocap_update
    if age > MOCAP_STALE_TIMEOUT:
        return False, f'Mocap pose is stale ({age:.2f}s since the last update)'

    return True, 'Mocap pose is current'


def setup_estimate_logger(cf):
    log_config = LogConfig(name='HoverEstimate', period_in_ms=100)
    log_config.add_variable('stateEstimate.x', 'float')
    log_config.add_variable('stateEstimate.y', 'float')
    log_config.add_variable('stateEstimate.z', 'float')

    def on_data(timestamp, data, logconf):
        global last_state_estimate_update
        del timestamp
        del logconf
        state_estimate['x'] = data['stateEstimate.x']
        state_estimate['y'] = data['stateEstimate.y']
        state_estimate['z'] = data['stateEstimate.z']
        last_state_estimate_update = time.monotonic()

    def on_error(logconf, msg):
        print(f'[WARN] Estimate logger error from {logconf.name}: {msg}')

    cf.log.add_config(log_config)
    log_config.data_received_cb.add_callback(on_data)
    log_config.error_cb.add_callback(on_error)
    log_config.start()
    return log_config


def wait_for_takeoff_height(target_height, launch_xy=None):
    deadline = time.time() + TAKEOFF_SETTLE_TIMEOUT
    minimum_height = max(0.0, target_height - TAKEOFF_HEIGHT_TOLERANCE)

    while time.time() < deadline:
        mocap_fresh, reason = mocap_is_fresh()
        if not mocap_fresh:
            return False, reason

        x = current_position["x"]
        y = current_position["y"]
        z = current_position["z"]
        if launch_xy is not None:
            takeoff_drift = ((x - launch_xy[0])**2 + (y - launch_xy[1])**2)**0.5
            if HOVER_ONLY_TEST:
                append_hover_diagnostic_sample(
                    'takeoff',
                    launch_xy,
                    f'altitude target >= {minimum_height:.2f}m'
                )
            if takeoff_drift > MAX_TAKEOFF_DRIFT:
                return False, (
                    f"Takeoff drift {takeoff_drift:.3f}m exceeded "
                    f"{MAX_TAKEOFF_DRIFT:.3f}m before reaching height"
                )
        horizontal_safe, reason = check_position_safe(x, y, FLIGHT_HEIGHT)
        if not horizontal_safe:
            return False, reason
        if z >= minimum_height:
            return True, f"Reached takeoff height {z:.2f}m"
        time.sleep(0.1)

    return False, (
        f"Mocap altitude stayed at {current_position['z']:.2f}m; "
        f"expected at least {minimum_height:.2f}m"
    )


def upload_trajectory(cf, trajectory_id, trajectory):
    """Upload trajectory to Crazyflie memory."""
    traj_mems = cf.mem.get_mems(MemoryElement.TYPE_TRAJ)
    if not traj_mems:
        raise RuntimeError("No trajectory memory found on Crazyflie!")
    trajectory_mem = traj_mems[0]
    trajectory_mem.trajectory = []

    total_duration = 0
    for row in trajectory:
        duration = row[0]
        x = Poly4D.Poly(row[1:9])
        y = Poly4D.Poly(row[9:17])
        z = Poly4D.Poly(row[17:25])
        yaw = Poly4D.Poly(row[25:33])
        trajectory_mem.trajectory.append(Poly4D(duration, x, y, z, yaw))
        total_duration += duration

    trajectory_mem.write_data_sync()
    cf.high_level_commander.define_trajectory(trajectory_id, 0, len(trajectory_mem.trajectory))
    return total_duration


def load_polynomial_trajectory(path):
    """Load raw Poly4D rows: duration plus eight coefficients for each axis."""
    if not path.is_file():
        raise FileNotFoundError(f'Polynomial trajectory file not found: {path}')

    trajectory = []
    with path.open(newline='', encoding='ascii') as trajectory_file:
        reader = csv.reader(trajectory_file)
        header = next(reader, None)
        if header is None or len(header) != 33:
            raise ValueError(f'{path} must have a 33-column Poly4D header')

        for line_number, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) != 33:
                raise ValueError(
                    f'{path}:{line_number} has {len(row)} columns; expected 33'
                )
            try:
                values = [float(value) for value in row]
            except ValueError as error:
                raise ValueError(
                    f'{path}:{line_number} contains a non-numeric coefficient'
                ) from error
            if not np.isfinite(values).all() or values[0] <= 0.0:
                raise ValueError(
                    f'{path}:{line_number} has an invalid duration or coefficient'
                )
            trajectory.append(values)

    if not trajectory:
        raise ValueError(f'Polynomial trajectory file is empty: {path}')
    if len(trajectory) > 31:
        raise ValueError(
            f'{path} has {len(trajectory)} segments; Crazyflie supports at most 31'
        )
    return trajectory


def anchor_trajectory(trajectory, origin):
    """Translate a local Poly4D trajectory into absolute mocap coordinates."""
    anchored_trajectory = []
    for segment in trajectory:
        anchored_segment = list(segment)
        anchored_segment[1] += origin[0]
        anchored_segment[9] += origin[1]
        anchored_segment[17] += origin[2]
        anchored_trajectory.append(anchored_segment)
    return anchored_trajectory


def scale_trajectory_xy(trajectory, scale):
    """Scale local X/Y Poly4D coefficients without changing Z or yaw."""
    if scale <= 0.0:
        raise ValueError('Trajectory XY scale must be positive')

    scaled_trajectory = []
    for segment in trajectory:
        scaled_segment = list(segment)
        for coefficient_index in range(1, 17):
            scaled_segment[coefficient_index] *= scale
        scaled_trajectory.append(scaled_segment)
    return scaled_trajectory


def run_sequence(cf, trajectory_id, duration, trajectory, takeoff_x, takeoff_y, pattern_center,
                 trajectory_is_relative):
    commander = cf.high_level_commander

    mocap_fresh, reason = mocap_is_fresh()
    if not mocap_fresh:
        print(f'[SAFETY] Flight aborted before takeoff: {reason}')
        return

    print("\n" + "="*60)
    print("FIGURE-8 FLIGHT SEQUENCE")
    print("="*60)
    print(f"Cage bounds (from corners): X[{CAGE_BOUNDS['x_min']:.3f}, {CAGE_BOUNDS['x_max']:.3f}] "
          f"Y[{CAGE_BOUNDS['y_min']:.3f}, {CAGE_BOUNDS['y_max']:.3f}] "
          f"Z[{CAGE_BOUNDS['z_min']:.1f}, {CAGE_BOUNDS['z_max']:.1f}]")
    if trajectory_is_relative:
        print('Pattern center: live mocap position at trajectory start')
    else:
        print(f"Pattern center: ({pattern_center[0]:.3f}, {pattern_center[1]:.3f})")
    print(f"Takeoff position: ({takeoff_x:.3f}, {takeoff_y:.3f})")
    print(f"Safety margin: {SAFETY_MARGIN}m")
    print(f"Flight height: {FLIGHT_HEIGHT}m")
    print(f"Figure-8 amplitude: {FIGURE8_AMPLITUDE}m")
    if USE_GENERATED_POLYNOMIAL_TRAJECTORY:
        print(f"Generated trajectory XY scale: {POLYNOMIAL_TRAJECTORY_XY_SCALE}")
    print("="*60 + "\n")

    # Absolute trajectories need to start at their configured center. Relative
    # source trajectories are anchored to live mocap after takeoff below.
    if trajectory_is_relative:
        print("[FLIGHT] Figure-eight will be anchored to the live takeoff position.")
    else:
        trajectory_start_x, trajectory_start_y = pattern_center
        current_x = current_position['x']
        current_y = current_position['y']
        start_distance = ((trajectory_start_x - current_x)**2 +
                          (trajectory_start_y - current_y)**2)**0.5
        if start_distance > START_POSITION_TOLERANCE:
            print(f"[SAFETY] Drone is {start_distance:.3f}m from the trajectory start.")
            print(f"[SAFETY] Place it near ({trajectory_start_x:.3f}, "
                  f"{trajectory_start_y:.3f}) before running this script.")
            print("[SAFETY] Flight aborted before takeoff.")
            return
        print(f"[FLIGHT] Starting {start_distance:.3f}m from trajectory center")
    print(f"[FLIGHT] Taking off to {FLIGHT_HEIGHT}m...")
    if HOVER_ONLY_TEST:
        reset_hover_diagnostic_log()
        append_hover_diagnostic_sample('pre_takeoff', note='before takeoff command')
        print(f'[TEST] Hover diagnostic log: {HOVER_DIAGNOSTIC_CSV}')
    launch_xy = (current_position['x'], current_position['y'])
    commander.takeoff(FLIGHT_HEIGHT, 2.0)

    is_airborne, reason = wait_for_takeoff_height(FLIGHT_HEIGHT, launch_xy)
    print(f"[STATUS] Current position: ({current_position['x']:.2f}, "
          f"{current_position['y']:.2f}, {current_position['z']:.2f}) - {reason}")
    if HOVER_ONLY_TEST:
        append_hover_diagnostic_sample('post_takeoff', note=reason)

    if not is_airborne:
        print(f"[WARNING] Takeoff did not reach a safe height: {reason}")
        print("[SAFETY] Performing emergency land...")
        commander.land(0.0, 2.0)
        time.sleep(2.5)
        return

    if HOVER_ONLY_TEST:
        pattern_center = (current_position['x'], current_position['y'])
        print(f"[TEST] Hovering for {HOVER_TEST_DURATION:.1f}s; figure-eight is disabled.")
        hover_start = time.time()
        while time.time() - hover_start < HOVER_TEST_DURATION:
            mocap_fresh, reason = mocap_is_fresh()
            if not mocap_fresh:
                append_hover_diagnostic_sample('hover_abort', pattern_center, reason)
                print(f'[SAFETY] Hover guard tripped: {reason}')
                break
            is_safe, reason = check_position_safe(
                current_position['x'], current_position['y'], current_position['z'])
            if not is_safe:
                append_hover_diagnostic_sample('hover_abort', pattern_center, reason)
                print(f"[SAFETY] Hover guard tripped: {reason}")
                break
            drift = center_drift_from_pattern(pattern_center)
            append_hover_diagnostic_sample('hover', pattern_center)
            if drift > MAX_CENTER_DRIFT:
                note = f'Hover drift {drift:.3f}m exceeded {MAX_CENTER_DRIFT:.3f}m'
                append_hover_diagnostic_sample('hover_abort', pattern_center, note)
                print(f"[SAFETY] {note}")
                break
            time.sleep(0.1)
        print("[TEST] Landing after hover-only test...")
        commander.land(0.0, 2.0)
        time.sleep(2.5)
        commander.stop()
        append_hover_diagnostic_sample('landed', pattern_center)
        print(f'[TEST] Hover diagnostic log saved to {HOVER_DIAGNOSTIC_CSV}')
        return

    if trajectory_is_relative:
        pattern_center = (current_position['x'], current_position['y'])
        validation_origin = (
            pattern_center[0], pattern_center[1], current_position['z']
        )
        print('[INFO] Anchoring figure-eight to live mocap position: '
              f'({validation_origin[0]:.3f}, {validation_origin[1]:.3f}, '
              f'{validation_origin[2]:.3f})...')
        trajectory = anchor_trajectory(trajectory, validation_origin)
        is_valid, error_msg = validate_trajectory(
            trajectory
        )
        if not is_valid:
            print(f'[ERROR] Trajectory validation failed: {error_msg}')
            print('[SAFETY] Landing without starting the figure-eight.')
            commander.land(0.0, 2.0)
            time.sleep(2.5)
            return
        print('[INFO] Uploading live-anchored trajectory...')
        duration = upload_trajectory(cf, trajectory_id, trajectory)

    # Execute figure-8 trajectory with continuous boundary monitoring
    print(f"[FLIGHT] Starting figure-8 trajectory ({duration:.1f}s)...")
    # The source path was local, but it has now been translated into the
    # absolute mocap frame from the live post-takeoff pose.
    relative = False
    trajectory_timescale = TRAJECTORY_TIME_SCALE
    commander.start_trajectory(trajectory_id, trajectory_timescale, relative)
    
    # Monitor position during trajectory execution
    start_time = time.time()
    check_interval = 0.2  # EXPERIMENT: How often to check boundaries (seconds) - lower = more frequent checks but more CPU
    # Adjust wait time based on trajectory timescale (slower trajectory = longer wait)
    adjusted_duration = duration * trajectory_timescale
    while (time.time() - start_time) < (adjusted_duration + 2.0):  # Add extra buffer for slower, more relaxed movement
        mocap_fresh, reason = mocap_is_fresh()
        if not mocap_fresh:
            print(f'\n[WARNING] Mocap lost during flight: {reason}')
            print('[SAFETY] Aborting trajectory and performing emergency landing...')
            commander.stop()
            commander.land(0.0, 2.0)
            time.sleep(2.5)
            return

        # Check position safety during flight
        is_safe, reason = check_position_safe(
            current_position['x'],
            current_position['y'],
            current_position['z']
        )
        
        if not is_safe:
            print(f"\n[WARNING] Boundary violation detected during flight!")
            print(f"[STATUS] Position: ({current_position['x']:.2f}, "
                  f"{current_position['y']:.2f}, {current_position['z']:.2f})")
            print(f"[REASON] {reason}")
            print("[SAFETY] Aborting trajectory and performing emergency landing...")
            commander.stop()
            commander.land(0.0, 2.0)
            time.sleep(2.5)
            return
        
        drift = center_drift_from_pattern(pattern_center)
        if drift > MAX_CENTER_DRIFT:
            print(f"\n[WARNING] Center drift {drift:.3f}m exceeded {MAX_CENTER_DRIFT:.3f}m")
            print("[SAFETY] Aborting trajectory and performing emergency landing...")
            commander.stop()
            commander.land(0.0, 2.0)
            time.sleep(2.5)
            return

        time.sleep(check_interval)
    
    # Land
    print("[FLIGHT] Landing...")
    commander.land(0.0, 2.0)  # EXPERIMENT: Second parameter is landing velocity (m/s) - increase for faster landing
    time.sleep(2.5)  # EXPERIMENT: Wait time after landing (seconds) - adjust based on landing speed
    commander.stop()
    print("\n[SUCCESS] Flight complete! Drone safely landed.\n")


def main():
    global CAGE_BOUNDS
    
    cflib.crtp.init_drivers()

    # Calculate bounds from corner points
    print("[INFO] Calculating boundaries from corner points...")
    CAGE_BOUNDS = calculate_bounds_from_corners(CORNER_POINTS, z_min=0.0, z_max=FLIGHT_HEIGHT + 1.0)
    print(f"[INFO] Calculated bounds: X[{CAGE_BOUNDS['x_min']:.3f}, {CAGE_BOUNDS['x_max']:.3f}] "
          f"Y[{CAGE_BOUNDS['y_min']:.3f}, {CAGE_BOUNDS['y_max']:.3f}] "
          f"Z[{CAGE_BOUNDS['z_min']:.1f}, {CAGE_BOUNDS['z_max']:.1f}]")
    
    # Calculate pattern center
    if PATTERN_CENTER is None:
        pattern_center = calculate_center_from_corners(CORNER_POINTS)
        print(f"[INFO] Auto-calculated pattern center: ({pattern_center[0]:.3f}, {pattern_center[1]:.3f})")
    else:
        pattern_center = PATTERN_CENTER
        print(f"[INFO] Using manual pattern center: ({pattern_center[0]:.3f}, {pattern_center[1]:.3f})")
    
    # Calculate takeoff position
    print(f"[INFO] Calculating takeoff position from corner {TAKEOFF_CORNER}...")
    takeoff_x, takeoff_y = calculate_takeoff_position(TAKEOFF_CORNER, CORNER_POINTS, CAGE_BOUNDS, SAFETY_MARGIN)
    print(f"[INFO] Safe takeoff position: ({takeoff_x:.3f}, {takeoff_y:.3f})")

    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        cf = scf.cf
        trajectory_id = 1

        # Connect to the mocap system
        print("[INFO] Connecting to mocap system...")
        mocap_wrapper = MocapWrapper(rigid_body_name)
        mocap_wrapper.on_pose = lambda pose: send_extpose_quat(cf, pose[0], pose[1], pose[2], pose[3])
        
        # Wait for mocap to get initial position and verify data is flowing
        print("[INFO] Waiting for initial position data...")
        initial_wait_time = 2.0  # EXPERIMENT: Wait time for mocap initialization (seconds)
        time.sleep(initial_wait_time)
        
        # Verify mocap is sending position data
        print("[INFO] Verifying mocap position data...")
        mocap_fresh, reason = mocap_is_fresh()
        if not mocap_fresh:
            print(f'[ERROR] {reason}; refusing to arm.')
            print(f'[ERROR] Check VRPN, host_name, and rigid_body_name ({rigid_body_name!r}).')
            mocap_wrapper.close()
            return
        initial_pos = {'x': current_position['x'], 'y': current_position['y'], 'z': current_position['z']}
        print(f"[INFO] Initial position: ({initial_pos['x']:.3f}, {initial_pos['y']:.3f}, {initial_pos['z']:.3f})")
        time.sleep(1.0)  # Wait a bit more to see if position updates
        print(f"[INFO] Current position: ({current_position['x']:.3f}, {current_position['y']:.3f}, {current_position['z']:.3f})")
        
        if (abs(current_position['x'] - initial_pos['x']) < 0.001 and 
            abs(current_position['y'] - initial_pos['y']) < 0.001 and
            abs(current_position['z'] - initial_pos['z']) < 0.001):
            print("[WARNING] Mocap position appears static - position may not be updating!")
            print("[WARNING] This might be OK if drone is stationary, but verify mocap is tracking.")
        else:
            print(f"[INFO] Mocap position data is flowing (position changed)")

        print("[INFO] Adjusting orientation sensitivity...")
        adjust_orientation_sensitivity(cf)
        print("[INFO] Activating Kalman estimator...")
        activate_kalman_estimator(cf)
        
        # In relative mode, (0, 0, 0) is the takeoff setpoint. The real mocap
        # origin is captured and validated after takeoff, just before launch.
        trajectory_is_relative = START_FIGURE8_AT_CURRENT_POSITION
        if USE_GENERATED_POLYNOMIAL_TRAJECTORY and not trajectory_is_relative:
            print('[ERROR] The generated polynomial trajectory requires relative mode.')
            print('[SAFETY] Aborting before upload.')
            mocap_wrapper.close()
            return

        if trajectory_is_relative:
            execution_center = None
            trajectory_center = (0.0, 0.0)
            validation_origin = None
            print('[INFO] Preparing figure-8 relative to the live mocap '
                  'position at trajectory start...')
        else:
            execution_center = pattern_center
            trajectory_center = pattern_center
            validation_origin = (0.0, 0.0, 0.0)
            print(f"[INFO] Generating figure-8 centered at "
                  f"({pattern_center[0]:.3f}, {pattern_center[1]:.3f})...")

        if USE_GENERATED_POLYNOMIAL_TRAJECTORY:
            print(f'[INFO] Loading generated polynomial trajectory: '
                  f'{POLYNOMIAL_TRAJECTORY_CSV}')
            figure8_trajectory = load_polynomial_trajectory(
                POLYNOMIAL_TRAJECTORY_CSV
            )
            figure8_trajectory = scale_trajectory_xy(
                figure8_trajectory, POLYNOMIAL_TRAJECTORY_XY_SCALE
            )
            print('[INFO] Scaled generated trajectory X/Y by '
                  f'{POLYNOMIAL_TRAJECTORY_XY_SCALE}')
        else:
            figure8_trajectory = generate_figure8_trajectory(
                center_x=trajectory_center[0],
                center_y=trajectory_center[1],
                relative_to_start=trajectory_is_relative,
            )

        # Absolute trajectories can be validated now. Relative trajectories are
        # validated from the live post-takeoff pose in run_sequence().
        if not trajectory_is_relative:
            print('[INFO] Validating trajectory safety...')
            is_valid, error_msg = validate_trajectory(
                figure8_trajectory, origin=validation_origin
            )
            if not is_valid:
                print(f'[ERROR] Trajectory validation failed: {error_msg}')
                print('[SAFETY] Aborting flight.')
                mocap_wrapper.close()
                return
        
        print("[INFO] Uploading trajectory to Crazyflie...")
        duration = upload_trajectory(cf, trajectory_id, figure8_trajectory)
        print(f'[INFO] Trajectory uploaded. Total duration: {duration:.1f} seconds')
        
        print("[INFO] Resetting estimator...")
        enable_high_level_commander(cf)
        reset_estimator(cf)
        print("[INFO] Estimator reset complete. Waiting briefly for convergence...")
        # Give estimator time to receive position updates from mocap
        # Note: reset_estimator() already waits for position, so this is just a brief pause
        time.sleep(1.0)  # EXPERIMENT: Brief wait after reset (usually sufficient)
        print("[INFO] Estimator ready - proceeding with flight")

        estimate_log_config = setup_estimate_logger(cf)
        print(f'[INFO] Logging Crazyflie stateEstimate to {HOVER_DIAGNOSTIC_CSV}')

        mocap_fresh, reason = mocap_is_fresh()
        if not mocap_fresh:
            print(f'[SAFETY] Mocap check failed before arming: {reason}')
            estimate_log_config.stop()
            mocap_wrapper.close()
            return

        if trajectory_is_relative:
            horizontal_safe, reason = check_position_safe(
                current_position["x"], current_position["y"], FLIGHT_HEIGHT
            )
            if not horizontal_safe:
                print(f"[SAFETY] Current takeoff position is unsafe: {reason}")
                print("[SAFETY] Flight aborted before arming.")
                estimate_log_config.stop()
                mocap_wrapper.close()
                return
        else:
            start_distance = ((pattern_center[0] - current_position["x"])**2 +
                              (pattern_center[1] - current_position["y"])**2)**0.5
            if start_distance > START_POSITION_TOLERANCE:
                print(f"[SAFETY] Drone is {start_distance:.3f}m from the trajectory start.")
                print(f"[SAFETY] Place it near ({pattern_center[0]:.3f}, "
                      f"{pattern_center[1]:.3f}) before running this script.")
                print("[SAFETY] Flight aborted before arming.")
                estimate_log_config.stop()
                mocap_wrapper.close()
                return

        previous_flight_limits = {}
        try:
            if APPLY_CONSERVATIVE_FLIGHT_LIMITS:
                print('[INFO] Applying conservative lateral flight limits: '
                      f'{MAX_ROLL_PITCH_DEGREES:.1f} degrees roll/pitch, '
                      f'{MAX_HORIZONTAL_SPEED:.2f} m/s X/Y velocity')
                previous_flight_limits = apply_conservative_flight_limits(cf)
                time.sleep(0.2)
            else:
                print('[INFO] Conservative lateral flight limits disabled.')

            # Arm only after the temporary limits have been sent.
            print("[INFO] Arming drone...")
            cf.platform.send_arming_request(True)
            time.sleep(1.0)
            run_sequence(
                cf, trajectory_id, duration, figure8_trajectory, takeoff_x,
                takeoff_y, execution_center,
                trajectory_is_relative
            )
            time.sleep(1)
            cf.platform.send_arming_request(False)
        except KeyboardInterrupt:
            print("\n[INTERRUPT] Keyboard interrupt detected!")
            print("[SAFETY] Emergency landing...")
            cf.high_level_commander.land(0.0, 2.0)
            time.sleep(2.5)
            cf.platform.send_arming_request(False)
        except Exception as e:
            print(f"\n[ERROR] Exception during flight: {e}")
            print("[SAFETY] Emergency landing...")
            cf.high_level_commander.land(0.0, 2.0)
            time.sleep(2.5)
            cf.platform.send_arming_request(False)
        finally:
            if previous_flight_limits:
                print('[INFO] Restoring previous PID flight limits...')
                restore_flight_limits(cf, previous_flight_limits)
            if estimate_log_config is not None:
                estimate_log_config.stop()

        if mocap_wrapper:
            mocap_wrapper.close()


if __name__ == '__main__':
    main()
