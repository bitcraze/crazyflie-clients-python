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
#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
A detachable toolbox for showing console printouts from the Crazyflie
"""
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import Qt

import cfclient

__author__ = 'Bitcraze AB'
__all__ = ['ConsoleToolbox']

console_class = uic.loadUiType(
    cfclient.module_path + "/ui/toolboxes/consoleToolbox.ui")[0]


class ConsoleToolbox(QtWidgets.QWidget, console_class):
    """Console toolbox for showing printouts from the Crazyflie"""
    update = pyqtSignal(str)

    def __init__(self, helper, *args):
        super(ConsoleToolbox, self).__init__(*args)
        self.setupUi(self)

        self.update.connect(self.console.insertPlainText)

        self.helper = helper

    def getName(self):
        return 'Console'

    def _console_updated(self, data):
        self.update.emit(data)

    def enable(self):
        self.helper.cf.console.receivedChar.add_callback(self._console_updated)

    def disable(self):
        self.helper.cf.console.receivedChar.remove_callback(
            self._console_updated)

    def preferedDockArea(self):
        return Qt.BottomDockWidgetArea
