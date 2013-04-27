# -*- coding: utf8 -*-
#     ||
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
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Joystick driver using PyGame. This module works on all platform suported by
PyGames.
"""

import pygame
import pygame.locals

from .constants import TYPE_BUTTON, TYPE_AXIS
from .jevent import JEvent

class Joystick:
    """
    Pygame implementation of the Joystick class
    """

    def __init__(self):
        self.opened = False
        self.buttons = []
        self.axes = []
        self.joy = None
        self.device_id = -1
        
        pygame.init()
    
    def available_devices(self):
        """List all the available devices."""
        devices = {}

        count = pygame.joystick.get_count()
        for i in range(0, count):
            joy = pygame.joystick.Joystick(i)
            devices[i] = joy.get_name()

        return devices
    
    
    def open(self, device_id):
        """ 
        Open the joystick device. The device_id is given by 
        available_devices
        """
        if self.joy:
            raise Exception("Joystick already open")
    
        self.joy = pygame.joystick.Joystick(device_id)
        self.joy.init()
        
        self.axes = list(0 for i in range(self.joy.get_numaxes()))
        self.buttons = list(0 for i in range(self.joy.get_numbuttons()))

    def close(self):
        """ Open the joystick device """
        self.joy.quit()
        self.joy = None

    def get_events(self):
        """ Returns a list of all joystick event since the last call """
        events = []
        
        for evt in pygame.event.get():
            if evt.type == pygame.locals.JOYBUTTONDOWN:
                events.append(JEvent (type = TYPE_BUTTON,
                                      number = evt.button,
                                      value  = 1,
                                     ))
                self.buttons[evt.button] = 1
            if evt.vttype == pygame.locals.JOYBUTTONUP:
                events.append(JEvent (type = TYPE_BUTTON,
                                      number = evt.button,
                                      value  = 0,
                                     ))
                self.buttons[evt.button] = 0
            if evt.type == pygame.locals.JOYAXISMOTION:
                events.append(JEvent (type = TYPE_AXIS,
                                      number = evt.axis,
                                      value  = self.joy.get_axis(evt.axis),
                                     ))
                self.axes[evt.axis] = self.joy.get_axis(evt.axis)

        return events
    
