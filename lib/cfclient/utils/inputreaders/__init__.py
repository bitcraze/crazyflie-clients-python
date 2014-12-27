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

class InputDevice():
    def __init__(self, dev_name, dev_id, dev_reader):
        self._reader = dev_reader
        self._id = dev_id
        self.name = dev_name
        self.input_map = None
        self.data = None
        self._prev_pressed = None

    def open(self):
        self.data = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                     "thrust": -1.0, "pitchcal": 0.0, "rollcal": 0.0,
                     "estop": False, "exit":False, "althold": False,
                     "alt1": False, "alt2": False}
        self._prev_pressed = {"pitchNeg": False, "rollNeg": False,
                              "pitchPos": False, "rollPos": False}

        self._reader.open(self._id)

    def close(self):
        self._reader.close()

    def read(self):
        [axis, buttons] = self._reader.read()
        self.data["pitchcal"] = 0.0
        self.data["rollcal"] = 0.0

        self.data = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0, "thrust": 0.0,
                     "pitchcal": 0.0, "rollcal": 0.0, "estop": False, "exit": False,
                     "althold": False, "alt1": False, "alt2": False}

        i = 0
        for a in axis:
            index = "Input.AXIS-%d" % i
            try:
                if self.input_map[index]["type"] == "Input.AXIS":
                    key = self.input_map[index]["key"]
                    axisvalue = a
                    # Offset the value first
                    axisvalue = axisvalue + self.input_map[index]["offset"]
                    # All axis are in the range [-a,+a]
                    axisvalue = axisvalue * self.input_map[index]["scale"]
                    # The value is now in the correct direction and in the range [-1,1]
                    self.data[key] += axisvalue
            except Exception:
                # Axis not mapped, ignore..
                pass
            i += 1

        i = 0
        for b in buttons:
            index = "Input.BUTTON-%d" % i
            if b == 1:
                try:
                    if self.input_map[index]["type"] == "Input.BUTTON":
                        key = self.input_map[index]["key"]
                        if (key == "estop"):
                            self.data["estop"] = not self.data["estop"]
                        elif (key == "exit"):
                            self.data["exit"] = True
                        elif (key == "althold"):
                            self.data["althold"] = not self.data["althold"]
                        else: # Generic cal for pitch/roll
                            # Workaround for event vs poll
                            name = self.input_map[index]["name"]
                            self._prev_pressed[name] = True
                except Exception:
                    # Button not mapped, ignore..
                    pass
            else:
                try:
                    if self.input_map[index]["type"] == "Input.BUTTON":
                        key = self.input_map[index]["key"]
                        if (key == "althold"):
                            self.data["althold"] = False
                        # Workaround for event vs poll
                        name = self.input_map[index]["name"]
                        if self._prev_pressed[name]:
                            self.data[key] = self.input_map[index]["scale"]
                            self._prev_pressed[name] = False
                except Exception:
                    # Button not mapped, ignore..
                    pass
            i += 1

        return self.data