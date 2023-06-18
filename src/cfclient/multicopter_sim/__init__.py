#
#  MulticopterSim client for Crazyflie client GUI
#  
#  Uses a TCP socket to accept vehicle pose and send back stick demands

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


class MulticopterSimClient:

    def __init__(self, host='127.0.0.1', port=5000):

        self.connected = False

        self.sock = None

        self.host = host
        self.port = port

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

        self.fakepose = np.zeros(6, dtype=np.float32)

        return True

    def disconnect(self):

        self.connected = False

    def getSticks(self):

        return (1, 2, 3, 4, 5, 6)

    def step(self):

        if self.connected:

            stick_bytes = None

            try:

                # Get stick demands from server as six floats
                stick_bytes = self.sock.recv(6*4)

                # XXX run dynamics and flight control to get pose
                self.fakepose[2] += .001

                self.sock.send(np.ndarray.tobytes(self.fakepose))

            except socket.timeout:

                return None

            except Exception as e:

                self._debug('*************** EXEPTION: ' + str(e))

                exit(0)

            sticks = (10, 20, 30, 60)  # r, p, y, t
            return sticks, self.fakepose

            # return np.frombuffer(pose_bytes)

        return None

    def _debug(self, msg):

        print(msg)
        stdout.flush()
