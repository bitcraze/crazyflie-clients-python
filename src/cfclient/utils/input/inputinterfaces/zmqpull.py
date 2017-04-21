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
Input interface that supports receiving commands via ZMQ.
"""

import logging
from threading import Thread

from cfclient.utils.config import Config

try:
    import zmq
except Exception as e:
    raise Exception("ZMQ library probably not installed ({})".format(e))

if not Config().get("enable_zmq_input"):
    raise Exception("ZMQ input disabled in config file")

__author__ = 'Bitcraze AB'
__all__ = ['ZMQReader']

ZMQ_PULL_PORT = 1024 + 188

logger = logging.getLogger(__name__)

MODULE_MAIN = "ZMQReader"
MODULE_NAME = "ZMQ"


class _PullReader(Thread):

    def __init__(self, receiver, callback, *args):
        super(_PullReader, self).__init__(*args)
        self._receiver = receiver
        self._cb = callback
        self.daemon = True

    def run(self):
        while True:
            self._cb(self._receiver.recv_json())


class ZMQReader:
    """Used for reading data from input devices using the PyGame API."""

    def __init__(self):
        context = zmq.Context()
        receiver = context.socket(zmq.PULL)
        self._bind_addr = "tcp://127.0.0.1:{}".format(ZMQ_PULL_PORT)
        # If the port is already bound an exception will be thrown
        # and caught in the initialization of the readers and handled.
        receiver.bind(self._bind_addr)
        logger.info("Biding ZMQ at {}".format(self._bind_addr))

        self.name = MODULE_NAME

        self.limit_rp = False
        self.limit_thrust = False
        self.limit_yaw = False

        self.data = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                     "thrust": -1.0, "estop": False, "exit": False,
                     "assistedControl": False, "alt1": False, "alt2": False,
                     "pitchNeg": False, "rollNeg": False,
                     "pitchPos": False, "rollPos": False}

        logger.info("Initialized ZMQ")

        self._receiver_thread = _PullReader(receiver, self._cmd_callback)
        self._receiver_thread.start()

    def _cmd_callback(self, cmd):
        for k in list(cmd["ctrl"].keys()):
            self.data[k] = cmd["ctrl"][k]

    def open(self, device_id):
        """
        Initialize the reading and open the device with deviceId and set the
        mapping for axis/buttons using the inputMap
        """
        return

    def read(self, device_id):
        """Read input from the selected device."""

        return self.data

    def close(self, device_id):
        return

    def devices(self):
        """List all the available connections"""
        # As a temporary workaround we always say we have ZMQ
        # connected. If it's not connected, there's just no data.
        return [{"id": 0, "name": "ZMQ@{}".format(self._bind_addr)}]
