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
import os
import re
import glob
import traceback
import logging
import shutil

from . import inputreaders as readers
from . import inputinterfaces as interfaces

import cfclient
from cfclient.utils.config import Config
from cfclient.utils.config_manager import ConfigManager

from cfclient.utils.periodictimer import PeriodicTimer
from cflib.utils.callbacks import Caller
from .mux.nomux import NoMux
from .mux.takeovermux import TakeOverMux
from .mux.takeoverselectivemux import TakeOverSelectiveMux

__author__ = 'Bitcraze AB'
__all__ = ['JoystickReader']

logger = logging.getLogger(__name__)

MAX_THRUST = 65000
INITAL_TAGET_HEIGHT = 0.4
MAX_TARGET_HEIGHT = 1.0
MIN_TARGET_HEIGHT = 0.03
MIN_HOVER_HEIGHT = 0.20
INPUT_READ_PERIOD = 0.01


class JoystickReader(object):
    """
    Thread that will read input from devices/joysticks and send control-set
    points to the Crazyflie
    """
    inputConfig = []

    ASSISTED_CONTROL_ALTHOLD = 0
    ASSISTED_CONTROL_POSHOLD = 1
    ASSISTED_CONTROL_HEIGHTHOLD = 2
    ASSISTED_CONTROL_HOVER = 3

    def __init__(self, do_device_discovery=True):
        self._input_device = None

        self._mux = [NoMux(self), TakeOverSelectiveMux(self),
                     TakeOverMux(self)]
        # Set NoMux as default
        self._selected_mux = self._mux[0]

        self.min_thrust = 0
        self.max_thrust = 0
        self._thrust_slew_rate = 0
        self.thrust_slew_enabled = False
        self.thrust_slew_limit = 0
        self.has_pressure_sensor = False
        self._hover_max_height = MAX_TARGET_HEIGHT

        self.max_rp_angle = 0
        self.max_yaw_rate = 0
        try:
            self.set_assisted_control(Config().get("assistedControl"))
        except KeyError:
            self.set_assisted_control(JoystickReader.ASSISTED_CONTROL_ALTHOLD)

        self._old_thrust = 0
        self._old_raw_thrust = 0
        self.springy_throttle = True
        self._target_height = INITAL_TAGET_HEIGHT

        self.trim_roll = Config().get("trim_roll")
        self.trim_pitch = Config().get("trim_pitch")
        self._rp_dead_band = 0.1

        self._input_map = None

        if Config().get("flightmode") == "Normal":
            self.max_yaw_rate = Config().get("normal_max_yaw")
            self.max_rp_angle = Config().get("normal_max_rp")
            # Values are stored at %, so use the functions to set the values
            self.min_thrust = Config().get("normal_min_thrust")
            self.max_thrust = Config().get("normal_max_thrust")
            self.thrust_slew_limit = Config().get("normal_slew_limit")
            self.thrust_slew_rate = Config().get("normal_slew_rate")
        else:
            self.max_yaw_rate = Config().get("max_yaw")
            self.max_rp_angle = Config().get("max_rp")
            # Values are stored at %, so use the functions to set the values
            self.min_thrust = Config().get("min_thrust")
            self.max_thrust = Config().get("max_thrust")
            self.thrust_slew_limit = Config().get("slew_limit")
            self.thrust_slew_rate = Config().get("slew_rate")

        self._dev_blacklist = None
        if len(Config().get("input_device_blacklist")) > 0:
            self._dev_blacklist = re.compile(
                Config().get("input_device_blacklist"))
        logger.info("Using device blacklist [{}]".format(
            Config().get("input_device_blacklist")))

        self._available_devices = {}

        # TODO: The polling interval should be set from config file
        self._read_timer = PeriodicTimer(INPUT_READ_PERIOD, self.read_input)

        if do_device_discovery:
            self._discovery_timer = PeriodicTimer(1.0,
                                                  self._do_device_discovery)
            self._discovery_timer.start()

        # Check if user config exists, otherwise copy files
        if not os.path.exists(ConfigManager().configs_dir):
            logger.info("No user config found, copying dist files")
            os.makedirs(ConfigManager().configs_dir)

        for f in glob.glob(
                cfclient.module_path + "/configs/input/[A-Za-z]*.json"):
            dest = os.path.join(ConfigManager().
                                configs_dir, os.path.basename(f))
            if not os.path.isfile(dest):
                logger.debug("Copying %s", f)
                shutil.copy2(f, ConfigManager().configs_dir)

        ConfigManager().get_list_of_configs()

        self.input_updated = Caller()
        self.assisted_input_updated = Caller()
        self.heighthold_input_updated = Caller()
        self.hover_input_updated = Caller()
        self.rp_trim_updated = Caller()
        self.emergency_stop_updated = Caller()
        self.device_discovery = Caller()
        self.device_error = Caller()
        self.assisted_control_updated = Caller()
        self.alt1_updated = Caller()
        self.alt2_updated = Caller()

        # Call with 3 bools (rp_limiting, yaw_limiting, thrust_limiting)
        self.limiting_updated = Caller()

    def _get_device_from_name(self, device_name):
        """Get the raw device from a name"""
        for d in readers.devices():
            if d.name == device_name:
                return d
        return None

    def set_hover_max_height(self, height):
        self._hover_max_height = height

    def set_alt_hold_available(self, available):
        """Set if altitude hold is available or not (depending on HW)"""
        self.has_pressure_sensor = available

    def _do_device_discovery(self):
        devs = self.available_devices()

        # This is done so that devs can easily get access
        # to limits without creating lots of extra code
        for d in devs:
            d.input = self

        if len(devs):
            self.device_discovery.call(devs)
            self._discovery_timer.stop()

    def available_mux(self):
        return self._mux

    def set_mux(self, name=None, mux=None):
        old_mux = self._selected_mux
        if name:
            for m in self._mux:
                if m.name == name:
                    self._selected_mux = m
        elif mux:
            self._selected_mux = mux

        old_mux.close()

        logger.info("Selected MUX: {}".format(self._selected_mux.name))

    def set_assisted_control(self, mode):
        self._assisted_control = mode

    def get_assisted_control(self):
        return self._assisted_control

    def available_devices(self):
        """List all available and approved input devices.
        This function will filter available devices by using the
        blacklist configuration and only return approved devices."""
        devs = readers.devices()
        devs += interfaces.devices()
        approved_devs = []

        for dev in devs:
            if ((not self._dev_blacklist) or
                    (self._dev_blacklist and
                     not self._dev_blacklist.match(dev.name))):
                dev.input = self
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
        if device_name in list(device_config_mapping.keys()):
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
        [axes, buttons, mapped_values] = self._input_device.read(
            include_raw=True)
        dict_axes = {}
        dict_buttons = {}

        for i, a in enumerate(axes):
            dict_axes[i] = a

        for i, b in enumerate(buttons):
            dict_buttons[i] = b

        return [dict_axes, dict_buttons, mapped_values]

    def set_raw_input_map(self, input_map):
        """Set an input device map"""
        # TODO: Will not work!
        if self._input_device:
            self._input_device.input_map = input_map

    def set_input_map(self, device_name, input_map_name):
        """Load and set an input device map with the given name"""
        dev = self._get_device_from_name(device_name)
        settings = ConfigManager().get_settings(input_map_name)

        if settings:
            self.springy_throttle = settings["springythrottle"]
            self._rp_dead_band = settings["rp_dead_band"]
            self._input_map = ConfigManager().get_config(input_map_name)
        dev.input_map = self._input_map
        dev.input_map_name = input_map_name
        Config().get("device_config_mapping")[device_name] = input_map_name
        dev.set_dead_band(self._rp_dead_band)

    def start_input(self, device_name, role="Device", config_name=None):
        """
        Start reading input from the device with name device_name using config
        config_name. Returns True if device supports mapping, otherwise False
        """
        try:
            # device_id = self._available_devices[device_name]
            # Check if we supplied a new map, if not use the preferred one
            device = self._get_device_from_name(device_name)
            self._selected_mux.add_device(device, role)
            # Update the UI with the limiting for this device
            self.limiting_updated.call(device.limit_rp,
                                       device.limit_yaw,
                                       device.limit_thrust)
            self._read_timer.start()
            return device.supports_mapping
        except Exception:
            self.device_error.call(
                "Error while opening/initializing  input device\n\n%s" %
                (traceback.format_exc()))

        if not self._input_device:
            self.device_error.call(
                "Could not find device {}".format(device_name))
        return False

    def resume_input(self):
        self._selected_mux.resume()
        self._read_timer.start()

    def pause_input(self, device_name=None):
        """Stop reading from the input device."""
        self._read_timer.stop()
        self._selected_mux.pause()

    def _set_thrust_slew_rate(self, rate):
        self._thrust_slew_rate = rate
        if rate > 0:
            self.thrust_slew_enabled = True
        else:
            self.thrust_slew_enabled = False

    def _get_thrust_slew_rate(self):
        return self._thrust_slew_rate

    def read_input(self):
        """Read input data from the selected device"""
        try:
            data = self._selected_mux.read()

            if data:
                if data.toggled.assistedControl:
                    if self._assisted_control == \
                            JoystickReader.ASSISTED_CONTROL_POSHOLD or \
                            self._assisted_control == \
                            JoystickReader.ASSISTED_CONTROL_HOVER:
                        if data.assistedControl and self._assisted_control != \
                                JoystickReader.ASSISTED_CONTROL_HOVER:
                            for d in self._selected_mux.devices():
                                d.limit_thrust = False
                                d.limit_rp = False
                        elif data.assistedControl:
                            for d in self._selected_mux.devices():
                                d.limit_thrust = True
                                d.limit_rp = False
                        else:
                            for d in self._selected_mux.devices():
                                d.limit_thrust = True
                                d.limit_rp = True
                    if self._assisted_control == \
                            JoystickReader.ASSISTED_CONTROL_ALTHOLD:
                        self.assisted_control_updated.call(
                                            data.assistedControl)
                    if ((self._assisted_control ==
                            JoystickReader.ASSISTED_CONTROL_HEIGHTHOLD) or
                            (self._assisted_control ==
                             JoystickReader.ASSISTED_CONTROL_HOVER)):
                        try:
                            self.assisted_control_updated.call(
                                                data.assistedControl)
                            if not data.assistedControl:
                                # Reset height controller state to initial
                                # target height both in the UI and in the
                                # Crazyflie.
                                # TODO: Implement a proper state update of the
                                #       input layer
                                self.heighthold_input_updated.\
                                    call(0, 0,
                                         0, INITAL_TAGET_HEIGHT)
                                self.hover_input_updated.\
                                    call(0, 0,
                                         0, INITAL_TAGET_HEIGHT)
                        except Exception as e:
                            logger.warning(
                                "Exception while doing callback from "
                                "input-device for assited "
                                "control: {}".format(e))

                if data.toggled.estop:
                    try:
                        self.emergency_stop_updated.call(data.estop)
                    except Exception as e:
                        logger.warning("Exception while doing callback from"
                                       "input-device for estop: {}".format(e))

                if data.toggled.alt1:
                    try:
                        self.alt1_updated.call(data.alt1)
                    except Exception as e:
                        logger.warning("Exception while doing callback from"
                                       "input-device for alt1: {}".format(e))
                if data.toggled.alt2:
                    try:
                        self.alt2_updated.call(data.alt2)
                    except Exception as e:
                        logger.warning("Exception while doing callback from"
                                       "input-device for alt2: {}".format(e))

                # Reset height target when height-hold is not selected
                if not data.assistedControl or \
                        (self._assisted_control !=
                         JoystickReader.ASSISTED_CONTROL_HEIGHTHOLD and
                         self._assisted_control !=
                         JoystickReader.ASSISTED_CONTROL_HOVER):
                    self._target_height = INITAL_TAGET_HEIGHT

                if self._assisted_control == \
                        JoystickReader.ASSISTED_CONTROL_POSHOLD \
                        and data.assistedControl:
                    vx = data.roll
                    vy = data.pitch
                    vz = data.thrust
                    yawrate = data.yaw
                    # The odd use of vx and vy is to map forward on the
                    # physical joystick to positiv X-axis
                    self.assisted_input_updated.call(vy, -vx, vz, yawrate)
                elif self._assisted_control == \
                        JoystickReader.ASSISTED_CONTROL_HOVER \
                        and data.assistedControl:
                    vx = data.roll
                    vy = data.pitch

                    # Scale thrust to a value between -1.0 to 1.0
                    vz = (data.thrust - 32767) / 32767.0
                    # Integrate velosity setpoint
                    self._target_height += vz * INPUT_READ_PERIOD
                    # Cap target height
                    if self._target_height > self._hover_max_height:
                        self._target_height = self._hover_max_height
                    if self._target_height < MIN_HOVER_HEIGHT:
                        self._target_height = MIN_HOVER_HEIGHT

                    yawrate = data.yaw
                    # The odd use of vx and vy is to map forward on the
                    # physical joystick to positiv X-axis
                    self.hover_input_updated.call(vy, -vx, yawrate,
                                                  self._target_height)
                else:
                    # Update the user roll/pitch trim from device
                    if data.toggled.pitchNeg and data.pitchNeg:
                        self.trim_pitch -= .2
                    if data.toggled.pitchPos and data.pitchPos:
                        self.trim_pitch += .2
                    if data.toggled.rollNeg and data.rollNeg:
                        self.trim_roll -= .2
                    if data.toggled.rollPos and data.rollPos:
                        self.trim_roll += .2

                    if data.toggled.pitchNeg or data.toggled.pitchPos or \
                            data.toggled.rollNeg or data.toggled.rollPos:
                        self.rp_trim_updated.call(self.trim_roll,
                                                  self.trim_pitch)

                    if self._assisted_control == \
                            JoystickReader.ASSISTED_CONTROL_HEIGHTHOLD \
                            and data.assistedControl:
                        roll = data.roll + self.trim_roll
                        pitch = data.pitch + self.trim_pitch
                        yawrate = data.yaw
                        # Scale thrust to a value between -1.0 to 1.0
                        vz = (data.thrust - 32767) / 32767.0
                        # Integrate velosity setpoint
                        self._target_height += vz * INPUT_READ_PERIOD
                        # Cap target height
                        if self._target_height > self._hover_max_height:
                            self._target_height = self._hover_max_height
                        if self._target_height < MIN_TARGET_HEIGHT:
                            self._target_height = MIN_TARGET_HEIGHT
                        self.heighthold_input_updated.call(roll, -pitch,
                                                           yawrate,
                                                           self._target_height)
                    else:
                        # Using alt hold the data is not in a percentage
                        if not data.assistedControl:
                            data.thrust = JoystickReader.p2t(data.thrust)

                        # Thrust might be <0 here, make sure it's not otherwise
                        # we'll get an error.
                        if data.thrust < 0:
                            data.thrust = 0
                        if data.thrust > 0xFFFF:
                            data.thrust = 0xFFFF

                        self.input_updated.call(data.roll + self.trim_roll,
                                                data.pitch + self.trim_pitch,
                                                data.yaw, data.thrust)
            else:
                self.input_updated.call(0, 0, 0, 0)
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

    thrust_slew_rate = property(_get_thrust_slew_rate, _set_thrust_slew_rate)
