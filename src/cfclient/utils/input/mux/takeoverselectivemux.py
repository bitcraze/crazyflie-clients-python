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
Mux for controlling roll/pitch from one device (slave/student) and the rest
from a second device (master/teacher) with the possibility to take over
roll/pitch as well.
"""

import logging

from . import InputMux

__author__ = 'Bitcraze AB'
__all__ = ['TakeOverSelectiveMux']

logger = logging.getLogger(__name__)


class TakeOverSelectiveMux(InputMux):

    def __init__(self, *args):
        super(TakeOverSelectiveMux, self).__init__(*args)
        self._master = "Teacher"
        self._slave = "Student"
        self.name = "Teacher (RP)"
        self._devs = {self._master: None, self._slave: None}

        self._muxing = {
            self._master: ("thrust", "yaw", "estop", "alt1", "alt2",
                           "assistedControl", "exit"),
            self._slave: ("roll", "pitch")
        }

    def read(self):
        try:
            if self._devs[self._master] and self._devs[self._slave]:
                dm = self._devs[self._master].read()
                ds = self._devs[self._slave].read()
                if not dm.muxswitch:
                    for key in self._muxing[self._slave]:
                        dm.set(key, ds.get(key))

                return dm
            else:
                return None

        except Exception as e:
            logger.warning(e)
            return None
