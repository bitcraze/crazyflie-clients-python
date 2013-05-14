# -*- coding: utf-8 -*-
#
#     ||          ____  _ __                           
#  +------+      / __ )(_) /_______________ _____  ___ 
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013 Bitcraze AB
#
#  Crazyflie Nano Quadcopter Client
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Headless client for the Crazyflie.
"""

import sys
import os
import logging
import signal

from PyQt4.Qt import *
from PyQt4.QtCore import QCoreApplication
import cflib.crtp
from cflib.crazyflie import Crazyflie
import cfclient.utils
from cfclient.utils.input import JoystickReader
from cfclient.utils.config import Config

if os.name == 'posix':
    print 'Disabling standard output for libraries!'
    stdout = os.dup(1)
    os.dup2(os.open('/dev/null', os.O_WRONLY), 1)
    sys.stdout = os.fdopen(stdout, 'w')

# set SDL to use the dummy NULL video driver, 
#   so it doesn't need a windowing system.
os.environ["SDL_VIDEODRIVER"] = "dummy"

class HeadlessClient(QCoreApplication):
    def __init__(self, argv, link_uri, input_config, input_device=0, list_controllers=False):
        super(HeadlessClient, self).__init__(argv)

        self._input_config = input_config
        self._input_device = input_device
        self._list_controllers = list_controllers

        # Init the CRTP drivers
        cflib.crtp.init_drivers()

        # Open up the input-device
        self._jr = JoystickReader()
        self._jr.start()

        # Connect the Crazyflie
        self._cf = Crazyflie(ro_cache=sys.path[0]+"/cflib/cache",
                             rw_cache=sys.path[1]+"/cache")
        self._cf.open_link(link_uri)

        # For now ignore the connection procedure and
        # all callbacks...it not needed for just sending
        # setpoint commands.
        
        # Set values for input from config (advanced)
        self._jr.updateMinMaxThrustSignal.emit(
            self._p2t(Config().get("min_thrust")),
            self._p2t(Config().get("max_thrust")))
        self._jr.updateMaxRPAngleSignal.emit(
            Config().get("max_rp"))
        self._jr.updateMaxYawRateSignal.emit(
            Config().get("max_yaw"))
        self._jr.updateThrustLoweringSlewrateSignal.emit(
            self._p2t(Config().get("slew_rate")),
            self._p2t(Config().get("slew_limit")))

        # Set up the joystick reader
        self._jr.sendControlSetpointSignal.connect(self._cf.commander.send_setpoint, Qt.DirectConnection)
        self._jr.inputDeviceErrorSignal.connect(self._input_dev_error)
        #self._jr.inputUpdateSignal.connect(self._j_print)
        self._jr.discovery_signal.connect(self._print_discovery)

    def _j_print(self, roll, pitch, yaw, thrust):
        print "%f,%f,%f,%f" % (roll, pitch, yaw, thrust)

    def _print_discovery(self, devs):
        for d in devs:
            print "Found controller #%i: %s" % (d["id"], d["name"])
        if self._list_controllers:
            self.exit(0)
        else:
            print "Will use [%s] for input" % devs[self._input_device]["name"]
            self._jr.startInput(devs[self._input_device]["name"], self._input_config)

    def _input_dev_error(self, m):
        print m
        self.exit(-1)

    def _p2t(self, percentage):
        return int(65000 * (percentage / 100.0))

def main():
    import argparse

    parser = argparse.ArgumentParser(prog="cfheadless")
    parser.add_argument("-u", "--uri", action="store", dest="uri", type=str, default="radio://0/10/250K",
                        help="URI to use for connection to the Crazyradio dongle, defaults to radio://0/10/250K")
    parser.add_argument("--uris", action="store_true", dest="list_uris",
                        help="Only display available radio URIs and exit")
    parser.add_argument("-i", "--input", action="store", dest="input", type=str, default="PS3_Mode_1",
                        help="Input mapping to use for the controller, defaults to PS3_Mode_1")
    parser.add_argument("-d", "--debug", action="store_true", dest="debug",
                        help="Enable debug output")
    parser.add_argument("-c", "--controller", action="store", type=int, dest="controller", default=0,
                        help="Use controller with specified id, id defaults to 0")
    (args, remaining_args) = parser.parse_known_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)


    app = HeadlessClient(remaining_args, link_uri=args.uri,
                         input_config=args.input, input_device=args.controller,
                         list_controllers=args.list_controllers)
    sys.exit(app.exec_())
