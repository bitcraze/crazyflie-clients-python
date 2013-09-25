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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
Headless client for the Crazyflie.
"""

import sys
import os
import logging
import signal

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

class HeadlessClient():
    """Crazyflie headless client"""

    def __init__(self):
        """Initialize the headless client and libraries"""
        cflib.crtp.init_drivers()

        self._jr = JoystickReader(do_device_discovery=False)

        self._cf = Crazyflie(ro_cache=sys.path[0]+"/cflib/cache",
                             rw_cache=sys.path[1]+"/cache")

        signal.signal(signal.SIGINT, signal.SIG_DFL) 

    def setup_controller(self, input_config, input_device=0):
        """Set up the device reader""" 
        # Set up the joystick reader
        self._jr.device_error.add_callback(self._input_dev_error)

        devs = self._jr.getAvailableDevices()
        print "Will use [%s] for input" % devs[input_device]["name"]
        self._jr.start_input(devs[input_device]["name"],
                             input_config)

    def list_controllers(self):
        """List the available controllers"""
        for dev in self._jr.getAvailableDevices():
            print "Controller #{}: {}".format(dev["id"], dev["name"])

    def connect_crazyflie(self, link_uri):
        """Connect to a Crazyflie on the given link uri"""
        self._cf.connectionFailed.add_callback(self._connection_failed)
        self._cf.open_link(link_uri)
        self._jr.input_updated.add_callback(self._cf.commander.send_setpoint)

    def _connection_failed(self, link, message):
        """Callback for a failed Crazyflie connection"""
        print "Connection failed on {}: {}".format(link, message)
        self._jr.stop_input()
        sys.exit(-1)

    def _input_dev_error(self, message):
        """Callback for an input device error"""
        print "Error when reading device: {}".format(message)
        sys.exit(-1)

def main():
    """Main Crazyflie headless application"""
    import argparse

    parser = argparse.ArgumentParser(prog="cfheadless")
    parser.add_argument("-u", "--uri", action="store", dest="uri", type=str,
                        default="radio://0/10/250K",
                        help="URI to use for connection to the Crazyradio"
                             " dongle, defaults to radio://0/10/250K")
    parser.add_argument("-i", "--input", action="store", dest="input",
                        type=str, default="PS3_Mode_1",
                        help="Input mapping to use for the controller,"
                             "defaults to PS3_Mode_1")
    parser.add_argument("-d", "--debug", action="store_true", dest="debug",
                        help="Enable debug output")
    parser.add_argument("-c", "--controller", action="store", type=int,
                        dest="controller", default=0,
                        help="Use controller with specified id,"
                             " id defaults to 0")
    parser.add_argument("--controllers", action="store_true",
                        dest="list_controllers",
                        help="Only display available controllers and exit")
    (args, unused) = parser.parse_known_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    headless = HeadlessClient()

    if (args.list_controllers):
        headless.list_controllers()
    else:
        headless.setup_controller(input_config=args.input,
                                  input_device=args.controller)
        headless.connect_crazyflie(link_uri=args.uri)

