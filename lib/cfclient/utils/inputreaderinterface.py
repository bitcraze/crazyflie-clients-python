#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
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
Interface for reading input devices and interfaces
"""


class InputReaderInterface(object):

    def __init__(self, dev_name, dev_id, dev_reader):
        """Initialize the reader"""
        # Set if the device supports mapping and can be configured
        self.supports_mapping = True

        # Set if the MUX should automatically limit roll/pitch/thrust/yaw
        # according to the settings in the UI
        self.limit_rp = True
        self.limit_thrust = True
        self.limit_yaw = True

        self._reader = dev_reader
        self.id = dev_id
        self.name = dev_name
        self.input_map = None
        self.input_map_name = ""
        self.data = None
        self._prev_pressed = None
        self.reader_name = dev_reader.name

        self.data = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                     "thrust": 0.0, "estop": False, "exit": False,
                     "althold": False, "alt1": False, "alt2": False,
                     "pitchNeg": False, "rollNeg": False,
                     "pitchPos": False, "rollPos": False}

    def open(self, device_id):
        """Initalize the reading and open the device with deviceId and set the mapping for axis/buttons using the
        inputMap"""
        return

    def read(self, device_id):
        """Read input from the selected device."""
        return None

    def close(self, device_id):
        return

    def devices(self):
        """List all the available devices."""
        return []