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
import queue
from threading import Thread
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig

import cfclient

if os.name == 'posix':
    print('Disabling standard output for libraries!')
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

# Timeout before giving up when verifying param write
PARAM_TIMEOUT = 2
# Timeout before giving up connection
CONNECT_TIMEOUT = 5
# Timeout before giving up adding/starting log config
LOG_TIMEOUT = 10

logger = logging.getLogger(__name__)


class _SrvThread(Thread):

    def __init__(self, socket, log_socket, param_socket, conn_socket, cf,
                 *args):
        super(_SrvThread, self).__init__(*args)
        self._socket = socket
        self._log_socket = log_socket
        self._param_socket = param_socket
        self._conn_socket = conn_socket
        self._cf = cf

        self._cf.connected.add_callback(self._connected)
        self._cf.connection_failed.add_callback(self._connection_failed)
        self._cf.connection_lost.add_callback(self._connection_lost)
        self._cf.disconnected.add_callback(self._disconnected)
        self._cf.connection_requested.add_callback(self._connection_requested)
        self._cf.param.all_updated.add_callback(self._tocs_updated)
        self._cf.param.all_update_callback.add_callback(self._all_param_update)

        self._conn_queue = queue.Queue(1)
        self._param_queue = queue.Queue(1)
        self._log_started_queue = queue.Queue(1)
        self._log_added_queue = queue.Queue(1)

        self._logging_configs = {}

    def _connection_requested(self, uri):
        conn_ev = {"version": 1, "event": "requested", "uri": uri}
        self._conn_socket.send_json(conn_ev)

    def _connected(self, uri):
        conn_ev = {"version": 1, "event": "connected", "uri": uri}
        self._conn_socket.send_json(conn_ev)

    def _connection_failed(self, uri, msg):
        logger.info("Connection failed to {}: {}".format(uri, msg))
        resp = {"version": 1, "status": 1, "msg": msg}
        self._conn_queue.put_nowait(resp)
        conn_ev = {"version": 1, "event": "failed", "uri": uri, "msg": msg}
        self._conn_socket.send_json(conn_ev)

    def _connection_lost(self, uri, msg):
        conn_ev = {"version": 1, "event": "lost", "uri": uri, "msg": msg}
        self._conn_socket.send_json(conn_ev)

    def _disconnected(self, uri):
        conn_ev = {"version": 1, "event": "disconnected", "uri": uri}
        self._conn_socket.send_json(conn_ev)

    def _tocs_updated(self):
        # First do the log
        log_toc = self._cf.log.toc.toc
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
                    "access": "RW" if param_toc[group][
                        name].access == 0 else "RO",
                    "value": self._cf.param.values[group][name]}

        resp = {"version": 1, "status": 0, "log": log, "param": param}
        self._conn_queue.put_nowait(resp)

    def _handle_scanning(self):
        resp = {"version": 1}
        interfaces = cflib.crtp.scan_interfaces()
        resp["interfaces"] = []
        for i in interfaces:
            resp["interfaces"].append({"uri": i[0], "info": i[1]})
        return resp

    def _handle_connect(self, uri):
        self._cf.open_link(uri)
        return self._conn_queue.get(block=True)

    def _logging_started(self, conf, started):
        out = {"version": 1, "name": conf.name}
        if started:
            out["event"] = "started"
        else:
            out["event"] = "stopped"
        self._log_socket.send_json(out)
        self._log_started_queue.put_nowait(started)

    def _logging_added(self, conf, added):
        out = {"version": 1, "name": conf.name}
        if added:
            out["event"] = "created"
        else:
            out["event"] = "deleted"
        self._log_socket.send_json(out)
        self._log_added_queue.put_nowait(added)

    def _handle_logging(self, data):
        resp = {"version": 1}
        if data["action"] == "create":
            lg = LogConfig(data["name"], data["period"])
            for v in data["variables"]:
                lg.add_variable(v)
            lg.started_cb.add_callback(self._logging_started)
            lg.added_cb.add_callback(self._logging_added)
            try:
                lg.data_received_cb.add_callback(self._logdata_callback)
                self._logging_configs[data["name"]] = lg
                self._cf.log.add_config(lg)
                lg.create()
                self._log_added_queue.get(block=True, timeout=LOG_TIMEOUT)
                resp["status"] = 0
            except KeyError as e:
                resp["status"] = 1
                resp["msg"] = str(e)
            except AttributeError as e:
                resp["status"] = 2
                resp["msg"] = str(e)
            except queue.Empty:
                resp["status"] = 3
                resp["msg"] = "Log configuration did not start"
        if data["action"] == "start":
            try:
                self._logging_configs[data["name"]].start()
                self._log_started_queue.get(block=True, timeout=LOG_TIMEOUT)
                resp["status"] = 0
            except KeyError as e:
                resp["status"] = 1
                resp["msg"] = "{} config not found".format(str(e))
            except queue.Empty:
                resp["status"] = 2
                resp["msg"] = "Log configuration did not stop"
        if data["action"] == "stop":
            try:
                self._logging_configs[data["name"]].stop()
                self._log_started_queue.get(block=True, timeout=LOG_TIMEOUT)
                resp["status"] = 0
            except KeyError as e:
                resp["status"] = 1
                resp["msg"] = "{} config not found".format(str(e))
            except queue.Empty:
                resp["status"] = 2
                resp["msg"] = "Log configuration did not stop"
        if data["action"] == "delete":
            try:
                self._logging_configs[data["name"]].delete()
                self._log_added_queue.get(block=True, timeout=LOG_TIMEOUT)
                resp["status"] = 0
            except KeyError as e:
                resp["status"] = 1
                resp["msg"] = "{} config not found".format(str(e))
            except queue.Empty:
                resp["status"] = 2
                resp["msg"] = "Log configuration did not stop"

        return resp

    def _handle_param(self, data):
        resp = {"version": 1}
        group = data["name"].split(".")[0]
        name = data["name"].split(".")[1]
        self._cf.param.add_update_callback(group=group, name=name,
                                           cb=self._param_callback)
        try:
            self._cf.param.set_value(data["name"], str(data["value"]))
            answer = self._param_queue.get(block=True, timeout=PARAM_TIMEOUT)
            resp["name"] = answer["name"]
            resp["value"] = answer["value"]
            resp["status"] = 0
        except KeyError as e:
            resp["status"] = 1
            resp["msg"] = str(e)
        except AttributeError as e:
            resp["status"] = 2
            resp["msg"] = str(e)
        except queue.Empty:
            resp["status"] = 3
            resp["msg"] = "Timeout when setting parameter" \
                          "{}".format(data["name"])
        return resp

    def _all_param_update(self, name, value):
        resp = {"version": 1, "name": name, "value": value}
        self._param_socket.send_json(resp)

    def _param_callback(self, name, value):
        group = name.split(".")[0]
        name_short = name.split(".")[1]
        self._cf.param.remove_update_callback(group=group, name=name_short)
        self._param_queue.put_nowait({"name": name, "value": value})

    def _logdata_callback(self, ts, data, conf):
        out = {"version": 1, "name": conf.name, "event": "data",
               "timestamp": ts, "variables": {}}
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
                response = self._handle_scanning()
            elif cmd["cmd"] == "connect":
                response = self._handle_connect(cmd["uri"])
            elif cmd["cmd"] == "disconnect":
                self._cf.close_link()
                response["status"] = 0
            elif cmd["cmd"] == "log":
                response = self._handle_logging(cmd)
            elif cmd["cmd"] == "param":
                response = self._handle_param(cmd)
            else:
                response["status"] = 0xFF
                response["msg"] = "Unknown command {}".format(cmd["cmd"])
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
        """Start threads and bind ports"""
        cflib.crtp.init_drivers(enable_debug_driver=True)
        self._cf = Crazyflie(ro_cache=None,
                             rw_cache=cfclient.config_path + "/cache")

        signal.signal(signal.SIGINT, signal.SIG_DFL)

        self._base_url = base_url
        self._context = zmq.Context()

        cmd_srv = self._bind_zmq_socket(zmq.REP, "cmd", ZMQ_SRV_PORT)
        log_srv = self._bind_zmq_socket(zmq.PUB, "log", ZMQ_LOG_PORT)
        param_srv = self._bind_zmq_socket(zmq.PUB, "param", ZMQ_PARAM_PORT)
        ctrl_srv = self._bind_zmq_socket(zmq.PULL, "ctrl", ZMQ_CTRL_PORT)
        conn_srv = self._bind_zmq_socket(zmq.PUB, "conn", ZMQ_CONN_PORT)

        self._scan_thread = _SrvThread(cmd_srv, log_srv, param_srv, conn_srv,
                                       self._cf)
        self._scan_thread.start()

        self._ctrl_thread = _CtrlThread(ctrl_srv, self._cf)
        self._ctrl_thread.start()

    def _bind_zmq_socket(self, pattern, name, port):
        srv = self._context.socket(pattern)
        srv_addr = "{}:{}".format(self._base_url, port)
        srv.bind(srv_addr)
        logger.info("Biding ZMQ {} server"
                    "at {}".format(name, srv_addr))
        return srv


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


if __name__ == "__main__":
    main()
