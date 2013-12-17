#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013 Bitcraze AB
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
Used to write log data to files.
"""

__author__ = 'Bitcraze AB'
__all__ = ['LogWriter']

import os
import sys

import logging

logger = logging.getLogger(__name__)

from cflib.crazyflie.log import LogConfig

import traceback


class LogWriter():
    """Create a writer for a specific log block"""

    def __init__(self, logblock, connect_time=None, directory=None):
        """Initialize the writer"""
        self._block = logblock
        self._dir = directory

        dir = os.path.join(sys.path[1], "logdata")
        self._filename = os.path.join(dir, logblock.name)
        if not os.path.isdir(dir):
            os.makedirs(dir)

        self._file = None
        self._header_written = False

    def _write_header(self):
        """Write the header to the file"""
        if not self._header_written:
            s = "Timestamp"
            for v in self._block.variables:
                s += "," + v.name
            s += '\n'
            self._file.write(s)
            self._header_written = True

    def _new_data(self, data, timestamp):
        """Callback when new data arrives from the Crazyflie"""
        if self._file:
            s = "%d" % timestamp
            for d in data:
                s += "," + str(data[d])
            s += '\n'
            self._file.write(s)

    def writing(self):
        """Return True if the file is open and we are using it,
        otherwise false"""
        return True if self._file else False

    def stop(self):
        """Stop the logging to file"""
        if self._file:
            self._file.close()
            self._file = None
            self._block.data_received.remove_callback(self._new_data)
            logger.info("Stopped logging of block [%s] to file [%s]",
                        self._block.name, self._filename)

    def start(self):
        """Start the logging to file"""
        if not self._file:
            self._file = open(self._filename, 'w')
            self._write_header()
            self._block.data_received.add_callback(self._new_data)
            logger.info("Started logging of block [%s] to file [%s]",
                        self._block.name, self._filename)