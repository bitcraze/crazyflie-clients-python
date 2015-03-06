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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Find all the available input readers and try to import them.

To create a new input device reader drop a .py file into this
directory and it will be picked up automatically.
"""

__author__ = 'Bitcraze AB'
__all__ = ['InputDevice']

import os
import glob
import logging
from cfclient.utils.inputreaderinterface import InputReaderInterface

logger = logging.getLogger(__name__)

found_readers = [os.path.splitext(os.path.basename(f))[0] for
             f in glob.glob(os.path.dirname(__file__) + "/[A-Za-z]*.py")]
if len(found_readers) == 0:
    found_readers = [os.path.splitext(os.path.basename(f))[0] for
                 f in glob.glob(os.path.dirname(__file__) +
                                "/[A-Za-z]*.pyc")]

logger.info("Found readers: {}".format(found_readers))

initialized_readers = []
available_devices = []

for reader in found_readers:
    try:
        module = __import__(reader, globals(), locals(), [reader], -1)
        main_name = getattr(module, "MODULE_MAIN")
        initialized_readers.append(getattr(module, main_name)())
        logger.info("Successfully initialized [{}]".format(reader))
    except Exception as e:
        logger.info("Could not initialize [{}]: {}".format(reader, e))
        #import traceback
        #logger.info(traceback.format_exc())

def devices():
    # Todo: Support rescanning and adding/removing devices
    if len(available_devices) == 0:
        for reader in initialized_readers:
            devs = reader.devices()
            for dev in devs:
                available_devices.append(InputDevice(dev["name"],
                                                     dev["id"],
                                                     reader))
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
        self.data = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                     "thrust": -1.0, "estop": False, "exit":False,
                     "althold": False, "alt1": False, "alt2": False,
                     "pitchNeg": False, "rollNeg": False,
                     "pitchPos": False, "rollPos": False}

        self._reader.open(self.id)

    def close(self):
        self._reader.close(self.id)

    def _zero_all_buttons(self):
        buttons = ("estop", "exit", "althold", "alt1", "alt2", "rollPos",
                   "rollNeg", "pitchPos", "pitchNeg")
        for b in buttons:
            self.data[b] = False

    def read(self, include_raw=False):
        [axis, buttons] = self._reader.read(self.id)

        # To support split axis we need to zero all the axis
        self.data["roll"] = 0.0
        self.data["pitch"] = 0.0
        self.data["yaw"] = 0.0
        self.data["thrust"] = 0.0

        i = 0
        for a in axis:
            index = "Input.AXIS-%d" % i
            try:
                if self.input_map[index]["type"] == "Input.AXIS":
                    key = self.input_map[index]["key"]
                    axisvalue = a + self.input_map[index]["offset"]
                    axisvalue = axisvalue / self.input_map[index]["scale"]
                    self.data[key] += axisvalue
            except Exception:
                #logger.warning("Axis {}".format(i))
                pass
            i += 1

        # Workaround for fixing issues during mapping (remapping buttons while
        # they are pressed.
        self._zero_all_buttons()

        i = 0
        for b in buttons:
            index = "Input.BUTTON-%d" % i
            try:
                if self.input_map[index]["type"] == "Input.BUTTON":
                    key = self.input_map[index]["key"]
                    self.data[key] = True if b == 1 else False
            except Exception:
                # Button not mapped, ignore..
                pass
            i += 1

        if include_raw:
            return [axis, buttons, self.data]
        else:
            #logger.warning(self.data)
            #if self.id == 0:
            #    logger.info("{}".format(self.input_map["Input.AXIS-3"]["key"]))
            #    logger.info("{}:{}".format(self.id, self.data["thrust"]))
            return self.data