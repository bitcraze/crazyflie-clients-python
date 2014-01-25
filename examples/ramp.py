#!/usr/bin/env python
# This example shows how to control a Crazyflie using cflib

import time, sys
from threading import Thread

#FIXME: Has to be launched from within the example folder
sys.path.append("../lib")
import cflib
from cflib.crazyflie import Crazyflie

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Main:
    def __init__(self, uri):
        self.crazyflie = Crazyflie()
        self.uri = uri
        cflib.crtp.init_drivers()
 
        # You may need to update this value if your Crazyradio uses a different frequency.
        self.crazyflie.open_link(uri)
        # Set up the callback when connected
        self.crazyflie.connected.add_callback(self.connectSetupFinished)
 
    def connectSetupFinished(self, linkURI):
        # Start a separate thread to do the motor test.
        # Do not hijack the calling thread!
        Thread(target=self.pulse_command).start()
 
    def pulse_command(self):
        thrust_mult = 1
        thrust_step = 500
        thrust = 20000
        pitch = 0
        roll = 0
        yawrate = 0
        while thrust >= 20000:
            self.crazyflie.commander.send_setpoint(roll, pitch, yawrate, thrust)
            time.sleep(0.1)
            if thrust >= 25000:
                thrust_mult = -1
            thrust += thrust_step * thrust_mult
        self.crazyflie.commander.send_setpoint(0, 0, 0, 0)
        # Make sure that the last packet leaves before the link is closed
        # since the message queue is not flushed before closing
        time.sleep(0.1)
        self.crazyflie.close_link()

Main("radio://0/30/2M")