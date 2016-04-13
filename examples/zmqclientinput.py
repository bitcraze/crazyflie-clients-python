#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Original code from rshum19


"""
Code showing how to control the Crazyflie using the ZMQ input socket.
This code will ramp the Crazyflie motors from 25% to 45%

To work, ZMQ has to be enabled in the client configuration and the client needs
to be connected to a Crazyflie.
See https://wiki.bitcraze.io/doc:crazyflie:client:pycfclient:zmq#input_device
for the protocol documentation.
"""

import time

try:
    import zmq
except ImportError as e:
    raise Exception("ZMQ library probably not installed ({})".format(e))

context = zmq.Context()
sender = context.socket(zmq.PUSH)
bind_addr = "tcp://127.0.0.1:{}".format(1024 + 188)
sender.connect(bind_addr)

cmdmess = {
    "version": 1,
    "ctrl": {
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        "thrust": 30
    }
}
print("starting to send control commands!")

# Unlocking thrust protection
cmdmess["ctrl"]["thrust"] = 0
sender.send_json(cmdmess)

for i in range(2500, 4500, 1):
    cmdmess["ctrl"]["thrust"] = i / 100.0
    sender.send_json(cmdmess)
    time.sleep(0.01)

cmdmess["ctrl"]["thrust"] = 0
sender.send_json(cmdmess)
