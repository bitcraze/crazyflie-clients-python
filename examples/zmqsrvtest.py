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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
ZMQ server test application. Use CTRL-C to end the application.

NOTE! If connected to a Crazyflie this will power on the motors!
"""

from threading import Thread
import signal
import time
import sys

try:
    import zmq
except ImportError as e:
    raise Exception("ZMQ library probably not installed ({})".format(e))


class _LogThread(Thread):

    def __init__(self, socket, *args):
        super(_LogThread, self).__init__(*args)
        self._socket = socket

    def run(self):
        while True:
            log = self._socket.recv_json()
            if log["event"] == "data":
                print(log)
            if log["event"] == "created":
                print("Created block {}".format(log["name"]))
            if log["event"] == "started":
                print("Started block {}".format(log["name"]))
            if log["event"] == "stopped":
                print("Stopped block {}".format(log["name"]))
            if log["event"] == "deleted":
                print("Deleted block {}".format(log["name"]))


class _ParamThread(Thread):

    def __init__(self, socket, *args):
        super(_ParamThread, self).__init__(*args)
        self._socket = socket

    def run(self):
        while True:
            param = self._socket.recv_json()
            print(param)


class _ConnThread(Thread):

    def __init__(self, socket, *args):
        super(_ConnThread, self).__init__(*args)
        self._socket = socket

    def run(self):
        while True:
            msg = self._socket.recv_json()
            print(msg)


class _CtrlThread(Thread):

    def __init__(self, socket, *args):
        super(_CtrlThread, self).__init__(*args)
        self._socket = socket
        self._thrust_max = 30000
        self._thrust_min = 20000
        self._thrust = self._thrust_min
        self._thrust_step = 100
        self._cmd = {
            "version": 1,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "thrust": 0.0
        }

    def run(self):
        print("Starting to send control commands!")
        while True:
            time.sleep(0.01)
            self._thrust += self._thrust_step
            if (self._thrust >= self._thrust_max or
                    self._thrust <= self._thrust_min):
                self._thrust_step *= -1
            self._cmd["thrust"] = self._thrust
            self._socket.send_json(self._cmd)


signal.signal(signal.SIGINT, signal.SIG_DFL)

SRV_ADDR = "tcp://127.0.0.1"
CF_URI = "radio://0/10/250K"

context = zmq.Context()
client_conn = context.socket(zmq.REQ)
client_conn.connect("{}:2000".format(SRV_ADDR))

log_conn = context.socket(zmq.SUB)
log_conn.connect("{}:2001".format(SRV_ADDR))
log_conn.setsockopt_string(zmq.SUBSCRIBE, u"")

param_conn = context.socket(zmq.SUB)
param_conn.connect("{}:2002".format(SRV_ADDR))
param_conn.setsockopt_string(zmq.SUBSCRIBE, u"")

conn_conn = context.socket(zmq.SUB)
conn_conn.connect("{}:2003".format(SRV_ADDR))
conn_conn.setsockopt_string(zmq.SUBSCRIBE, u"")

ctrl_conn = context.socket(zmq.PUSH)
ctrl_conn.connect("{}:2004".format(SRV_ADDR))

# Start async threads
log_thread = _LogThread(log_conn)
log_thread.start()

param_thread = _ParamThread(param_conn)
param_thread.start()

conn_thread = _ConnThread(conn_conn)
conn_thread.start()

print("Trying unknown command ...", end=' ')
scan_cmd = {
    "version": 1,
    "cmd": "blah"
}
client_conn.send_json(scan_cmd)
resp = client_conn.recv_json()
if resp["status"] != 0:
    print("fail! {}".format(resp["msg"]))
else:
    print("done!")

print("Scanning for Crazyflies ...", end=' ')
scan_cmd = {
    "version": 1,
    "cmd": "scan"
}
client_conn.send_json(scan_cmd)
resp = client_conn.recv_json()
print("done!")
for i in resp["interfaces"]:
    print("\t{} - {}".format(i["uri"], i["info"]))

connect_cmd = {
    "version": 1,
    "cmd": "connect",
    "uri": "{}".format(CF_URI)
}
print("Connecting to {} ...".format(connect_cmd["uri"]), end=' ')
client_conn.send_json(connect_cmd)
resp = client_conn.recv_json()
if resp["status"] != 0:
    print("fail! {}".format(resp["msg"]))
    sys.exit(1)
print("done!")

# Do logging
print("Loggable variables")
for group in resp["log"]:
    print("\t{}".format(group))
    for name in resp["log"][group]:
        print("\t  {} ({})".format(name,
                                   resp["log"][group][name]["type"]))

print("Parameter variables")
for group in resp["param"]:
    print("\t{}".format(group))
    for name in resp["param"][group]:
        print("\t  {} ({}, {})= {}".format(
            name, resp["param"][group][name]["type"],
            resp["param"][group][name]["access"],
            resp["param"][group][name]["value"]))

log_cmd = {
    "version": 1,
    "cmd": "log",
    "action": "create",
    "name": "Test log block",
    "period": 1000,
    "variables": [
        "pm.vbat",
        "stabilizer.roll"
    ]
}
print("Creating logging {} ...".format(log_cmd["name"]), end=' ')
client_conn.send_json(log_cmd)
resp = client_conn.recv_json()
if resp["status"] == 0:
    print("done!")
else:
    print("fail! {}".format(resp["msg"]))

log_cmd = {
    "version": 1,
    "cmd": "log",
    "action": "start",
    "name": "Test log block"
}
print("Starting logging {} ...".format(log_cmd["name"]), end=' ')
client_conn.send_json(log_cmd)
resp = client_conn.recv_json()
if resp["status"] == 0:
    print("done!")
else:
    print("fail!")

param_cmd = {
    "version": 1,
    "cmd": "param",
    "name": "system.selftestPassed",
    "value": True
}

print("Setting param {} to {}...".format(param_cmd["name"],
                                         param_cmd["value"]), end=' ')
client_conn.send_json(param_cmd)
resp = client_conn.recv_json()
if resp["status"] == 0:
    print("done!")
else:
    print("fail! {}".format(resp["msg"]))


# Start sending control commands
ctrl = _CtrlThread(ctrl_conn)
ctrl.start()

# Wait a bit, then stop the logging
time.sleep(5)

log_cmd = {
    "version": 1,
    "cmd": "log",
    "action": "stop",
    "name": "No name",
}
print("Stopping logging {} ...".format(log_cmd["name"]), end=' ')
client_conn.send_json(log_cmd)
resp = client_conn.recv_json()
if resp["status"] == 0:
    print("done!")
else:
    print("fail! {}".format(resp["msg"]))

log_cmd = {
    "version": 1,
    "cmd": "log",
    "action": "stop",
    "name": "Test log block",
}
print("Stopping logging {} ...".format(log_cmd["name"]), end=' ')
client_conn.send_json(log_cmd)
resp = client_conn.recv_json()
if resp["status"] == 0:
    print("done!")
else:
    print("fail!")

log_cmd = {
    "version": 1,
    "cmd": "log",
    "action": "delete",
    "name": "Test log block",
}
print("Deleting logging {} ...".format(log_cmd["name"]), end=' ')
client_conn.send_json(log_cmd)
resp = client_conn.recv_json()
if resp["status"] == 0:
    print("done!")
else:
    print("fail!")


# Wait a bit, then disconnect
time.sleep(5)

connect_cmd = {
    "version": 1,
    "cmd": "disconnect",
    "uri": "{}".format(CF_URI)
}
print("Disconnecting from {} ...".format(connect_cmd["uri"]), end=' ')
client_conn.send_json(connect_cmd)
resp = client_conn.recv_json()
if resp["status"] != 0:
    print("fail! {}".format(resp["msg"]))
    sys.exit(1)
print("done!")
