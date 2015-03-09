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
Server used to connect to a Crazyflie using ZMQ.


"""

import sys
import os
import logging
import signal
import zmq

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from threading import Thread
from Queue import Queue

if os.name == 'posix':
    print 'Disabling standard output for libraries!'
    stdout = os.dup(1)
    os.dup2(os.open('/dev/null', os.O_WRONLY), 1)
    sys.stdout = os.fdopen(stdout, 'w')

# set SDL to use the dummy NULL video driver, 
#   so it doesn't need a windowing system.
os.environ["SDL_VIDEODRIVER"] = "dummy"

# Main command socket for control (ping/pong)
ZMQ_SRV_PORT = 2000
# Log data socket (publish)
ZMQ_LOG_PORT = 2001
# Param value updated (publish)
ZMQ_PARAM_PORT = 2002
# Async event for connection, like connection lost (publish)
ZMQ_CONN_PORT = 2003
# Control set-poins for Crazyflie (pull)
ZMQ_CTRL_PORT = 2004

logger = logging.getLogger(__name__)

class _SrvThread(Thread):

    def __init__(self, socket, log_socket, param_socket, cf, *args):
        super(_SrvThread, self).__init__(*args)
        self._socket = socket
        self._log_socket = log_socket
        self._param_socket = param_socket
        #self.daemon = True
        self._cf =cf

        self._cf.connected.add_callback(self._connected)
        self._cf.param.all_updated.add_callback(self._tocs_updated)

        self._conn_queue = Queue(1)
        self._param_queue = Queue(1)

    def _connected(self, uri):
        logger.info("Connected to {}".format(uri))

    def _tocs_updated(self):
        # First do the log
        log_toc = self._cf.log._toc.toc
        log = {}
        for group in log_toc:
            log[group] = {}
            for name in log_toc[group]:
                log[group][name] = {"type": log_toc[group][name].ctype}
        # The the params
        param_toc = self._cf.param.toc.toc
        param = {}
        for group in param_toc:
            param[group] = {}
            for name in param_toc[group]:
                param[group][name] = {
                    "type": param_toc[group][name].ctype,
                    "access": "RW" if param_toc[group][name].access == 0 else "RO",
                    "value": self._cf.param.values[group][name]}

        self._conn_queue.put_nowait([log, param])

    def _disconnected(self, uri):
        print "Disconnected from {}".format(uri)

    def _handle_scanning(self, data):
        interfaces = cflib.crtp.scan_interfaces()
        data["interfaces"] = []
        for i in interfaces:
            data["interfaces"].append({"uri": i[0], "info": i[1]})

    def _handle_connect(self, uri, data):
        self._cf.open_link(uri)
        [data["log"], data["param"]] = self._conn_queue.get(block=True)

    def _handle_logging(self, data):
        if data["action"] == "create":
            lg = LogConfig(data["name"], data["period"])
            for v in data["variables"]:
                lg.add_variable(v)

            self._cf.log.add_config(lg)
            if lg.valid:
                lg.data_received_cb.add_callback(self._logdata_callback)
                #lg.error_cb.add_callback(self._log_error_signal.emit)
                lg.start()
                return 0

            else:
                logger.warning("Could not setup logconfiguration after "
                               "connection!")
                return 1

    def _handle_param(self, data, response):
        group = data["name"].split(".")[0]
        name = data["name"].split(".")[1]
        self._cf.param.add_update_callback(group=group, name=name,
                                           cb=self._param_callback)
        self._cf.param.set_value(data["name"], str(data["value"]))
        answer = self._param_queue.get(block=True)
        response["name"] = answer["name"]
        response["value"] = answer["value"]
        response["status"] = 0

    def _param_callback(self, name, value):
        group = name.split(".")[0]
        name_short = name.split(".")[1]
        self._cf.param.remove_update_callback(group=group, name=name_short)
        self._param_queue.put_nowait({"name": name, "value": value})

    def _logdata_callback(self, ts, data, conf):
        out = {"version": 1, "name": conf.name, "timestamp": ts, "variables": {}}
        for d in data:
            out["variables"][d] = data[d]
        self._log_socket.send_json(out)

    def run(self):
        logger.info("Starting server thread")
        while True:
            # Wait for the command
            cmd = self._socket.recv_json()
            response = {"version": 1}
            logger.info("Got command {}".format(cmd))
            if cmd["cmd"] == "scan":
                self._handle_scanning(response)
            if cmd["cmd"] == "connect":
                self._handle_connect(cmd["uri"], response)
            if cmd["cmd"] == "log":
                response["status"] = self._handle_logging(cmd)
            if cmd["cmd"] == "param":
                self._handle_param(cmd, response)
            self._socket.send_json(response)

class _CtrlThread(Thread):
    def __init__(self, socket, cf, *args):
        super(_CtrlThread, self).__init__(*args)
        self._socket = socket
        self._cf = cf

    def run(self):
        while True:
            cmd = self._socket.recv_json()
            self._cf.commander.send_setpoint(cmd["roll"], cmd["pitch"],
                                             cmd["yaw"], cmd["thrust"])


class ZMQServer():
    """Crazyflie ZMQ server"""

    def __init__(self, base_url):
        """Initialize the headless client and libraries"""
        cflib.crtp.init_drivers(enable_debug_driver=True)

        self._cf = Crazyflie(ro_cache=sys.path[0]+"/cflib/cache",
                             rw_cache=sys.path[1]+"/cache")

        signal.signal(signal.SIGINT, signal.SIG_DFL)

        context = zmq.Context()
        srv = context.socket(zmq.REP)
        self._srv_addr = "{}:{}".format(base_url, ZMQ_SRV_PORT)
        srv.bind(self._srv_addr)
        logger.info("Biding ZMQ command server at {}".format(self._srv_addr))

        log_srv = context.socket(zmq.PUB)
        self._log_srv_addr = "{}:{}".format(base_url, ZMQ_LOG_PORT)
        log_srv.bind(self._log_srv_addr)
        logger.info("Biding ZMQ log server at {}".format(self._log_srv_addr))

        param_srv = context.socket(zmq.PUB)
        self._param_srv_addr = "{}:{}".format(base_url, ZMQ_PARAM_PORT)
        param_srv.bind(self._param_srv_addr)
        logger.info("Biding ZMQ param server at {}".format(self._param_srv_addr))

        ctrl_srv = context.socket(zmq.PULL)
        self._ctrl_srv_addr = "{}:{}".format(base_url, ZMQ_CTRL_PORT)
        ctrl_srv.bind(self._ctrl_srv_addr)
        logger.info("Biding ZMQ ctrl server at {}".format(self._ctrl_srv_addr))

        self._scan_thread = _SrvThread(srv, log_srv, param_srv, self._cf)
        self._scan_thread.start()

        self._ctrl_thread = _CtrlThread(ctrl_srv, self._cf)
        self._ctrl_thread.start()


def main():
    """Main Crazyflie ZMQ application"""
    import argparse

    parser = argparse.ArgumentParser(prog="cfzmq")
    parser.add_argument("-u", "--url", action="store", dest="url", type=str,
                        default="tcp://127.0.0.1",
                        help="URL where ZMQ will accept connections")
    parser.add_argument("-d", "--debug", action="store_true", dest="debug",
                        help="Enable debug output")
    (args, unused) = parser.parse_known_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    ZMQServer(args.url)

    # CRTL-C to exit
