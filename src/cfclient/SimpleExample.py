import time
import qtm

import cflib.crtp
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.syncLogger import SyncLogger

from twisted.internet import threads

# The channel and bandwidth we will try to connect the Crazyflie on
uri = "radio://0/83/2M"

# The ip address of the computer running QTM
qtm_ip = "127.0.0.1"

# SyncronousCrazyflie
scf = None

# Coordinates of the path which the Crazyflie will follow (X, Y, Z, Yaw) set in (m)
flight_path = [
    (0, 0, 1.2, 0.0),
    (1, 0, 1.2, 0.0),
    (0, 1, 1.2, 0.0),
    (-1, 0, 1.2, 0.0),
    (0, -1, 1.2, 0.0),
    (1, 0, 1.2, 0.0),
    (0, 0, 1.2, 0.0),
    (0, 0, 0.3, 0.0),
    (0, 0, 0.15, 0.0),
]


def on_connect(connection, version):
    """Callback when QTM has been connected"""
    print('Connected to QTM with {}'.format(version.decode("UTF-8")))

    # The 'connection' object represents the connection with QTM and is used to interact with QTM
    # Make sure that the last thing done with the connection object is the
    # 'stream_frame' call due to QTMRTProtocol internals
    connection.stream_frames(frames='allframes', components=['6deuler'], on_packet=on_packet)


def on_disconnect(reason):
    """Callback when QTM has been disconnected"""
    print(reason)


def on_event(event):
    """Callback when QTM sends an event"""
    print(event)


def on_packet(packet):
    """Callback once every packet sent by QTM"""
    global scf

    # Unpack the data from QTM
    header, bodies = packet.get_6d_euler()
    # 'Bodies' contains a list of the requested data, in this case position and rotation data of the 6DoF objects
    # currently in QTM


    if scf is None or bodies is None:
        # Crazyflie not yet created or no packet with a 6DoF body received, most likely because of QTM settings...
        return

    # Blindly assume that the first object in the list is the Crazyflie and save the X, Y, Z
    # The positions returned by QTM is in 'mm' divide by 1000 to get them in 'm'
    x = bodies[1][0][0]/1000
    y = bodies[1][0][1]/1000
    z = bodies[1][0][2]/1000

    # If QTM temporarily looses tracking it returns 'Nan'
    # If we would send that forward to the Crazyflie it would crash
    # Check if x, y, z have assigned values (that they are not Nan)
    if x == x and y == y and z == z:
        # If they have, feed the actual position of the Crazyflie back to the Crazyflie, to allow for self correction
        scf.cf.extpos.send_extpos(x, y, z)


def flight_controller():
    global scf
    with SyncCrazyflie(uri) as _scf:
        scf = _scf
        # reset the kalman filter and find a new estimated position
        reset_estimator(scf)
        fly_along_path(scf, flight_path)


def reset_estimator(scf):
    # Reset the Kalman filter

    cf = scf.cf
    cf.param.set_value('kalman.resetEstimation', '1')
    time.sleep(0.1)
    cf.param.set_value('kalman.resetEstimation', '0')

    wait_for_position_estimator(scf)


def wait_for_position_estimator(scf):
    print('Waiting for estimator to find stable position...')


    log_config = LogConfig(name='Kalman Variance', period_in_ms=500)
    log_config.add_variable('kalman.varPX', 'float')
    log_config.add_variable('kalman.varPY', 'float')
    log_config.add_variable('kalman.varPZ', 'float')

    var_y_history = [1000] * 10
    var_x_history = [1000] * 10
    var_z_history = [1000] * 10

    threshold = 0.001

    with SyncLogger(scf, log_config) as logger:
        for log_entry in logger:
            data = log_entry[1]

            var_x_history.append(data['kalman.varPX'])
            var_x_history.pop(0)
            var_y_history.append(data['kalman.varPY'])
            var_y_history.pop(0)
            var_z_history.append(data['kalman.varPZ'])
            var_z_history.pop(0)

            min_x = min(var_x_history)
            max_x = max(var_x_history)
            min_y = min(var_y_history)
            max_y = max(var_y_history)
            min_z = min(var_z_history)
            max_z = max(var_z_history)

            if (max_x - min_x) < threshold and (
                        max_y - min_y) < threshold and (
                        max_z - min_z) < threshold:

                print("Position found with error, x: {}, y: {}, z: {}"
                      .format(max_x - min_x, max_y - min_y, max_z - min_z))
                break


def fly_along_path(scf, path):
    cf = scf.cf

    cf.param.set_value('flightmode.posSet', '1')
    time.sleep(0.1)

    for position in path:
        print('Setting position {}'.format(position))
        for i in range(50):

            # The 'send_setpoint' function takes the arguments in the order (Y, X, Yaw, Z)
            # The z-value has to be set as the actual 'thrust-value' sent to the Crazyflie and needs to be
            # multiplied by 1000
            cf.commander.send_setpoint(position[1], position[0], position[3], int(position[2] * 1000))

            # The Crazyflie needs to be sent a setpoint at least twice a second or it will stop
            time.sleep(0.1)

    cf.commander.send_setpoint(0, 0, 0, 0)
    # Make sure that the last packet leaves before the link is closed
    # since the message queue is not flushed before closing
    time.sleep(0.1)
    print("Finished")


if __name__ == '__main__':
    # Initialize the low-level drivers (don't list the debug drivers)
    cflib.crtp.init_drivers(enable_debug_driver=False)

    # Connect to QTM on a specific ip
    qrt = qtm.QRT(qtm_ip, 22223, version='1.17')
    qrt.connect(on_connect=on_connect, on_disconnect=on_disconnect, on_event=on_event)

    d = threads.deferToThread(flight_controller)
    qtm.start()
