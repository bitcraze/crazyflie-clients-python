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
PySDL2 driver, but in the future native support will be provided for Linux and
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

import cfclient.utils.inputreaders as readers
import cfclient.utils.inputinterfaces as interfaces

logger = logging.getLogger(__name__)

from cfclient.utils.config import Config
from cfclient.utils.config_manager import ConfigManager

from cfclient.utils.periodictimer import PeriodicTimer
from cflib.utils.callbacks import Caller
import cfclient.utils.mux
from cfclient.utils.mux import InputMux
from cfclient.utils.mux.nomux import NoMux
from cfclient.utils.mux.selectivemux import SelectiveMux
from cfclient.utils.mux.takeovermux import TakeOverMux
from cfclient.utils.mux.mixmux import MixMux
from cfclient.utils.mux.takeoverselectivemux import TakeOverSelectiveMux

MAX_THRUST = 65000

class JoystickReader:
    """
    Thread that will read input from devices/joysticks and send control-set
    ponts to the Crazyflie
    """
    inputConfig = []

    def __init__(self, do_device_discovery=True):
        self._input_device = None

        self._min_thrust = 0
        self._max_thrust = 0
        self._thrust_slew_rate = 0
        self._thrust_slew_enabled = False
        self._thrust_slew_limit = 0
        self._has_pressure_sensor = False

        self._old_thrust = 0
        self._old_raw_thrust = 0
        self._old_alt_hold = False
        self._springy_throttle = True

        self._prev_values = {}

        self._trim_roll = Config().get("trim_roll")
        self._trim_pitch = Config().get("trim_pitch")

        self._input_map = None

        self._mux = [NoMux(self), SelectiveMux(self), TakeOverMux(self),
                     MixMux(self), TakeOverSelectiveMux(self)]
        # Set NoMux as default
        self._selected_mux = self._mux[0]

        if Config().get("flightmode") is "Normal":
            self.set_yaw_limit(Config().get("normal_max_yaw"))
            self.set_rp_limit(Config().get("normal_max_rp"))
            # Values are stored at %, so use the functions to set the values
            self.set_thrust_limits(
                Config().get("normal_min_thrust"),
                Config().get("normal_max_thrust"))
            self.set_thrust_slew_limiting(
                Config().get("normal_slew_rate"),
                Config().get("normal_slew_limit"))
        else:
            self.set_yaw_limit(Config().get("max_yaw"))
            self.set_rp_limit(Config().get("max_rp"))
            # Values are stored at %, so use the functions to set the values
            self.set_thrust_limits(
                Config().get("min_thrust"), Config().get("max_thrust"))
            self.set_thrust_slew_limiting(
                Config().get("slew_rate"), Config().get("slew_limit"))

        self._dev_blacklist = None
        if len(Config().get("input_device_blacklist")) > 0:
            self._dev_blacklist = re.compile(
                            Config().get("input_device_blacklist"))
        logger.info("Using device blacklist [{}]".format(
                            Config().get("input_device_blacklist")))


        self._available_devices = {}

        # TODO: The polling interval should be set from config file
        self._read_timer = PeriodicTimer(0.01, self.read_input)

        if do_device_discovery:
            self._discovery_timer = PeriodicTimer(1.0, 
                            self._do_device_discovery)
            self._discovery_timer.start()

        # Check if user config exists, otherwise copy files
        if not os.path.exists(ConfigManager().configs_dir):
            logger.info("No user config found, copying dist files")
            os.makedirs(ConfigManager().configs_dir)

        for f in glob.glob(sys.path[0] +
                           "/cfclient/configs/input/[A-Za-z]*.json"):
            dest = os.path.join(ConfigManager().
                                configs_dir, os.path.basename(f))
            if not os.path.isfile(dest):
                logger.debug("Copying %s", f)
                shutil.copy2(f, ConfigManager().configs_dir)

        ConfigManager().get_list_of_configs()

        self.input_updated = Caller()
        self.rp_trim_updated = Caller()
        self.emergency_stop_updated = Caller()
        self.device_discovery = Caller()
        self.device_error = Caller()
        self.althold_updated = Caller()
        self.alt1_updated = Caller()
        self.alt2_updated = Caller()

        # Call with 3 bools (rp_limiting, yaw_limiting, thrust_limiting)
        self.limiting_updated = Caller()

    def set_alt_hold_available(self, available):
        """Set if altitude hold is available or not (depending on HW)"""
        self._has_pressure_sensor = available

    def enable_alt_hold(self, althold):
        """Enable or disable altitude hold"""
        self._old_alt_hold = althold

    def _do_device_discovery(self):
        devs = self.available_devices()

        if len(devs):
            self.device_discovery.call(devs)
            self._discovery_timer.stop()

    def available_mux(self):
        available = []
        for m in self._mux:
            available.append(m.name)

        return available

    def set_mux(self, name=None, mux=None):
        if name:
            for m in self._mux:
                if m.name == name:
                    self._selected_mux = m
        elif mux:
            self._selected_mux = mux

        logger.info("Selected MUX: {}".format(self._selected_mux.name))

    def get_mux_supported_dev_count(self):
        return self._selected_mux.get_supported_dev_count()

    def available_devices(self):
        """List all available and approved input devices.
        This function will filter available devices by using the
        blacklist configuration and only return approved devices."""
        devs = readers.devices()
        devs += interfaces.devices()
        approved_devs = []

        for dev in devs:
            if ((not self._dev_blacklist) or 
                    (self._dev_blacklist and not
                     self._dev_blacklist.match(dev.name))):
                approved_devs.append(dev)

        return approved_devs 

    def enableRawReading(self, device_name):
        """
        Enable raw reading of the input device with id deviceId. This is used
        to get raw values for setting up of input devices. Values are read
        without using a mapping.
        """
        if self._input_device:
            self._input_device.close()
            self._input_device = None

        for d in readers.devices():
            if d.name == device_name:
                self._input_device = d

        # Set the mapping to None to get raw values
        self._input_device.input_map = None
        self._input_device.open()

    def get_saved_device_mapping(self, device_name):
        """Return the saved mapping for a given device"""
        config = None
        device_config_mapping = Config().get("device_config_mapping")
        if device_name in device_config_mapping.keys():
            config = device_config_mapping[device_name]

        logging.debug("For [{}] we recommend [{}]".format(device_name, config))
        return config

    def stop_raw_reading(self):
        """Disable raw reading of input device."""
        if self._input_device:
            self._input_device.close()
            self._input_device = None

    def read_raw_values(self):
        """ Read raw values from the input device."""
        [axes, buttons, mapped_values] = self._input_device.read(include_raw=True)
        dict_axes = {}
        dict_buttons = {}

        for i, a in enumerate(axes):
            dict_axes[i] = a

        for i, b in enumerate(buttons):
            dict_buttons[i] = b

        return [dict_axes, dict_buttons, mapped_values]

    def set_raw_input_map(self, input_map):
        """Set an input device map"""
        if self._input_device:
            self._input_device.input_map = input_map

    def set_input_map(self, device_name, input_map_name):
        """Load and set an input device map with the given name"""
        settings = ConfigManager().get_settings(input_map_name)
        if settings:
            self._springy_throttle = settings["springythrottle"]
            self._input_map = ConfigManager().get_config(input_map_name)
        if self._input_device:
            self._input_device.input_map = self._input_map
        Config().get("device_config_mapping")[device_name] = input_map_name

    def get_device_name(self):
        """Get the name of the current open device"""
        if self._input_device:
            return self._input_device.name
        return None

    def start_input(self, device_name, config_name=None):
        """
        Start reading input from the device with name device_name using config
        config_name. Returns True if device supports mapping, otherwise False
        """
        try:
            #device_id = self._available_devices[device_name]
            # Check if we supplied a new map, if not use the preferred one
            for d in readers.devices():
                if d.name == device_name:
                    self._input_device = d
                    if not config_name:
                        config_name = self.get_saved_device_mapping(device_name)
                    self.set_input_map(device_name, config_name)
                    self._input_device.open()
                    self._input_device.input_map = self._input_map
                    self._input_device.input_map_name = config_name
                    self._selected_mux.add_device(self._input_device, None)
                    # Update the UI with the limiting for this device
                    self.limiting_updated.call(self._input_device.limit_rp,
                                               self._input_device.limit_yaw,
                                               self._input_device.limit_thrust)
                    self._read_timer.start()
                    return self._input_device.supports_mapping
        except Exception:
            self.device_error.call(
                     "Error while opening/initializing  input device\n\n%s" %
                     (traceback.format_exc()))

        if not self._input_device:
            self.device_error.call(
                     "Could not find device {}".format(device_name))
        return False

    def stop_input(self, device_name = None):
        """Stop reading from the input device."""
        if device_name:
            for d in readers.devices():
                if d.name == device_name:
                    d.close()
        else:
            for d in readers.devices():
                d.close()
            #if self._input_device:
            #    self._input_device.close()
            #    self._input_device = None

    def set_yaw_limit(self, max_yaw_rate):
        """Set a new max yaw rate value."""
        for m in self._mux:
            m.max_yaw_rate = max_yaw_rate

    def set_rp_limit(self, max_rp_angle):
        """Set a new max roll/pitch value."""
        for m in self._mux:
            m.max_rp_angle = max_rp_angle

    def set_thrust_slew_limiting(self, thrust_slew_rate, thrust_slew_limit):
        """Set new values for limit where the slewrate control kicks in and
        for the slewrate."""
        for m in self._mux:
            m.thrust_slew_rate = JoystickReader.p2t(thrust_slew_rate)
            m.thrust_slew_limit = JoystickReader.p2t(thrust_slew_limit)
            if thrust_slew_rate > 0:
                m.thrust_slew_enabled = True
            else:
                m.thrust_slew_enabled = False

    def set_thrust_limits(self, min_thrust, max_thrust):
        """Set a new min/max thrust limit."""
        for m in self._mux:
            m.min_thrust = JoystickReader.p2t(min_thrust)
            m.max_thrust = JoystickReader.p2t(max_thrust)

    def set_trim_roll(self, trim_roll):
        """Set a new value for the roll trim."""
        for m in self._mux:
            m.trim_roll = trim_roll

    def set_trim_pitch(self, trim_pitch):
        """Set a new value for the trim trim."""
        for m in self._mux:
            m.trim_pitch = trim_pitch

    def _calc_rp_trim(self, key_neg, key_pos, data):
        if self._check_toggle(key_neg, data) and not data[key_neg]:
            return -1.0
        if self._check_toggle(key_pos, data) and not data[key_pos]:
            return 1.0
        return 0.0

    def _check_toggle(self, key, data):
        if not key in self._prev_values:
            self._prev_values[key] = data[key]
        elif self._prev_values[key] != data[key]:
            self._prev_values[key] = data[key]
            return True
        return False

    def read_input(self):
        """Read input data from the selected device"""
        try:
            [roll, pitch, yaw, thrust] = self._selected_mux.read()

            #if trim_roll != 0 or trim_pitch != 0:
            #    self._trim_roll += trim_roll
            #    self._trim_pitch += trim_pitch
            #    self.rp_trim_updated.call(self._trim_roll, self._trim_pitch)

            #trimmed_roll = roll + self._trim_roll
            #trimmed_pitch = pitch + self._trim_pitch

            # Thrust might be <0 here, make sure it's not otherwise we'll get an error.
            if thrust < 0:
                thrust = 0
            if thrust > 65535:
                thrust = 65535

            self.input_updated.call(roll, pitch, yaw, thrust)
        except Exception:
            logger.warning("Exception while reading inputdevice: %s",
                           traceback.format_exc())
            self.device_error.call("Error reading from input device\n\n%s" %
                                     traceback.format_exc())
            self.input_updated.call(0, 0, 0, 0)
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
