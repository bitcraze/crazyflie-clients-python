#!/usr/bin/env python
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
Kinect controller
"""

import sys
import os
import logging
import signal

import cflib.crtp
from cflib.crazyflie import Crazyflie
import cfclient.utils
from kinect.kinect import Kinect
from kinect.pid import PID, PID_RP

from cfclient.utils.config import Config

# Roll/pitch limit
CAP = 15.0
# Thrust limit
TH_CAP = 55000

class KinectPilot():
    """Crazyflie Kinect Pilot"""

    def __init__(self):
        """Initialize the headless client and libraries"""
        cflib.crtp.init_drivers()

        self._cf = Crazyflie(ro_cache=sys.path[0]+"/cflib/cache",
                             rw_cache=sys.path[1]+"/cache")

        self.kinect = Kinect(self)

        # Create PID controllers for piloting the Crazyflie
        # The Kinect camera is in the back of the Crazyflie so
        # pitch = depth, roll = x, thrust = y
        self.r_pid = PID_RP(P=0.05, D=1.0, I=0.00025, set_point=0.0)
        self.p_pid = PID_RP(P=0.1, D=1.0, I=0.00025, set_point=0.0)
        self.t_pid = PID(P=30.0, D=500.0, I=40.0, set_point=0.0)

        self.sp_x = 320
        self.sp_y = 240

        signal.signal(signal.SIGINT, signal.SIG_DFL) 

    def connect_crazyflie(self, link_uri):
        """Connect to a Crazyflie on the given link uri"""
        self._cf.connectionFailed.add_callback(self._connection_failed)
        self._cf.open_link(link_uri)

    def _connection_failed(self, link, message):
        """Callback for a failed Crazyflie connection"""
        print "Connection failed on {}: {}".format(link, message)
        sys.exit(-1)

    def _p2t(self, percentage):
        """Convert a percentage to raw thrust"""
        return int(65000 * (percentage / 100.0))

    def set_sp_callback(self, x, y):
        self.sp_x = x
        self.sp_y = y

    def control(self, dry=False):
        """Control loop for Kinect control"""
        safety = 10
        while True:
            (x,y,depth) = self.kinect.find_position()
            if x and y and depth:
                safety = 10
                roll = self.r_pid.update(self.sp_x-x)
                pitch = self.p_pid.update(180-depth)
                thrust = self.t_pid.update(self.sp_y-y)
                roll_sp = -roll
                pitch_sp = -pitch
                thrust_sp = thrust+38000
                if (roll_sp > CAP):
                    roll_sp = CAP
                if (roll_sp < -CAP):
                    roll_sp = -CAP             

                if (pitch_sp > CAP):
                    pitch_sp = CAP
                if (pitch_sp < -CAP):
                    pitch_sp = -CAP             

                if (thrust_sp > TH_CAP):
                    thrust_sp = TH_CAP
                if (thrust_sp < 0):
                    thrust_sp = 0

                print self.t_pid.error

                #texts = ["R=%.2f,P=%.2f,T=%.2f" % (roll_sp, pitch_sp, thrust_sp),
                #         "TH: P=%.2f" % self.t_pid.P_value,
                #         "TH: D=%.2f" % self.t_pid.D_value,
                #         "TH: I=%.2f" % self.t_pid.I_value,
                #         "TH: e=%.2f" % self.t_pid.error]
                #texts = ["R=%.2f,P=%.2f,T=%.2f" % (roll_sp, pitch_sp, thrust_sp),
                #         "R: P=%.2f" % self.r_pid.P_value,
                #         "R: I=%.2f" % self.r_pid.I_value,
                #         "R: D=%.2f" % self.r_pid.D_value,
                #         "P: P=%.2f" % self.p_pid.P_value,
                #         "P: I=%.2f" % self.p_pid.I_value,
                #         "P: D=%.2f" % self.p_pid.D_value]
                texts = []
                self.kinect.show(texts)
                self.kinect.show_xy_sp(self.sp_x, self.sp_y)
                if not dry:
                    self._cf.commander.send_setpoint(roll_sp, pitch_sp-2.0, 0, thrust_sp)
            else:
                safety = safety - 1
            if safety < 0 and not dry:
                self._cf.commander.send_setpoint(0, 0, 0, 0)
                

def main():
    """Main Crazyflie Kinect application"""
    import argparse

    parser = argparse.ArgumentParser(prog="cfkinect")
    parser.add_argument("-u", "--uri", action="store", dest="uri", type=str,
                        default="radio://0/10/250K",
                        help="URI to use for connection to the Crazyradio"
                             " dongle, defaults to radio://0/10/250K")
    parser.add_argument("-y", "--dry", dest="dry", action="store_true",
                        help="Do not send commands to Crazyflie")
    parser.add_argument("-d", "--debug", action="store_true", dest="debug",
                        help="Enable debug output")
    (args, unused) = parser.parse_known_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    kinect_pilot = KinectPilot()

    if not args.dry:
        kinect_pilot.connect_crazyflie(link_uri=args.uri)

    kinect_pilot.control(args.dry)

