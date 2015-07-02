#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2014 Bitcraze AB
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.
"""

"""

__author__ = 'Bitcraze AB'
__all__ = ['NoMux']

import os
import glob
from . import InputMux
import logging
logger = logging.getLogger(__name__)

class NoMux(InputMux):
    def __init__(self, *args):
        super(NoMux, self).__init__(*args)
        self.name = "Normal"
        self._devs = {"Device": None}

    def add_device(self, dev, role):
        logger.info("Adding device {} to MUX {}".format(dev.name, self.name))
        # Save the old dev and close after the new one is opened
        self._open_new_device(dev, role)

    def read(self):
        if self._devs["Device"]:
            data = self._devs["Device"].read()
            roll = data["roll"]
            pitch = data["pitch"]
            thrust = data["thrust"]
            yaw = data["yaw"]

            if self._devs["Device"].limit_rp:
                [roll, pitch] = self._scale_rp(roll, pitch)
                [roll, pitch] = self._trim_rp(roll, pitch)

            if self._devs["Device"].limit_thrust:
                thrust = self._limit_thrust(thrust,
                                            data["althold"],
                                            data["estop"])
            if self._devs["Device"].limit_yaw:
                yaw = self._scale_and_deadband_yaw(yaw)


            self._update_alt_hold(data["althold"])
            self._update_em_stop(data["estop"])
            self._update_alt1(data["alt1"])
            self._update_alt2(data["alt2"])

            return [roll, pitch, yaw, thrust]
        else:
            return [0.0, 0.0, 0.0, 0.0]


