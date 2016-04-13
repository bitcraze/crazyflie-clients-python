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
Test script to show how to use the ZMQ param backend for the Crazyflie
Python Client. The backend is started automatically in the client if ZMQ
is available.

The example will use the buzzer parameters (still testing firmware) and first
set the buzzer to on (at 4 kHz) for 3 seconds and then turn it off again.
"""
import time

try:
    import zmq
except ImportError as e:
    raise Exception("ZMQ library probably not installed ({})".format(e))

zmess = {
    "version": 1,
    "cmd": "",
    "name": "",
    "value": ""
}

zmess["cmd"] = "toc"

context = zmq.Context()
receiver = context.socket(zmq.REQ)
bind_addr = "tcp://127.0.0.1:{}".format(1024 + 189)
receiver.connect(bind_addr)
receiver.send_json(zmess)

response = receiver.recv_json()
print(response)

zmess = {
    "version": 1,
    "cmd": "set",
    "name": "buzzer.effect",
    "value": "0"
}
receiver.send_json(zmess)
response = receiver.recv_json()
print(response)

zmess = {
    "version": 1,
    "cmd": "set",
    "name": "buzzer.ratio",
    "value": "127"
}
receiver.send_json(zmess)
response = receiver.recv_json()
print(response)

zmess = {
    "version": 1,
    "cmd": "set",
    "name": "buzzer.freq",
    "value": "4000"
}
receiver.send_json(zmess)
response = receiver.recv_json()
print(response)

time.sleep(3)

zmess = {
    "version": 1,
    "cmd": "set",
    "name": "buzzer.ratio",
    "value": "0"
}
receiver.send_json(zmess)
response = receiver.recv_json()
print(response)
