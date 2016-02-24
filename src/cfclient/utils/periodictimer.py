#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013-2014 Bitcraze AB
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

import logging
from threading import Thread
from cflib.utils.callbacks import Caller
import time

__author__ = 'Bitcraze AB'
__all__ = ['PeriodicTimer']

logger = logging.getLogger(__name__)


class PeriodicTimer:
    """Create a periodic timer that will periodically call a callback"""

    def __init__(self, period, callback):
        self._callbacks = Caller()
        self._callbacks.add_callback(callback)
        self._started = False
        self._period = period
        self._thread = None

    def start(self):
        """Start the timer"""
        if self._thread:
            logger.warning("Timer already started, not restarting")
            return
        self._thread = _PeriodicTimerThread(self._period, self._callbacks)
        self._thread.setDaemon(True)
        self._thread.start()

    def stop(self):
        """Stop the timer"""
        if self._thread:
            self._thread.stop()
            self._thread = None


class _PeriodicTimerThread(Thread):

    def __init__(self, period, caller):
        super(_PeriodicTimerThread, self).__init__()
        self._period = period
        self._callbacks = caller
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        while not self._stop:
            time.sleep(self._period)
            if self._stop:
                break
            self._callbacks.call()
