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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Driver for reading data from the PySDL2 API. Used from Inpyt.py for reading input data.
"""

import sys
if sys.platform.startswith('linux'):
    raise Exception("No SDL2 support on Linux")

__author__ = 'Bitcraze AB'
__all__ = ['PySDL2Reader']

import sdl2
import sdl2.ext
import sdl2.hints
import time
import logging

logger = logging.getLogger(__name__)

MODULE_MAIN = "PySDL2Reader"
MODULE_NAME = "PySDL2"

class _JS():
    def __init__(self, num, name):
        self.axes = []
        self.buttons = []
        self.name = MODULE_NAME
        self._j = None
        self._btn_count = 0
        self._id = num
        self._name = name

    def open(self):
        self._j = sdl2.SDL_JoystickOpen(self._id)
        self._btn_count = sdl2.SDL_JoystickNumButtons(self._j)

        self.axes = list(0 for i in range(sdl2.SDL_JoystickNumAxes(self._j)))
        self.buttons = list(0 for i in range(sdl2.SDL_JoystickNumButtons(self._j)+4))

    def close(self):
        if self._j:
            sdl2.joystick.SDL_JoystickClose(self._j)
        self._j = None

    def _set_fake_hat_button(self, btn=None):
        self.buttons[self._btn_count] = 0
        self.buttons[self._btn_count+1] = 0
        self.buttons[self._btn_count+2] = 0
        self.buttons[self._btn_count+3] = 0

        if btn:
            self.buttons[self._btn_count+btn] = 1

    def read(self):
        for e in sdl2.ext.get_events():
            if e.type == sdl2.SDL_JOYAXISMOTION:
                self.axes[e.jaxis.axis] = e.jaxis.value / 32767.0

            if e.type == sdl2.SDL_JOYBUTTONDOWN:
                self.buttons[e.jbutton.button] = 1

            if e.type == sdl2.SDL_JOYBUTTONUP:
                self.buttons[e.jbutton.button] = 0

            if e.type == sdl2.SDL_JOYHATMOTION:
                if e.jhat.value == sdl2.SDL_HAT_CENTERED:
                    self._set_fake_hat_button()
                elif e.jhat.value == sdl2.SDL_HAT_UP:
                    self._set_fake_hat_button(0)
                elif e.jhat.value == sdl2.SDL_HAT_DOWN:
                    self._set_fake_hat_button(1)
                elif e.jhat.value == sdl2.SDL_HAT_LEFT:
                    self._set_fake_hat_button(2)
                elif e.jhat.value == sdl2.SDL_HAT_RIGHT:
                    self._set_fake_hat_button(3)
        return [self.axes, self.buttons]

class PySDL2Reader():
    """Used for reading data from input devices using the PySDL2 API."""
    def __init__(self):
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_JOYSTICK)
        sdl2.SDL_SetHint(sdl2.hints.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1")
        sdl2.ext.init()
        self._js = {}
        self.name = MODULE_NAME

    def open(self, device_id):
        """Initalize the reading and open the device with deviceId and set the mapping for axis/buttons using the
        inputMap"""
        self._js[device_id].open()

    def close(self, device_id):
        self._js[device_id].close()

    def read(self, device_id):
        """Read input from the selected device."""
        return self._js[device_id].read()

    def devices(self):
        """List all the available devices."""
        logger.info("Looking for devices")
        dev = []
        names = []

        nbrOfInputs = sdl2.joystick.SDL_NumJoysticks()
        for i in range(0, nbrOfInputs):
            j = sdl2.joystick.SDL_JoystickOpen(i)
            name = sdl2.joystick.SDL_JoystickName(j)
            if names.count(name) > 0:
                name = "{0} #{1}".format(name, names.count(name) + 1)
            dev.append({"id": i, "name": name})
            self._js[i] = _JS(i, name)
            names.append(name)
            sdl2.joystick.SDL_JoystickClose(j)
        return dev
