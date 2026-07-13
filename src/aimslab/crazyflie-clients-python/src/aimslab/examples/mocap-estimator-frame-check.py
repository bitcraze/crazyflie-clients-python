#!/usr/bin/env python3
"""Compare VRPN mocap pose with the Crazyflie estimator without flying.

This diagnostic never arms the Crazyflie and never sends takeoff, landing, or
trajectory commands. Keep the aircraft on the floor and move it by hand to
inspect the coordinate-frame and yaw relationship before another hover test.
"""

import math
import time
from threading import Lock
from threading import Thread

import cflib.crtp
import motioncapture
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.utils import uri_helper
from cflib.utils.reset_estimator import reset_estimator


URI = uri_helper.uri_from_env(default='radio://0/80/2M/E7E7E7E7E7')
HOST_NAME = '192.168.1.42:3883'
MOCAP_SYSTEM_TYPE = 'vrpn'
RIGID_BODY_NAME = 'crazyflie_21'
PRINT_INTERVAL_SECONDS = 0.2


class MocapState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.quaternion = None
        self.last_update = 0.0

    def update(self, position, quaternion):
        with self._lock:
            self.position = tuple(position)
            self.quaternion = quaternion
            self.last_update = time.monotonic()

    def snapshot(self):
        with self._lock:
            return self.position, self.quaternion, self.last_update


class EstimateState:
    def __init__(self):
        self._lock = Lock()
        self.position = None
        self.yaw_degrees = None
        self.last_update = 0.0

    def update(self, position, yaw_degrees):
        with self._lock:
            self.position = tuple(position)
            self.yaw_degrees = yaw_degrees
            self.last_update = time.monotonic()

    def snapshot(self):
        with self._lock:
            return self.position, self.yaw_degrees, self.last_update


mocap_state = MocapState()
estimate_state = EstimateState()


class MocapWrapper(Thread):
    def __init__(self, body_name):
        super().__init__(daemon=True)
        self.body_name = body_name
        self.on_pose = None
        self._stay_open = True
        self.start()

    def close(self):
        self._stay_open = False
        self.join(timeout=1.0)

    def run(self):
        mocap = motioncapture.connect(MOCAP_SYSTEM_TYPE, {'hostname': HOST_NAME})
        print(f"[INFO] Mocap connected, looking for {self.body_name!r}")
        found_body = False

        while self._stay_open:
            mocap.waitForNextFrame()
            body = mocap.rigidBodies.get(self.body_name)
            if body is None:
                continue

            if not found_body:
                print(f"[INFO] Found rigid body: {self.body_name}")
                found_body = True

            position = body.position
            mocap_state.update(position, body.rotation)
            if self.on_pose:
                self.on_pose(position)


def wait_for_fresh_mocap(timeout_seconds=5.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        position, _, last_update = mocap_state.snapshot()
        if position is not None and time.monotonic() - last_update < 1.0:
            return
        time.sleep(0.05)
    raise RuntimeError('No fresh VRPN pose was received')


def setup_estimator_logger(cf):
    log_config = LogConfig(name='FrameCheck', period_in_ms=100)
    log_config.add_variable('stateEstimate.x', 'float')
    log_config.add_variable('stateEstimate.y', 'float')
    log_config.add_variable('stateEstimate.z', 'float')
    log_config.add_variable('stabilizer.yaw', 'float')

    def on_data(timestamp, data, config):
        del timestamp
        del config
        estimate_state.update(
            (data['stateEstimate.x'], data['stateEstimate.y'], data['stateEstimate.z']),
            data['stabilizer.yaw'],
        )

    def on_error(config, message):
        print(f"[WARN] Estimator logger error from {config.name}: {message}")

    cf.log.add_config(log_config)
    log_config.data_received_cb.add_callback(on_data)
    log_config.error_cb.add_callback(on_error)
    log_config.start()
    return log_config


def quaternion_yaw_degrees(quaternion):
    sin_yaw = 2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y)
    cos_yaw = 1.0 - 2.0 * (quaternion.y ** 2 + quaternion.z ** 2)
    return math.degrees(math.atan2(sin_yaw, cos_yaw))


def print_comparison():
    mocap_position, mocap_quaternion, mocap_update = mocap_state.snapshot()
    estimate_position, estimate_yaw, estimate_update = estimate_state.snapshot()

    if estimate_position is None:
        print('[WAIT] Waiting for Crazyflie estimator log data...')
        return

    delta = tuple(
        estimate_position[axis] - mocap_position[axis] for axis in range(3)
    )
    mocap_yaw = quaternion_yaw_degrees(mocap_quaternion)
    print(
        '[FRAME] '
        f"mocap=({mocap_position[0]:+.3f}, {mocap_position[1]:+.3f}, {mocap_position[2]:+.3f}) "
        f"estimate=({estimate_position[0]:+.3f}, {estimate_position[1]:+.3f}, {estimate_position[2]:+.3f}) "
        f"delta=({delta[0]:+.3f}, {delta[1]:+.3f}, {delta[2]:+.3f}) "
        f"mocap_yaw={mocap_yaw:+.1f}deg cf_yaw={estimate_yaw:+.1f}deg "
        f"ages=({time.monotonic() - mocap_update:.2f}s, "
        f"{time.monotonic() - estimate_update:.2f}s)"
    )


def main():
    print('[INFO] UNARMED FRAME CHECK: no flight commands are sent.')
    print('[INFO] Keep the Crazyflie on the floor. Move it slowly by hand along')
    print('[INFO] cage X and Y, then rotate it about vertical. Press Ctrl+C to stop.')

    cflib.crtp.init_drivers()
    mocap_wrapper = MocapWrapper(RIGID_BODY_NAME)
    log_config = None

    try:
        with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
            cf = scf.cf
            mocap_wrapper.on_pose = lambda position: cf.extpos.send_extpos(
                position[0], position[1], position[2]
            )

            wait_for_fresh_mocap()
            cf.param.set_value('stabilizer.estimator', '2')
            log_config = setup_estimator_logger(cf)
            print('[INFO] Resetting estimator while VRPN position is streaming...')
            reset_estimator(cf)

            while True:
                print_comparison()
                time.sleep(PRINT_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print('\n[INFO] Frame check stopped.')
    finally:
        if log_config:
            log_config.stop()
        mocap_wrapper.close()


if __name__ == '__main__':
    main()
