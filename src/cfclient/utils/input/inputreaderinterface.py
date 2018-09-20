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

from time import time
import logging

logger = logging.getLogger(__name__)


class _ToggleState(dict):

    def __getattr__(self, attr):
        return self.get(attr)

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


class InputData:

    def __init__(self):
        # self._toggled = {}
        self._axes = ("roll", "pitch", "yaw", "thrust")
        self._buttons = ("alt1", "alt2", "estop", "exit", "pitchNeg",
                         "pitchPos", "rollNeg", "rollPos", "assistedControl",
                         "muxswitch")
        for axis in self._axes:
            self.__dict__[axis] = 0.0
        self.toggled = _ToggleState()
        self._prev_btn_values = {}
        for button in self._buttons:
            self.__dict__[button] = False
            self.toggled[button] = False
            self._prev_btn_values[button] = False

    def get_all_indicators(self):
        return self._axes + self._buttons

    def _check_toggle(self, key, data):
        if key not in self._prev_btn_values:
            self._prev_btn_values[key] = data
        elif self._prev_btn_values[key] != data:
            self._prev_btn_values[key] = data
            return True
        return False

    def reset_axes(self):
        for axis in self._axes:
            self.__dict__[axis] = 0.0

    def reset_buttons(self):
        for button in self._buttons:
            self.__dict__[button] = False

    def set(self, name, value):
        try:
            if name in self._buttons:
                if self._check_toggle(name, value):
                    self.toggled[name] = True
                else:
                    self.toggled[name] = False
        except KeyError:
            pass
        self.__dict__[name] = value

    def get(self, name):
        return self.__dict__[name]


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

        self.input = None

        self._reader = dev_reader
        self.id = dev_id
        self.name = dev_name
        self.input_map = None
        self.input_map_name = ""
        self.data = None
        self._prev_pressed = None
        self.reader_name = dev_reader.name

        self.data = InputData()

        # Stateful things
        self._old_thrust = 0
        self._old_raw_thrust = 0

        self._prev_thrust = 0
        self._last_time = 0
        # How low you have to pull the thrust to bypass the slew-rate (0-100%)
        self.thrust_stop_limit = -90

    def open(self):
        """Initialize the reading and open the device with deviceId and set the
        mapping for axis/buttons using the inputMap"""
        return

    def read(self):
        """Read input from the selected device."""
        return None

    def close(self):
        return

    @staticmethod
    def devices():
        """List all the available devices."""
        return []

    def _cap_rp(self, rp):
        ret = rp * self.input.max_rp_angle
        if ret > self.input.max_rp_angle:
            ret = self.input.max_rp_angle
        elif ret < -1 * self.input.max_rp_angle:
            ret = -1 * self.input.max_rp_angle

        return ret

    def _scale_rp(self, roll, pitch):
        return [self._cap_rp(roll), self._cap_rp(pitch)]

    def _scale_and_deadband_yaw(self, yaw):
        return (InputReaderInterface.deadband(yaw, 0.2) *
                self.input.max_yaw_rate)

    def _limit_thrust(self, thrust, assisted_control, emergency_stop):
        # Thrust limiting (slew, minimum and emergency stop)

        current_time = time()
        if self.input.springy_throttle:
            if assisted_control and \
                    (self.input.get_assisted_control() ==
                     self.input.ASSISTED_CONTROL_ALTHOLD or
                     self.input.get_assisted_control() ==
                     self.input.ASSISTED_CONTROL_HEIGHTHOLD or
                     self.input.get_assisted_control() ==
                     self.input.ASSISTED_CONTROL_HOVER):
                thrust = int(round(InputReaderInterface.deadband(thrust, 0.2) *
                                   32767 + 32767))  # Convert to uint16

                # do not drop thrust to 0 after switching hover mode off
                # set previous values for slew limit logic
                self._prev_thrust = self.input.thrust_slew_limit
                self._last_time = current_time

            else:
                # Scale the thrust to percent (it's between 0 and 1)
                thrust *= 100

                # The default action is to just use the thrust...
                limited_thrust = thrust
                if limited_thrust > self.input.max_thrust:
                    limited_thrust = self.input.max_thrust

                # ... but if we are lowering the thrust, check the limit
                if self._prev_thrust > thrust >= self.thrust_stop_limit and \
                        not emergency_stop:
                    # If we are above the limit, then don't use the slew...
                    if thrust > self.input.thrust_slew_limit:
                        limited_thrust = thrust
                    else:
                        # ... but if we are below first check if we "entered"
                        # the limit, then set it to the limit
                        if self._prev_thrust > self.input.thrust_slew_limit:
                            limited_thrust = self.input.thrust_slew_limit
                        else:
                            # If we are "inside" the limit, then lower
                            # according to the rate we have set each iteration
                            lowering = ((current_time - self._last_time) *
                                        self.input.thrust_slew_rate)
                            limited_thrust = self._prev_thrust - lowering
                elif emergency_stop or thrust < self.thrust_stop_limit:
                    # If the thrust have been pulled down or the
                    # emergency stop has been activated then bypass
                    # the slew and force 0
                    self._prev_thrust = 0
                    limited_thrust = 0

                # For the next iteration set the previous thrust to the limited
                # one (will be the slewed thrust if we are slewing)
                self._prev_thrust = limited_thrust

                # Lastly make sure we're following the "minimum" thrust setting
                if limited_thrust < self.input.min_thrust:
                    self._prev_thrust = 0
                    limited_thrust = 0

                self._last_time = current_time

                thrust = limited_thrust
        else:
            thrust = thrust / 2 + 0.5
            if assisted_control and self.input.get_assisted_control() == \
                    self.input.ASSISTED_CONTROL_ALTHOLD:
                thrust = 32767
            else:
                if thrust < -0.90 or emergency_stop:
                    thrust = 0
                else:
                    thrust = self.input.min_thrust + thrust * (
                        self.input.max_thrust -
                        self.input.min_thrust)
                if (self.input.thrust_slew_enabled and
                    self.input.thrust_slew_limit > thrust and not
                        emergency_stop):
                    if self._old_thrust > self.input.thrust_slew_limit:
                        self._old_thrust = self.input.thrust_slew_limit
                    if thrust < (self._old_thrust -
                                 self.input.thrust_slew_rate / 100):
                        thrust = (self._old_thrust -
                                  self.input.thrust_slew_rate / 100)
                    if thrust < -1 or thrust < self.input.min_thrust:
                        thrust = 0

        self._old_thrust = thrust
        self._old_raw_thrust = thrust
        return thrust

    @staticmethod
    def deadband(value, threshold):
        if abs(value) < threshold:
            value = 0
        elif value > 0:
            value -= threshold
        elif value < 0:
            value += threshold
        return value / (1 - threshold)
