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

class MulticopterSimClient:

    def __init__(self, connect_button, host='127.0.0.1', port=5000):

        self.connect_button = connect_button

        self.host = host
        self.port = port

    def connect(self):

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:

            try:

                sock.connect((self.host, self.port))

                sock.settimeout(0.5)

                self.connect_button.setText('Disconnect')

                thread = Thread(target=self._run_thread, args=(sock,))

                thread.start()

            except ConnectionRefusedError:

                self._debug(
                        'Connection error; did you start the server first?')

    def _run_thread(self, sock):

        self._debug(sock)
        exit(0)

        while True:

            try:
                telemetry_bytes = sock.recv(8*13)

            except socket.timeout:
                break

            telemetry = np.frombuffer(telemetry_bytes)

    def _debug(self, msg):

        print(msg)
        stdout.flush()

