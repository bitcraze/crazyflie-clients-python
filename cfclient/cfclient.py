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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
The main file for the Crazyflie control application.
"""

__author__ = 'Bitcraze AB'
__all__ = ['']

import sys, os

# Put the lib in the path
sys.path.append("..")

# Try all the imports used in the project here to control what happens....
try:
  import usb
except:
  print "No pyusb installation found, exiting!"
  sys.exit(1)

try:
  import pygame
except:
  print "No pygame installation found, exiting!"
  sys.exit(1)

try:
  import PyQt4
except:
  print "No PyQT4 installation found, exiting!"
  sys.exit(1)

import logging

# Set ERROR level for PyQt4 logger
qtlogger = logging.getLogger('PyQt4')
qtlogger.setLevel(logging.ERROR)

# Set DEBUG level for the rest of the loggers
logging.basicConfig(level=logging.INFO)

# Disable printouts from STL
if os.name=='posix':
    stdout = os.dup(1)
    os.dup2(os.open('/dev/null', os.O_WRONLY), 1)
    sys.stdout = os.fdopen(stdout, 'w')

# Start up the main user-interface
from ui.main import MainUI
from PyQt4.QtGui import QApplication
app = QApplication(sys.argv)
main_window = MainUI()
main_window.show()

sys.exit(app.exec_())

