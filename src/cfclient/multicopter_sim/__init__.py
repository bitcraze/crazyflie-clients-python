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
from threading import Thread
from time import sleep

class MulticopterSimClient:

    def __init__(self, connect_button, host='127.0.0.1', port=5000):

        self.connect_button = connect_button

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

            self.sock.settimeout(0.5)

            self.connect_button.setText('Disconnect')

            self.connected = True

            thread = Thread(target=self._run_thread)

            thread.start()

        except ConnectionRefusedError:

            return False

        return True

    def disconnect(self):

        self.connect_button.setText('Connect')

        self.connected = False

    def _run_thread(self):

        count = 0

        while self.connected:

            print(count)
            count += 1

            try:
                telemetry_bytes = self.sock.recv(8*13)

            except socket.timeout:
                break

            telemetry = np.frombuffer(telemetry_bytes)

            # self._debug(telemetry[0])

            sleep(0)  # yield to main thread

    def _debug(self, msg):

        print(msg)
        stdout.flush()

