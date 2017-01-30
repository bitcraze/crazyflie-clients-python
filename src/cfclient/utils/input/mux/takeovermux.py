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
Mux for giving control to one device (slave/student) for all axis (roll/pitch/
yaw/thrust) with the ability to take over all of them from a second device
(master/teacher).
"""
import logging

from .takeoverselectivemux import TakeOverSelectiveMux

__author__ = 'Bitcraze AB'
__all__ = ['TakeOverMux']

logger = logging.getLogger(__name__)


class TakeOverMux(TakeOverSelectiveMux):

    def __init__(self, *args):
        super(TakeOverMux, self).__init__(*args)
        self.name = "Teacher (RPYT)"
        self._muxing = {
            self._master: ("estop", "alt1", "alt2", "assistedControl", "exit"),
            self._slave: ("roll", "pitch", "yaw", "thrust")
        }
