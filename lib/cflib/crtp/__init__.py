#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
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
Scans and creates communication interfaces.
"""

__author__ = 'Bitcraze AB'
__all__ = []


import logging
logger = logging.getLogger(__name__)

from .radiodriver import RadioDriver
from .udpdriver import UdpDriver
from .serialdriver import SerialDriver
from .debugdriver import DebugDriver
from .exceptions import WrongUriType

drivers = [RadioDriver, SerialDriver, UdpDriver, DebugDriver]
instances = []


def init_drivers():
    """ Initialize all the drivers. """
    for d in drivers:
        try:
            instances.append(d())
        except Exception:
            continue


def scan_interfaces():
    """ Scan all the interfaces for available Crazyflies """
    available = []
    found = []
    for d in instances:
        logger.debug("Scanning: %s", d)
        try:
            found = d.scan_interface()
            available += found
        except Exception:
            raise
            continue
    return available


def get_interfaces_status():
    """Get the status of all the interfaces"""
    status = {}
    for d in instances:
        try:
            status[d.get_name()] = d.get_status()
        except Exception:
            raise
            continue
    return status


def get_link_driver(uri, linkQualityCallback=None, linkErrorCallback=None):
    """ Return the link driver for the given URI """
    for d in instances:
        try:
            d.connect(uri, linkQualityCallback, linkErrorCallback)
            return d
        except WrongUriType:
            continue
