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
A quick implementation of a Leapmotion reader for controlling the Crazyflie.
"""

__author__ = 'Bitcraze AB'
__all__ = ['LeapmotionReader']
import time
import leapmotion.Leap, sys
from leapmotion.Leap import CircleGesture, KeyTapGesture, ScreenTapGesture, SwipeGesture
import logging

logger = logging.getLogger(__name__)

class LeapListener(leapmotion.Leap.Listener):

    def set_data_callback(self, callback):
        self._dcb = callback

    def on_init(self, controller):
        logger.info("Initialized")

    def on_connect(self, controller):
        logger.info("Connected")

        # Enable gestures
        #controller.enable_gesture(leapmotion.Leap.Gesture.TYPE_CIRCLE);
        #controller.enable_gesture(leapmotion.Leap.Gesture.TYPE_KEY_TAP);
        #controller.enable_gesture(leapmotion.Leap.Gesture.TYPE_SCREEN_TAP);
        #controller.enable_gesture(leapmotion.Leap.Gesture.TYPE_SWIPE);

    def on_disconnect(self, controller):
        # Note: not dispatched when running in a debugger.
        logger.info("Disconnected")

    def on_exit(self, controller):
        logger.info("Exited")

    def on_frame(self, controller):
        # Get the most recent frame and report some basic information
        frame = controller.frame()

        #logger.info("Frame id: %d, timestamp: %d, hands: %d, fingers: %d, tools: %d, gestures: %d" % (
        #                              frame.id, frame.timestamp, len(frame.hands), len(frame.fingers), len(frame.tools), len(frame.gestures())))
        if not frame.hands.empty:
            # Get the first hand
            hand = frame.hands[0]

            normal = hand.palm_normal
            direction = hand.direction
            # Pich and roll are mixed up...
            roll = -direction.pitch * leapmotion.Leap.RAD_TO_DEG / 45.0
            pitch = -normal.roll * leapmotion.Leap.RAD_TO_DEG / 45.0
            yaw = direction.yaw * leapmotion.Leap.RAD_TO_DEG / 90.0
            thrust = (hand.palm_position[1] - 50)/200.0 # Use the elevation of the hand for thrust

            if thrust < 0.0:
                thrust = 0.0;
            if thrust > 1.0:
                thrust = 1.0

            # Protect against accidental readings. When tilting the had
            # fingers are sometimes lost so only use 4.
            if (len(hand.fingers) < 4):
                self._dcb(0,0,0,0)
            else:
                self._dcb(pitch, roll, yaw, thrust)

        else:
            self._dcb(0, 0, 0, 0)

class LeapmotionReader():
    """Used for reading data from input devices using the PyGame API."""
    def __init__(self):
        self.inputMap = None
        #pygame.init()
        self.data = {"roll":0.0, "pitch":0.0, "yaw":0.0, "thrust":0.0, "pitchcal":0.0, "rollcal":0.0, "estop": False, "exit":False}
        logger.info("Initializing")
        self._listener = LeapListener()
        self._listener.set_data_callback(self.leap_callback)
        logger.info("Created listender")
        self._controller = leapmotion.Leap.Controller()
        logger.info("Created controller")
        self._controller.add_listener(self._listener)
        logger.info("Registered listener")

    def start_input(self, deviceId, inputMap):
        """Initalize the reading and open the device with deviceId and set the mapping for axis/buttons using the
        inputMap"""
        self.data = {"roll":0.0, "pitch":0.0, "yaw":0.0, "thrust":0.0, "pitchcal":0.0, "rollcal":0.0, "estop": False, "exit":False}
        #self.inputMap = inputMap
        #self.j = pygame.joystick.Joystick(deviceId)
        #self.j.init()

    def leap_callback(self, roll, pitch, yaw, thrust):
        #logger.info("CB:%f,%f,%f"%(roll, pitch,yaw, thrust))

        self.data["roll"] = roll
        self.data["pitch"] = pitch
        self.data["yaw"] = yaw
        self.data["thrust"] = thrust

    def readInput(self):
        """Read input from the selected device."""
        # We only want the pitch/roll cal to be "oneshot", don't
        # save this value.
        self.data["pitchcal"] = 0.0
        self.data["rollcal"] = 0.0
        #for e in pygame.event.get():
        #  if e.type == pygame.locals.JOYAXISMOTION:
        #    index = "Input.AXIS-%d" % e.axis 
        #    try:
        #        if (self.inputMap[index]["type"] == "Input.AXIS"):
        #            key = self.inputMap[index]["key"]
        #            axisvalue = self.j.get_axis(e.axis)
        #            # All axis are in the range [-a,+a]
        #            axisvalue = axisvalue * self.inputMap[index]["scale"]
        #            # The value is now in the correct direction and in the range [-1,1]
        #            self.data[key] = axisvalue
        #    except Exception:
        #        # Axis not mapped, ignore..
        #        pass          

        #  if e.type == pygame.locals.JOYBUTTONDOWN:
        #    index = "Input.BUTTON-%d" % e.button 
        #    try:
        #        if (self.inputMap[index]["type"] == "Input.BUTTON"):
        #            key = self.inputMap[index]["key"]
        #            if (key == "estop"):
        #                self.data["estop"] = not self.data["estop"]
        #            elif (key == "exit"):
        #                self.data["exit"] = True
        #            else: # Generic cal for pitch/roll
        #                self.data[key] = self.inputMap[index]["scale"]
        #    except Exception:
        #        # Button not mapped, ignore..
        #        pass

        return self.data

    def enableRawReading(self, deviceId):
        """Enable reading of raw values (without mapping)"""
        #self.j = pygame.joystick.Joystick(deviceId)
        #self.j.init()
        return

    def disableRawReading(self):
        """Disable raw reading"""
        # No need to de-init since there's no good support for multiple input devices
        return

    def readRawValues(self):
        """Read out the raw values from the device"""
        rawaxis = {}
        rawbutton = {}

        #for e in pygame.event.get():
        #    if e.type == pygame.locals.JOYBUTTONDOWN:
        #        rawbutton[e.button] = 1
        #    if e.type == pygame.locals.JOYBUTTONUP:
        #        rawbutton[e.button] = 0
        #    if e.type == pygame.locals.JOYAXISMOTION:
        #        rawaxis[e.axis] = self.j.get_axis(e.axis)

        return [rawaxis,rawbutton]

    def getAvailableDevices(self):
        """List all the available devices."""
        dev = []
        #pygame.joystick.quit()
        #pygame.joystick.init()
        #nbrOfInputs = pygame.joystick.get_count()
        #for i in range(0,nbrOfInputs):
        #    j = pygame.joystick.Joystick(i)
        #    dev.append({"id":i, "name" : j.get_name()})
        
        dev.append({"id": 0, "name" : "Leapmotion"})
        
        return dev

