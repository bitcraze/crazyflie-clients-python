# -*- coding: utf-8 -*-
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
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation, 
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Multiplatform python joystick driver
Back-end currently implemented for linux_udev and pygame
"""

from .constants import TYPE_BUTTON, TYPE_AXIS

# FIXME: there is certainly a cleaner way to do that
# (will quickly be too indented)
try:
    from .linuxjsdev import Joystick
except ImportError:
    try:
        from .pygamejoystick import Joystick
    except ImportError:
        raise Exception("No suitable Joystick driver. \
                         Driver supported: Linux, pygame")

