#  Copyright (C) 2023 Simon D. Levy
#
#  MulticopterSim client for Crazyflie client GUI
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


class MulticopterSimClient:

    def __init__(self, host='127.0.0.1', port=5000):

        self.connected = False

        self.sock = None

        self.host = host
        self.port = port

        self.pose = None
        self.sticks = None

    def connect(self):
        '''
        Returns True on success, False on failure
        '''

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:

            self.sock.connect((self.host, self.port))

        except ConnectionRefusedError:

            return False

        self.sock.settimeout(0.5)

        self.connected = True

        return True

    def disconnect(self):

        self.connected = False

    def getPose(self):

        return tuple(self.pose)

    def setSticks(self, values):

        self.sticks = values

    def step(self, sticks):

        self._debug(sticks)

        if self.connected:

            try:
                pose_bytes = self.sock.recv(8*6)

                '''
                self._debug('%3.3f  %3.3f  %3.3f  %3.3f' % (
                    self.sticks[0],
                    self.sticks[1],
                    self.sticks[2],
                    self.sticks[3]))

                '''
            except socket.timeout:

                return None

            return np.frombuffer(pose_bytes)

        return None

    def _debug(self, msg):

        print(msg)
        stdout.flush()
