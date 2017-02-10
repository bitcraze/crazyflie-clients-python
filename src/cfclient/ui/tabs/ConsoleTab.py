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
The console tab is used as a console for printouts from the Crazyflie.
"""

import logging

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal

import cfclient
from cfclient.ui.tab import Tab

__author__ = 'Bitcraze AB'
__all__ = ['ConsoleTab']

logger = logging.getLogger(__name__)

console_tab_class = uic.loadUiType(cfclient.module_path +
                                   "/ui/tabs/consoleTab.ui")[0]


class ConsoleTab(Tab, console_tab_class):
    """Console tab for showing printouts from Crazyflie"""
    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _update = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(ConsoleTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Console"
        self.menuName = "Console"

        self.tabWidget = tabWidget
        self._helper = helper

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._update.connect(self.printText)

        self._helper.cf.console.receivedChar.add_callback(self._update.emit)
        self._helper.cf.connected.add_callback(self._connected_signal.emit)
        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._clearButton.clicked.connect(self.clear)
        self._dumpSystemLoadButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("system.taskDump", '1'))

    def printText(self, text):
        # Make sure we get printouts from the Crazyflie into the log (such as
        # build version and test ok/fail)
        logger.debug("[%s]", text)
        self.console.insertPlainText(text)

    def clear(self):
        self.console.clear()

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        self._dumpSystemLoadButton.setEnabled(True)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        self._dumpSystemLoadButton.setEnabled(False)
