#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013 Bitcraze AB
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

#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc., 51
#  Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Implementation of a periodic timer that will call a callback every time
the timer expires once started.
"""

__author__ = 'Bitcraze AB'
__all__ = ['PeriodicTimer']

import logging
from threading import Timer
from cflib.utils.callbacks import Caller

logger = logging.getLogger(__name__)

class PeriodicTimer:
    """Create a periodic timer that will periodicall call a callback"""
    def __init__(self, period, callback):
        self._callbacks = Caller()
        self._callbacks.add_callback(callback)
        self._started = False
        self._period = period
        self._timer = Timer(period, self._expired)
        self._timer.daemon = True

    def start(self):
        """Start the timer"""
        self._timer = Timer(self._period, self._expired)
        self._timer.daemon = True
        self._timer.start()
        self._started = True

    def stop(self):
        """Stop the timer"""
        self._timer.cancel()
        self._started = False

    def _expired(self):
        """Callback for the expired internal timer"""
        self._callbacks.call()
        if self._started:
            self.start() 

