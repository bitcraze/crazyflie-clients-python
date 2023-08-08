'''
Webots simulator support for Crazyflie Python client

Copyright (C) 2023 Simon D. Levy

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with
this program; if not, write to the Free Software Foundation, Inc., 51
Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
'''

import socket
import threading
import time
import struct

class WebotsConnection:

    TELEMETRY_MESSAGE_SIZE = 4

    def __init__(self, host = '127.0.0.1', port=5000):

        self.host = host
        self.port = port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

        self.is_open = False

        self.pose = 0, 0, 0, 0, 0, 0
        self.sticks = 0, 0, 0, 0
        self.mode = 0

    def start(self):

        try:
            self.sock.connect((self.host, self.port))

        except:
            return False

        self.is_open = True

        threading.Thread(target=self._threadfun).start()

        return True

    def stop(self):

        self.is_open = False
        self.sock.close()

    def isOpen(self):

        return self.is_open

    def getPose(self):

        return self.pose

    def setModeAndSticks(self, mode, sticks):

        self.mode = mode
        self.sticks = sticks

    def _threadfun(self):

        while self.is_open:

            try:

                self.pose = struct.unpack('ffffff', self.sock.recv(24))

                self.sock.send(struct.pack('fffff', 
                    self.mode,
                    self.sticks[0],
                    self.sticks[1],
                    self.sticks[2],
                    self.sticks[3]))

            except:
                pass

            time.sleep(0)

