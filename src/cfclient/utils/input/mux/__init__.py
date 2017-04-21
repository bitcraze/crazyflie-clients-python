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
The mux is used to open one or more devices and mix the inputs from all
of them into one "input" for the Crazyflie and UI.
"""
import logging

__author__ = 'Bitcraze AB'
__all__ = ['InputMux']

logger = logging.getLogger(__name__)


class InputMux(object):

    def __init__(self, input_layer):
        self._devs = {"Device": None}
        self.name = "N/A"
        self.input = input_layer

    def _open_new_device(self, dev, role):
        # Silently close device if open as other role
        for r in self._devs:
            if self._devs[r]:
                if self._devs[r] == dev:
                    self._devs[r] = None
                    dev.close()

        # First set role to None to stop reading
        old_dev = self._devs[role]
        self._devs[role] = None
        if old_dev:
            old_dev.close()

        # Open the new device before attaching it to a role
        dev.open()
        self._devs[role] = dev

    def supported_roles(self):
        return list(self._devs.keys())

    def add_device(self, dev, role):
        logger.info("Adding device {} to MUX {}".format(dev.name, self.name))
        self._open_new_device(dev, role)

    def pause(self):
        for d in [key for key in list(self._devs.keys()) if self._devs[key]]:
            self._devs[d].close()

    def devices(self):
        devs = ()
        for d in self._devs:
            if self._devs[d]:
                devs += (self._devs[d], )
        return devs

    def resume(self):
        for d in [key for key in list(self._devs.keys()) if self._devs[key]]:
            self._devs[d].open()

    def close(self):
        """Close down the MUX and close all it's devices"""
        for d in [key for key in list(self._devs.keys()) if self._devs[key]]:
            self._devs[d].close()
            self._devs[d] = None

    def read(self):
        return None
