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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.
"""

"""

__author__ = 'Bitcraze AB'
__all__ = ['InputMux']


import os
import glob
import logging

from cflib.utils.callbacks import Caller

logger = logging.getLogger(__name__)

MAX_THRUST = 65000

class InputMux(object):
    def __init__(self, input):
        self._devs = []
        self.name = "N/A"
        self.input = input

        self._prev_values = {}

        # Roll/pitch limitation
        self.max_rp_angle = 0

        # Thrust limitations
        self.thrust_slew_enabled = True
        self.thrust_slew_limit = 0
        self.thrust_slew_rate = 0
        self.max_thrust = 0
        self.max_yaw_rate = 0
        self.springy_throttle = True

        self.trim_roll = 0
        self.trim_pitch = 0

        self.has_pressure_sensor = False

        # TODO: Fix writing these values
        #self._max_rp_angle = 40
        #self._springy_throttle = True
        #self._thrust_slew_enabled = True
        #self._thrust_slew_limit = 30
        #self._thrust_slew_rate = 30
        #self._min_thrust = 20000
        #self._max_thrust = 50000
        #self._max_yaw_rate = 400

        #self._trim_roll = 0.0
        #self._trim_pitch = 0.0

        # Stateful things
        self._old_thrust = 0
        self._old_raw_thrust = 0
        self._old_alt_hold = False

        # TODO: Should these really be placed here?
        #self.input_updated = Caller()
        #self.rp_trim_updated = Caller()
        #self.emergency_stop_updated = Caller()
        #self.device_discovery = Caller()
        #self.device_error = Caller()
        #self.althold_updated = Caller()
        #self.alt1_updated = Caller()
        #self.alt2_updated = Caller()

    def get_supported_dev_count(self):
        return 1

    def add_device(self, dev, parameters):
        logger.info("Adding device and opening it")
        dev.open()
        self._devs.append(dev)

    def remove_device(self, dev):
        self._devs.remove(dev)
        dev.close()

    def close(self):
        """Close down the MUX and close all it's devices"""
        for d in self._devs:
            d.close()
        self._devs = []

    def _cap_rp(self, rp):
        ret = rp * self.max_rp_angle
        if ret > self.max_rp_angle:
            ret = self.max_rp_angle
        elif ret < -1 * self.max_rp_angle:
            ret = -1 * self.max_rp_angle

        return ret

    def _scale_rp(self, roll, pitch):
        return [self._cap_rp(roll), self._cap_rp(pitch)]

    def _scale_and_deadband_yaw(self, yaw):
        return InputMux.deadband(yaw, 0.2) * self.max_yaw_rate

    def _limit_thrust(self, thrust, althold, emergency_stop):
        # Thust limiting (slew, minimum and emergency stop)
        if self.springy_throttle:
            if althold and self.has_pressure_sensor:
                thrust = int(round(InputMux.deadband(thrust, 0.2)*32767 + 32767)) #Convert to uint16
            else:
                if thrust < 0.05 or emergency_stop:
                    thrust = 0
                else:
                    thrust = self.min_thrust + thrust * (self.max_thrust -
                                                            self.min_thrust)
                if (self.thrust_slew_enabled == True and
                    self.thrust_slew_limit > thrust and not
                    emergency_stop):
                    if self._old_thrust > self.thrust_slew_limit:
                        self._old_thrust = self.thrust_slew_limit
                    if thrust < (self._old_thrust - (self.thrust_slew_rate / 100)):
                        thrust = self._old_thrust - self.thrust_slew_rate / 100
                    if thrust < 0 or thrust < self.min_thrust:
                        thrust = 0
        else:
            thrust = thrust / 2 + 0.5
            if althold and self.has_pressure_sensor:
                #thrust = int(round(JoystickReader.deadband(thrust,0.2)*32767 + 32767)) #Convert to uint16
                thrust = 32767
            else:
                if thrust < -0.90 or emergency_stop:
                    thrust = 0
                else:
                    thrust = self.min_thrust + thrust * (self.max_thrust -
                                                            self.min_thrust)
                if (self.thrust_slew_enabled == True and
                    self.thrust_slew_limit > thrust and not
                    emergency_stop):
                    if self._old_thrust > self.thrust_slew_limit:
                        self._old_thrust = self.thrust_slew_limit
                    if thrust < (self._old_thrust - (self.thrust_slew_rate / 100)):
                        thrust = self._old_thrust - self.thrust_slew_rate / 100
                    if thrust < -1 or thrust < self.min_thrust:
                        thrust = 0

        self._old_thrust = thrust
        self._old_raw_thrust = thrust
        return thrust

    def set_alt_hold_available(self, available):
        """Set if altitude hold is available or not (depending on HW)"""
        self.input._has_pressure_sensor = available

    def enable_alt_hold(self, althold):
        """Enable or disable altitude hold"""
        self._old_alt_hold = althold

    def _check_toggle(self, key, data):
        if not key in self._prev_values:
            self._prev_values[key] = data
        elif self._prev_values[key] != data:
            self._prev_values[key] = data
            return True
        return False

    def _update_alt_hold(self, value):
        if self._check_toggle("althold", value):
            self.input.althold_updated.call(str(value))

    def _update_em_stop(self, value):
        if self._check_toggle("estop", value):
            self.input.emergency_stop_updated.call(value)

    def _update_alt1(self, value):
        if self._check_toggle("alt1", value):
            self.input.alt1_updated.call(value)

    def _update_alt2(self, value):
        if self._check_toggle("alt2", value):
            self.input.alt2_updated.call(value)

    def _trim_rp(self, roll, pitch):
        return [roll + self.trim_roll, pitch + self.trim_pitch]

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

    def read(self):
        return None