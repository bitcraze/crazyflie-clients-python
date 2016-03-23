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
Give access to the parameter framework via ZMQ.
"""

import logging
from threading import Thread, Lock

ZMQ_PULL_PORT = 1024 + 189
logger = logging.getLogger(__name__)

enabled = False
try:
    import zmq

    enabled = True
except Exception as e:
    logger.warning(
        "Not enabling ZMQ param access, import failed ({})".format(e))


class _PullReader(Thread):

    def __init__(self, receiver, callback, *args):
        super(_PullReader, self).__init__(*args)
        self._receiver = receiver
        self._cb = callback
        self.daemon = True
        self.lock = Lock()

    def run(self):
        while True:
            self.lock.acquire()
            self._cb(self._receiver.recv_json())


class ZMQParamAccess:
    """Used for reading data from input devices using the PyGame API."""

    def __init__(self, crazyflie):

        if enabled:
            self._cf = crazyflie
            context = zmq.Context()
            self._receiver = context.socket(zmq.REP)
            self._bind_addr = "tcp://*:{}".format(ZMQ_PULL_PORT)
            # If the port is already bound an exception will be thrown
            # and caught in the initialization of the readers and handled.
            self._receiver.bind(self._bind_addr)
            logger.info(
                "Biding ZMQ for parameters at {}".format(self._bind_addr))
            self._receiver_thread = _PullReader(self._receiver,
                                                self._cmd_callback)

    def start(self):
        if enabled:
            self._receiver_thread.start()

    def _cmd_callback(self, data):
        # logger.info(data)
        if data["cmd"] == "toc":
            response = {"version": 1, "toc": []}
            self._receiver.send_json(response)
            self._receiver_thread.lock.release()
        if data["cmd"] == "set":
            resp = {"version": 1}  # noqa
            group = data["name"].split(".")[0]
            name = data["name"].split(".")[1]
            self._cf.param.add_update_callback(group=group, name=name,
                                               cb=self._param_callback)
            self._cf.param.set_value(data["name"], str(data["value"]))

    def _param_callback(self, name, value):
        group = name.split(".")[0]
        name_short = name.split(".")[1]
        logger.info("Removing {}.{}".format(group, name_short))
        self._cf.param.remove_update_callback(group=group, name=name_short,
                                              cb=self._param_callback)

        response = {"version": 1, "cmd": "set", "name": name, "value": value}
        self._receiver.send_json(response)
        self._receiver_thread.lock.release()
