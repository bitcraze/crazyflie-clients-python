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
__all__ = ['MixMux']

import os
import glob
import logging

from . import InputMux

logger = logging.getLogger(__name__)

class MixMux(InputMux):
    def __init__(self, *args):
        super(MixMux, self).__init__(*args)
        self.name = "MixMux"
        self._mix_axes = ("roll", "pitch", "yaw", "thrust")
        self._mix_buttons = ("alt1", "alt2", "estop")

    def add_device(self, dev, parameters):
        logger.info("Adding device {} to {}".format(dev.name, self.name))
        logger.info("Device has mapping {}".format(dev.input_map_name))
        self._devs.append(dev)

    def get_supported_dev_count(self):
        return 2

    def _estop_callback(self, state):
        logger.info(state)

    def read(self):
        try:
            d1 = self._devs[0].read()
            d2 = self._devs[1].read()

            # Master has precedence if the axis/button is not mixed
            data = d1

            for a in self._mix_axes:
                data[a] += d2[a]

            for b in self._mix_buttons:
                data[b] |= d2[b]

            # Now res contains the mix of the two
            [roll, pitch] = self._scale_rp(data["roll"], data["pitch"])
            [roll, pitch] = self._trim_rp(roll, pitch)
            self._update_alt_hold(data["althold"])
            self._update_em_stop(data["estop"])
            self._update_alt1(data["alt1"])
            self._update_alt2(data["alt2"])
            thrust = self._limit_thrust(data["thrust"],
                                        data["althold"],
                                        data["estop"])

            yaw = self._scale_and_deadband_yaw(data["yaw"])

            return [roll, pitch, yaw, thrust]

        except Exception as e:
            logger.info("Could not read devices: {}".format(e))
            return [0.0, 0.0, 0.0, 0.0]
