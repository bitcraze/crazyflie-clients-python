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

__author__ = 'Bitcraze AB'
__all__ = ['PySDL2Reader']
import sdl2
import sdl2.ext
import sdl2.hints
import time
import logging
import sys

logger = logging.getLogger(__name__)

class PySDL2Reader():
    """Used for reading data from input devices using the PySDL2 API."""
    def __init__(self):
        self.inputMap = None
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_JOYSTICK)
        sdl2.SDL_SetHint(sdl2.hints.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1")
        sdl2.ext.init()

    def start_input(self, deviceId, inputMap):
        """Initalize the reading and open the device with deviceId and set the mapping for axis/buttons using the
        inputMap"""
        self.data = {"roll":0.0, "pitch":0.0, "yaw":0.0, "thrust":-1.0, "pitchcal":0.0, "rollcal":0.0, "estop": False, "exit":False, "althold":False}
        self.inputMap = inputMap
        self.j = sdl2.SDL_JoystickOpen(deviceId)

    def read_input(self):
        """Read input from the selected device."""
        # We only want the pitch/roll cal to be "oneshot", don't
        # save this value.
        self.data["pitchcal"] = 0.0
        self.data["rollcal"]  = 0.0

        for e in sdl2.ext.get_events():
          if e.type == sdl2.SDL_JOYAXISMOTION:
            index = "Input.AXIS-%d" % e.jaxis.axis
            try:
                if (self.inputMap[index]["type"] == "Input.AXIS"):
                    key = self.inputMap[index]["key"]
                    axisvalue = e.jaxis.value / 32767.0
                    # Offset the value first
                    axisvalue = axisvalue + self.inputMap[index]["offset"]
                    # All axis are in the range [-a,+a]
                    axisvalue = axisvalue * self.inputMap[index]["scale"]
                    # The value is now in the correct direction and in the range [-1,1]
                    self.data[key] = axisvalue
            except Exception:
                # Axis not mapped, ignore..
                pass          

          if e.type == sdl2.SDL_JOYBUTTONDOWN:
            index = "Input.BUTTON-%d" % e.jbutton.button            
            try:
                if (self.inputMap[index]["type"] == "Input.BUTTON"):
                    key = self.inputMap[index]["key"]
                    if (key == "estop"):
                        self.data["estop"] = not self.data["estop"]
                    elif (key == "exit"):
                        self.data["exit"] = True
                    elif (key == "althold"):
                        self.data["althold"] = not self.data["althold"]                        
                    else: # Generic cal for pitch/roll
                        self.data[key] = self.inputMap[index]["scale"]
            except Exception:
                # Button not mapped, ignore..
                pass
          
          if e.type == sdl2.SDL_JOYBUTTONUP:
            index = "Input.BUTTON-%d" % e.jbutton.button
            try:
                if (self.inputMap[index]["type"] == "Input.BUTTON"):
                    key = self.inputMap[index]["key"]
                    if (key == "althold"):
                        self.data["althold"] = False                     
            except Exception:
                # Button not mapped, ignore..
                pass            

          if e.type == sdl2.SDL_JOYHATMOTION:
            index = "Input.HAT-%d" % e.jhat.hat
            try:
                if (self.inputMap[index]["type"] == "Input.HAT"):
                    key = self.inputMap[index]["key"]
                    if (key == "trim"):
                        self.data["rollcal"] = e.value[0] * self.inputMap[index]["scale"]
                        self.data["pitchcal"] = e.value[1] * self.inputMap[index]["scale"]
            except Exception:
                # Hat not mapped, ignore..
                pass
            

        return self.data

    def enableRawReading(self, deviceId):
        """Enable reading of raw values (without mapping)"""
        logger.info("Now opening")
        #self.j = sdl2.joystick.SDL_JoystickOpen(deviceId)
        logger.info("Open")

    def disableRawReading(self):
        """Disable raw reading"""
        # No need to de-init since there's no good support for multiple input devices
        pass

    def readRawValues(self):
        """Read out the raw values from the device"""

        rawaxis = {}
        rawbutton = {}

        for event in sdl2.ext.get_events():
            if event.type == sdl2.SDL_JOYBUTTONDOWN:
                rawbutton[event.jbutton.button] = 1
            if event.type == sdl2.SDL_JOYBUTTONUP:
                rawbutton[event.jbutton.button] = 0
            if event.type == sdl2.SDL_JOYAXISMOTION:
                rawaxis[event.jaxis.axis] = event.jaxis.value / 32767.0
            if event.type == sdl2.SDL_JOYHATMOTION:
                if event.jhat.value == sdl2.SDL_HAT_CENTERED:
                    rawbutton[21] = 0
                    rawbutton[22] = 0
                    rawbutton[23] = 0
                    rawbutton[24] = 0
                elif event.jhat.value == sdl2.SDL_HAT_UP:
                    rawbutton[21] = 1
                elif event.jhat.value == sdl2.SDL_HAT_DOWN:
                    rawbutton[22] = 1
                elif event.jhat.value == sdl2.SDL_HAT_LEFT:
                    rawbutton[23] = 1
                elif event.jhat.value == sdl2.SDL_HAT_RIGHT:
                    rawbutton[24] = 1

        return [rawaxis,rawbutton]

    def getAvailableDevices(self):
        """List all the available devices."""
        logger.info("Looking for devices")
        dev = []
        names = []
        if hasattr(self, 'j') and sdl2.joystick.SDL_JoystickGetAttached(self.j):
            sdl2.joystick.SDL_JoystickClose(self.j)

        nbrOfInputs = sdl2.joystick.SDL_NumJoysticks()
        for i in range(0, nbrOfInputs):
            j = sdl2.joystick.SDL_JoystickOpen(i)
            name = sdl2.joystick.SDL_JoystickName(j)
            if names.count(name) > 0:
                name = "{0} #{1}".format(name, names.count(name) + 1)
            dev.append({"id":i, "name" : name})
            names.append(name)
            sdl2.joystick.SDL_JoystickClose(j)
        return dev
