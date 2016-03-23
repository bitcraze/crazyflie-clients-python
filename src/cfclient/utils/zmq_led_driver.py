#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2015 Bitcraze AB
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
Give access to the LED driver memory via ZMQ.
"""

from cflib.crazyflie.mem import MemoryElement

import logging
from threading import Thread, Lock

ZMQ_PULL_PORT = 1024 + 190
logger = logging.getLogger(__name__)

enabled = False
try:
    import zmq

    enabled = True
except Exception as e:
    logger.warning("Not enabling ZMQ LED driver access,"
                   "import failed ({})".format(e))


class _PullReader(Thread):
    """Blocking thread for reading from ZMQ socket"""

    def __init__(self, receiver, callback, *args):
        """Initialize"""
        super(_PullReader, self).__init__(*args)
        self._receiver = receiver
        self._cb = callback
        self.daemon = True
        self.lock = Lock()

    def run(self):
        while True:
            # self.lock.acquire()
            self._cb(self._receiver.recv_json())


class ZMQLEDDriver:
    """Used for reading data from input devices using the PyGame API."""

    def __init__(self, crazyflie):

        if enabled:
            self._cf = crazyflie
            context = zmq.Context()
            self._receiver = context.socket(zmq.PULL)
            self._bind_addr = "tcp://*:{}".format(ZMQ_PULL_PORT)
            # If the port is already bound an exception will be thrown
            # and caught in the initialization of the readers and handled.
            self._receiver.bind(self._bind_addr)
            logger.info("Biding ZMQ for LED driver"
                        "at {}".format(self._bind_addr))
            self._receiver_thread = _PullReader(self._receiver,
                                                self._cmd_callback)

    def start(self):
        if enabled:
            self._receiver_thread.start()

    def _cmd_callback(self, data):
        """Called when new data arrives via ZMQ"""
        if len(self._cf.mem.get_mems(MemoryElement.TYPE_DRIVER_LED)) > 0:
            logger.info("Updating memory")
            memory = self._cf.mem.get_mems(MemoryElement.TYPE_DRIVER_LED)[0]
            for i_led in range(len(data["rgbleds"])):
                memory.leds[i_led].set(data["rgbleds"][i_led][0],
                                       data["rgbleds"][i_led][1],
                                       data["rgbleds"][i_led][2])
            memory.write_data(self._write_cb)

    def _write_cb(self, mem, addr):
        return
