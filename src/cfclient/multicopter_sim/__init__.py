#  MulticopterSim client for Crazyflie client GUI
#  Uses a TCP socket to accept vehicle pose and send back stick demands
#
#  Copyright (C) 2023 Simon D. Levy
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

from sys import stdout
import socket
import numpy as np
from threading import Thread
from time import sleep


class MulticopterSimClient:

    def __init__(self, host='127.0.0.1', motor_port=5000, telemetry_port=5001):

        self.connected = False

        self.host = host
        self.motor_port = motor_port
        self.telemetry_port = telemetry_port

    def connect(self):
        '''
        Returns True on success, False on failure
        '''

        motorClientSocket = self._make_udpsocket()

        telemetryServerSocket = self._make_udpsocket()
        telemetryServerSocket.bind((self.host, self.telemetry_port))

        self.connected = True

        self.sticks = np.zeros(4, dtype=np.float32)
        self.pose = np.zeros(6, dtype=np.float32)

        thread = Thread(target=self._run_thread,
                        args=(telemetryServerSocket, motorClientSocket))

        thread.start()

        return True

    def disconnect(self):

        self.connected = False

    def step(self):

        return self.sticks, self.pose

    def _run_thread(self, telemetryServerSocket, motorClientSocket):

        running = False

        while True:

            try:
                telemetry_bytes, _ = telemetryServerSocket.recvfrom(8*17)
            except Exception:
                self.done = True
                break

            telemetryServerSocket.settimeout(.1)

            telemetry = np.frombuffer(telemetry_bytes)

            if not running:
                _debug('Running')
                running = True

            if telemetry[0] < 0:
                self.done = True
                break

            self.pose[0] = telemetry[1]
            self.pose[1] = telemetry[3]
            self.pose[2] = telemetry[5]
            self.pose[3] = telemetry[7]
            self.pose[4] = telemetry[9]
            self.pose[5] = telemetry[11]

            self.sticks[0] = telemetry[13]
            self.sticks[1] = telemetry[14]
            self.sticks[1] = telemetry[15]
            self.sticks[3] = telemetry[16]

            motorvals = 0, 0, 0, 0  # XXX

            motorClientSocket.sendto(
                    np.ndarray.tobytes(np.ndarray.astype(motorvals, np.float32)),
                    (self.host, self.motor_port))

            sleep(0)  # yield to other thread

    def _make_udpsocket(self):

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

        return sock    

    def _debug(self, msg):

        print(msg)
        stdout.flush()
