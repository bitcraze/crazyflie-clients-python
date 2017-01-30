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
Find all the available input readers and try to import them.

To create a new input device reader drop a .py file into this
directory and it will be picked up automatically.
"""

import logging
from ..inputreaderinterface import InputReaderInterface

__author__ = 'Bitcraze AB'
__all__ = ['InputDevice']

logger = logging.getLogger(__name__)


# Forces py2exe to include the input readers in the windows build
try:
    from . import pysdl2  # noqa
    from . import linuxjsdev  # noqa
except Exception:
    pass

# Statically listing the available input readers
input_readers = ["linuxjsdev",
                 "pysdl2"]

logger.info("Input readers: {}".format(input_readers))

initialized_readers = []
available_devices = []

for reader in input_readers:
    try:
        module = __import__(reader, globals(), locals(), [reader], 1)
        main_name = getattr(module, "MODULE_MAIN")
        initialized_readers.append(getattr(module, main_name)())
        logger.info("Successfully initialized [{}]".format(reader))
    except Exception as e:
        logger.info("Could not initialize [{}]: {}".format(reader, e))


def devices():
    # Todo: Support rescanning and adding/removing devices
    if len(available_devices) == 0:
        for r in initialized_readers:
            devs = r.devices()
            for dev in devs:
                available_devices.append(InputDevice(dev["name"],
                                                     dev["id"],
                                                     r))
    return available_devices


class InputDevice(InputReaderInterface):

    def __init__(self, dev_name, dev_id, dev_reader):
        super(InputDevice, self).__init__(dev_name, dev_id, dev_reader)

        # All devices supports mapping (and can be configured)
        self.supports_mapping = True

        # Limit roll/pitch/yaw/thrust for all devices
        self.limit_rp = True
        self.limit_thrust = True
        self.limit_yaw = True

    def open(self):
        # TODO: Reset data?
        self._reader.open(self.id)

    def close(self):
        self._reader.close(self.id)

    def read(self, include_raw=False):
        [axis, buttons] = self._reader.read(self.id)

        # To support split axis we need to zero all the axis
        self.data.reset_axes()

        i = 0
        for a in axis:
            index = "Input.AXIS-%d" % i
            try:
                if self.input_map[index]["type"] == "Input.AXIS":
                    key = self.input_map[index]["key"]
                    axisvalue = a + self.input_map[index]["offset"]
                    axisvalue = axisvalue / self.input_map[index]["scale"]
                    self.data.set(key, axisvalue + self.data.get(key))
            except (KeyError, TypeError):
                pass
            i += 1

        # Workaround for fixing issues during mapping (remapping buttons while
        # they are pressed.
        self.data.reset_buttons()

        i = 0
        for b in buttons:
            index = "Input.BUTTON-%d" % i
            try:
                if self.input_map[index]["type"] == "Input.BUTTON":
                    key = self.input_map[index]["key"]
                    self.data.set(key, True if b == 1 else False)
            except (KeyError, TypeError):
                # Button not mapped, ignore..
                pass
            i += 1

        if self.limit_rp:
            [self.data.roll, self.data.pitch] = self._scale_rp(self.data.roll,
                                                               self.data.pitch)
        if self.limit_thrust:
            self.data.thrust = self._limit_thrust(self.data.thrust,
                                                  self.data.assistedControl,
                                                  self.data.estop)
        if self.limit_yaw:
            self.data.yaw = self._scale_and_deadband_yaw(self.data.yaw)

        if include_raw:
            return [axis, buttons, self.data]
        else:
            return self.data
