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
Test script to show how to use the ZMQ LED-ring backend for the Crazyflie
Python Client. The backend is started automatically in the client if ZMQ
is available.

The example will fill up the ring by sending 12 message, each with a new
LED lit up, until all of them are lit up in the last message.
"""

try:
    import zmq
except ImportError as e:
    raise Exception("ZMQ library probably not installed ({})".format(e))

zmess = {
    "version": 1,
    "rgbleds": [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0]
    ]
}

context = zmq.Context()
receiver = context.socket(zmq.PUSH)
bind_addr = "tcp://127.0.0.1:{}".format(1024 + 190)
receiver.connect(bind_addr)

for i in range(12):
    zmess["rgbleds"][i] = [128, 0, 128]
    receiver.send_json(zmess)
