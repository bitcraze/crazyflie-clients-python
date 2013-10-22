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
import re
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

MAX_THRUST = 65000

class JoystickReader:
    """
    Thread that will read input from devices/joysticks and send control-set
    ponts to the Crazyflie
    """
    inputConfig = []

    def __init__(self, do_device_discovery=True):
        # TODO: Should be OS dependant
        self.inputdevice = PyGameReader()
        
        self._min_thrust = 0
        self._max_thrust = 0
        self._thrust_slew_rate = 0
        self._thrust_slew_enabled = False
        self._thrust_slew_limit = 0
        self._emergency_stop = False
        self._has_pressure_sensor = False

        self._old_thrust = 0
        self._old_alt_hold = False

        self._trim_roll = Config().get("trim_roll")
        self._trim_pitch = Config().get("trim_pitch")

        if (Config().get("flightmode") is "Normal"):
            self._max_yaw_rate = Config().get("normal_max_yaw")
            self._max_rp_angle = Config().get("normal_max_rp")
            # Values are stored at %, so use the functions to set the values
            self.set_thrust_limits(
                Config().get("normal_min_thrust"),
                Config().get("normal_max_thrust"))
            self.set_thrust_slew_limiting(
                Config().get("normal_slew_rate"),
                Config().get("normal_slew_limit"))
        else:
            self._max_yaw_rate = Config().get("max_yaw")
            self._max_rp_angle = Config().get("max_rp")
            # Values are stored at %, so use the functions to set the values
            self.set_thrust_limits(
                Config().get("min_thrust"), Config().get("max_thrust"))
            self.set_thrust_slew_limiting(
                Config().get("slew_rate"), Config().get("slew_limit"))

        self._dev_blacklist = None
        if (len(Config().get("input_device_blacklist")) > 0):
            self._dev_blacklist = re.compile(
                            Config().get("input_device_blacklist"))
        logger.info("Using device blacklist [{}]".format(
                            Config().get("input_device_blacklist")))


        # TODO: The polling interval should be set from config file
        self._read_timer = PeriodicTimer(0.01, self.read_input)

        if do_device_discovery:
            self._discovery_timer = PeriodicTimer(1.0, 
                            self._do_device_discovery)
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
        self.althold_updated = Caller()

    def setAltHoldAvailable(self, available):
        self._has_pressure_sensor = available

    def setAltHold(self, althold):
        self._old_alt_hold = althold

    def _do_device_discovery(self):
        devs = self.getAvailableDevices()

        if len(devs):
            self.device_discovery.call(devs)
            self._discovery_timer.stop()

    def getAvailableDevices(self):
        """List all available and approved input devices.
        This function will filter available devices by using the
        blacklist configuration and only return approved devices."""
        devs = self.inputdevice.getAvailableDevices()
        approved_devs = []

        for dev in devs:
            if ((not self._dev_blacklist) or 
                    (self._dev_blacklist and not
                     self._dev_blacklist.match(dev["name"]))):
                self._available_devices[dev["name"]] = dev["id"]
                approved_devs.append(dev)

        return approved_devs 

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
            self._read_timer.start()
        except Exception:
            self.device_error.call(
                     "Error while opening/initializing  input device\n\n%s" %
                     (traceback.format_exc()))

    def stop_input(self):
        """Stop reading from the input device."""
        self._read_timer.stop()

    def set_yaw_limit(self, max_yaw_rate):
        """Set a new max yaw rate value."""
        self._max_yaw_rate = max_yaw_rate

    def set_rp_limit(self, max_rp_angle):
        """Set a new max roll/pitch value."""
        self._max_rp_angle = max_rp_angle

    def set_thrust_slew_limiting(self, thrust_slew_rate, thrust_slew_limit):
        """Set new values for limit where the slewrate control kicks in and
        for the slewrate."""
        self._thrust_slew_rate = JoystickReader.p2t(thrust_slew_rate)
        self._thrust_slew_limit = JoystickReader.p2t(thrust_slew_limit)
        if (thrust_slew_rate > 0):
            self._thrust_slew_enabled = True
        else:
            self._thrust_slew_enabled = False

    def set_thrust_limits(self, min_thrust, max_thrust):
        """Set a new min/max thrust limit."""
        self._min_thrust = JoystickReader.p2t(min_thrust)
        self._max_thrust = JoystickReader.p2t(max_thrust)

    def set_trim_roll(self, trim_roll):
        """Set a new value for the roll trim."""
        self._trim_roll = trim_roll

    def set_trim_pitch(self, trim_pitch):
        """Set a new value for the trim trim."""
        self._trim_pitch = trim_pitch

    def read_input(self):
        """Read input data from the selected device"""
        try:
            data = self.inputdevice.read_input()
            roll = data["roll"] * self._max_rp_angle
            pitch = data["pitch"] * self._max_rp_angle
            thrust = data["thrust"]
            yaw = data["yaw"]
            raw_thrust = data["thrust"]
            emergency_stop = data["estop"]
            trim_roll = data["rollcal"]
            trim_pitch = data["pitchcal"]
            althold = data["althold"]

            if (self._old_alt_hold != althold):
                self.althold_updated.call(str(althold))
                self._old_alt_hold = althold

            if self._emergency_stop != emergency_stop:
                self._emergency_stop = emergency_stop
                self.emergency_stop_updated.call(self._emergency_stop)

            # Thust limiting (slew, minimum and emergency stop)
            if althold and self._has_pressure_sensor:
                thrust = int(round(JoystickReader.deadband(thrust,0.2)*32767 + 32767)) #Convert to uint16
            
            else:
                if raw_thrust < 0.05 or emergency_stop:
                    thrust = 0
                else:
                    thrust = self._min_thrust + thrust * (self._max_thrust -
                                                            self._min_thrust)
                if (self._thrust_slew_enabled == True and
                    self._thrust_slew_limit > thrust and not
                    emergency_stop):
                    if self._old_thrust > self._thrust_slew_limit:
                        self._old_thrust = self._thrust_slew_limit
                    if thrust < (self._old_thrust - (self._thrust_slew_rate / 100)):
                        thrust = self._old_thrust - self._thrust_slew_rate / 100
                    if raw_thrust < 0 or thrust < self._min_thrust:
                        thrust = 0

            self._old_thrust = thrust
            # Yaw deadband
            # TODO: Add to input device config?
            yaw = JoystickReader.deadband(yaw,0.2)*self._max_yaw_rate           

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
            self.device_error.call("Error reading from input device\n\n%s" %
                                     traceback.format_exc())
            self._read_timer.stop()

    @staticmethod
    def p2t(percentage):
        """Convert a percentage to raw thrust"""
        return int(MAX_THRUST * (percentage / 100.0))

    @staticmethod
    def deadband(value, threshold):
        if abs(value) < threshold:
            value = 0
        elif value > 0:
            value -= threshold
        elif value < 0:
            value += threshold
        return value/(1-threshold)
