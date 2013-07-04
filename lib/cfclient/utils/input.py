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

#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc., 51
#  Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Module to read input devices and send controls to the Crazyflie.

This module reads input from joysticks or other input devices and sends control
set-points to the Crazyflie. It can be configured in the UI.

Various drivers can be used to read input device data. Currently is uses the
PyGame driver, but in the future native support will be provided for Linux and
Windows drivers.

The input device's axes and buttons are mapped to software inputs using a
configuration file.
"""

__author__ = 'Bitcraze AB'
__all__ = ['JoystickReader']

import sys
import os
import glob
import traceback
import logging
import shutil

logger = logging.getLogger(__name__)

from cfclient.utils.pygamereader import PyGameReader
from cfclient.utils.config import Config
from cfclient.utils.config_manager import ConfigManager

from cfclient.utils.periodictimer import PeriodicTimer
from cflib.utils.callbacks import Caller

class JoystickReader:
    """
    Thread that will read input from devices/joysticks and send control-set
    ponts to the Crazyflie
    """
    inputConfig = []

    def __init__(self, do_device_discovery=True):
        # TODO: Should be OS dependant
        self.inputdevice = PyGameReader()

        self.maxRPAngle = 0
        self.thrustDownSlew = 0
        self.thrustSlewEnabled = False
        self.slewEnableLimit = 0
        self.maxYawRate = 0
        self.detectAxis = False
        self.emergencyStop = False

        self.oldThrust = 0

        self._trim_roll = Config().get("trim_roll")
        self._trim_pitch = Config().get("trim_pitch")

        # TODO: The polling interval should be set from config file
        self.readTimer = PeriodicTimer(0.01, self.readInput)

        if do_device_discovery:
            self._discovery_timer = PeriodicTimer(1.0, self._do_device_discovery)
            self._discovery_timer.start()

        self._available_devices = {}

        # Check if user config exists, otherwise copy files
        if not os.path.isdir(ConfigManager().configs_dir):
            logger.info("No user config found, copying dist files")
            os.makedirs(ConfigManager().configs_dir)
            for f in glob.glob(sys.path[0] +
                               "/cfclient/configs/input/[A-Za-z]*.json"):
                shutil.copy2(f, ConfigManager().configs_dir)

        ConfigManager().get_list_of_configs()

        self.input_updated = Caller()
        self.rp_trim_updated = Caller()
        self.emergency_stop_updated = Caller()
        self.device_discovery = Caller()
        self.device_error = Caller()

    def _do_device_discovery(self):
        devs = self.getAvailableDevices()

        if len(devs):
            self.device_discovery.call(devs)
            self._discovery_timer.stop()

    def getAvailableDevices(self):
        """List all available input devices."""
        devs = self.inputdevice.getAvailableDevices()

        for d in devs:
            self._available_devices[d["name"]] = d["id"]

        return devs

    def enableRawReading(self, deviceId):
        """
        Enable raw reading of the input device with id deviceId. This is used
        to get raw values for setting up of input devices. Values are read
        without using a mapping.
        """
        self.inputdevice.enableRawReading(deviceId)

    def disableRawReading(self):
        """Disable raw reading of input device."""
        self.inputdevice.disableRawReading()

    def readRawValues(self):
        """ Read raw values from the input device."""
        return self.inputdevice.readRawValues()

    def start_input(self, device_name, config_name):
        """
        Start reading input from the device with name device_name using config
        config_name
        """
        try:
            device_id = self._available_devices[device_name]
            self.inputdevice.start_input(
                                    device_id,
                                    ConfigManager().get_config(config_name))
            self.readTimer.start()
        except Exception:
            self.device_error.call(
                     "Error while opening/initializing  input device\n\n%s" %
                     (traceback.format_exc()))

    def stop_input(self):
        """Stop reading from the input device."""
        self.readTimer.stop()

    def set_yaw_limit(self, maxRate):
        """Set a new max yaw rate value."""
        self.maxYawRate = maxRate

    def set_rp_limit(self, maxAngle):
        """Set a new max roll/pitch value."""
        self.maxRPAngle = maxAngle

    def set_thrust_slew_limiting(self, thrustDownSlew, slewLimit):
        """Set new values for limit where the slewrate control kicks in and
        for the slewrate."""
        self.thrustDownSlew = thrustDownSlew
        self.slewEnableLimit = slewLimit
        if (thrustDownSlew > 0):
            self.thrustSlewEnabled = True
        else:
            self.thrustSlewEnabled = False

    def set_thrust_limits(self, minThrust, maxThrust):
        """Set a new min/max thrust limit."""
        self.minThrust = minThrust
        self.maxThrust = maxThrust

    def _update_trim_roll(self, trim_roll):
        """Set a new value for the roll trim."""
        self._trim_roll = trim_roll

    def _update_trim_pitch(self, trim_pitch):
        """Set a new value for the trim trim."""
        self._trim_pitch = trim_pitch

    def readInput(self):
        """Read input data from the selected device"""
        try:
            data = self.inputdevice.readInput()
            roll = data["roll"] * self.maxRPAngle
            pitch = data["pitch"] * self.maxRPAngle
            thrust = data["thrust"]
            yaw = data["yaw"]
            raw_thrust = data["thrust"]
            emergency_stop = data["estop"]
            trim_roll = data["rollcal"]
            trim_pitch = data["pitchcal"]

            if self.emergencyStop != emergency_stop:
                self.emergencyStop = emergency_stop
                self.emergency_stop_updated.call(self.emergencyStop)

            # Thust limiting (slew, minimum and emergency stop)
            if raw_thrust < 0.05 or emergency_stop:
                thrust = 0
            else:
                thrust = self.minThrust + thrust * (self.maxThrust -
                                                    self.minThrust)
            if (self.thrustSlewEnabled == True and
                self.slewEnableLimit > thrust and not
                emergency_stop):
                if self.oldThrust > self.slewEnableLimit:
                    self.oldThrust = self.slewEnableLimit
                if thrust < (self.oldThrust - (self.thrustDownSlew / 100)):
                    thrust = self.oldThrust - self.thrustDownSlew / 100
                if raw_thrust < 0 or thrust < self.minThrust:
                    thrust = 0
            self.oldThrust = thrust

            # Yaw deadband
            # TODO: Add to input device config?
            if yaw < -0.2 or yaw > 0.2:
                if yaw < 0:
                    yaw = (yaw + 0.2) * self.maxYawRate * 1.25
                else:
                    yaw = (yaw - 0.2) * self.maxYawRate * 1.25
            else:
                self.yaw = 0

            if trim_roll != 0 or trim_pitch != 0:
                self._trim_roll += trim_roll
                self._trim_pitch += trim_pitch
                self.rp_trim_updated.call(self._trim_roll, self._trim_pitch)

            trimmed_roll = roll + self._trim_roll
            trimmed_pitch = pitch + self._trim_pitch
            self.input_updated.call(trimmed_roll, trimmed_pitch, yaw, thrust)
        except Exception:
            logger.warning("Exception while reading inputdevice: %s",
                           traceback.format_exc())
            self.device_error.call(
                                     "Error reading from input device\n\n%s" %
                                     traceback.format_exc())
            self.readTimer.stop()
