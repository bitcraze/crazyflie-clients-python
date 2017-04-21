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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
Find all the available input interfaces and try to initialize them.

"""

import logging
from ..inputreaderinterface import InputReaderInterface

__author__ = 'Bitcraze AB'
__all__ = ['InputInterface']

logger = logging.getLogger(__name__)

# Force py2exe to include interfaces module in the build
try:
    from . import leapmotion  # noqa
    from . import wiimote  # noqa
    from . import zmqpull  # noqa
except Exception:
    pass

# Statically listing input interfaces
input_interface = ["leapmotion",
                   "wiimote",
                   "zmqpull"]

logger.info("Found interfaces: {}".format(input_interface))

initialized_interfaces = []
available_interfaces = []

for interface in input_interface:
    try:
        module = __import__(interface, globals(), locals(), [interface], 1)
        main_name = getattr(module, "MODULE_MAIN")
        initialized_interfaces.append(getattr(module, main_name)())
        logger.info("Successfully initialized [{}]".format(interface))
    except Exception as e:
        logger.info("Could not initialize [{}]: {}".format(interface, e))


def devices():
    # Todo: Support rescanning and adding/removing devices
    if len(available_interfaces) == 0:
        for reader in initialized_interfaces:
            devs = reader.devices()
            for dev in devs:
                available_interfaces.append(InputInterface(
                    dev["name"], dev["id"], reader))
    return available_interfaces


class InputInterface(InputReaderInterface):

    def __init__(self, dev_name, dev_id, dev_reader):
        super(InputInterface, self).__init__(dev_name, dev_id, dev_reader)

        # These devices cannot be mapped and configured
        self.supports_mapping = False

        # Ask the reader if it wants to limit
        # roll/pitch/yaw/thrust for all devices
        self.limit_rp = dev_reader.limit_rp
        self.limit_thrust = dev_reader.limit_thrust
        self.limit_yaw = dev_reader.limit_yaw

    def open(self):
        self._reader.open(self.id)

    def close(self):
        self._reader.close(self.id)

    def read(self, include_raw=False):
        mydata = self._reader.read(self.id)
        # Merge interface returned data into InputReader Data Item
        for key in list(mydata.keys()):
            self.data.set(key, mydata[key])

        return self.data
