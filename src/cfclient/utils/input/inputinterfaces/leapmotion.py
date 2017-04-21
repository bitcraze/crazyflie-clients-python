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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
#  USA.

"""
Leap Motion reader for controlling the Crazyflie. Note that this reader needs
the Leap Motion SDK to be manually copied. See src/leapsdk/__init__.py for
more info.
"""

try:
    import leapsdk.Leap as Leap
except Exception as e:
    raise Exception(
        "Leap Motion library probably not installed ({})".format(e))

import logging

__author__ = 'Bitcraze AB'
__all__ = ['LeapmotionReader']

logger = logging.getLogger(__name__)

MODULE_MAIN = "LeapmotionReader"
MODULE_NAME = "Leap Motion"


class LeapListener(Leap.Listener):

    def set_data_callback(self, callback):
        self._dcb = callback
        self._nbr_of_fingers = 0

    def on_init(self, controller):
        logger.info("Initialized")

    def on_connect(self, controller):
        logger.info("Connected")

    def on_disconnect(self, controller):
        # Note: not dispatched when running in a debugger.
        logger.info("Disconnected")

    def on_exit(self, controller):
        logger.info("Exited")

    def nbr_of_fingers(self):
        return self._nbr_of_fingers

    def on_frame(self, controller):
        # Get the most recent frame and report some basic information
        frame = controller.frame()
        data = {"roll": 0, "pitch": 0, "yaw": 0, "thrust": 0}
        if not frame.hands.is_empty:
            # Get the first hand
            hand = frame.hands[0]

            normal = hand.palm_normal
            direction = hand.direction
            # Pich and roll are mixed up...

            if len(hand.fingers) >= 4:
                data["roll"] = -direction.pitch * Leap.RAD_TO_DEG / 30.0
                data["pitch"] = -normal.roll * Leap.RAD_TO_DEG / 30.0
                data["yaw"] = direction.yaw * Leap.RAD_TO_DEG / 70.0
                # Use the elevation of the hand for thrust
                data["thrust"] = (hand.palm_position[1] - 80) / 150.0

            if data["thrust"] < 0.0:
                data["thrust"] = 0.0
            if data["thrust"] > 1.0:
                data["thrust"] = 1.0

        self._dcb(data)


class LeapmotionReader:
    """Used for reading data from input devices using the PyGame API."""

    def __init__(self):
        # pygame.init()
        self._ts = 0
        self._listener = LeapListener()
        self._listener.set_data_callback(self.leap_callback)
        self._controller = Leap.Controller()
        self._controller.add_listener(self._listener)
        self.name = MODULE_NAME

        self.limit_rp = True
        self.limit_thrust = True
        self.limit_yaw = True

        self.data = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                     "thrust": -1.0, "estop": False, "exit": False,
                     "assistedControl": False, "alt1": False, "alt2": False,
                     "pitchNeg": False, "rollNeg": False,
                     "pitchPos": False, "rollPos": False}
        logger.info("Initialized Leap")

    def open(self, deviceId):
        """
        Initialize the reading and open the device with deviceId and set the
        mapping for axis/buttons using the inputMap
        """
        return

    def leap_callback(self, data):
        for k in list(data.keys()):
            self.data[k] = data[k]

    def read(self, id):
        """Read input from the selected device."""
        return self.data

    def close(self, id):
        return

    def devices(self):
        """List all the available devices."""
        dev = []

        # According to API doc only 0 or 1 devices is supported
        # logger.info("Devs: {}".format(self._controller.is_connected))
        if self._controller.is_connected:
            dev.append({"id": 0, "name": "Leapmotion"})

        return dev
