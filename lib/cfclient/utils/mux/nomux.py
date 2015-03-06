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
        self.name = "None"

    def add_device(self, dev, parameters):
        logger.info("Adding device {} to MUX {}".format(dev.name, self.name))
        self._devs = [dev] # We only allow one device for this Mux

    def read(self):
        data = self._devs[0].read()
        roll = data["roll"]
        pitch = data["pitch"]
        thrust = data["thrust"]
        yaw = data["yaw"]

        if self._devs[0].limit_rp:
            [roll, pitch] = self._scale_rp(roll, pitch)
            [roll, pitch] = self._trim_rp(roll, pitch)

        if self._devs[0].limit_thrust:
            thrust = self._limit_thrust(thrust,
                                        data["althold"],
                                        data["estop"])
        if self._devs[0].limit_yaw:
            yaw = self._scale_and_deadband_yaw(yaw)


        self._update_alt_hold(data["althold"])
        self._update_em_stop(data["estop"])
        self._update_alt1(data["alt1"])
        self._update_alt2(data["alt2"])

        return [roll, pitch, yaw, thrust]



