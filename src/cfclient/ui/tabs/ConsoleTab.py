#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2023 Bitcraze AB
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

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QTextCursor

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox

__author__ = 'Bitcraze AB'
__all__ = ['ConsoleTab']

logger = logging.getLogger(__name__)

console_tab_class = uic.loadUiType(cfclient.module_path +
                                   "/ui/tabs/consoleTab.ui")[0]


class ConsoleTab(TabToolbox, console_tab_class):
    """Console tab for showing printouts from Crazyflie"""
    _link_established_signal = pyqtSignal(str)
    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _update = pyqtSignal(str)

    def __init__(self, helper):
        super(ConsoleTab, self).__init__(helper, 'Console')
        self.setupUi(self)

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._link_established_signal.connect(self._link_established)
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._update.connect(self.printText)

        self._helper.cf.console.receivedChar.add_callback(self._update.emit)
        self._helper.cf.connected.add_callback(self._connected_signal.emit)
        self._helper.cf.link_established.add_callback(self._link_established_signal.emit)
        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._clearButton.clicked.connect(self.clear)
        self._dumpSystemLoadButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("system.taskDump", '1'))
        self._dumpAssertInformation.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value_raw("system.assertInfo", 0x08, 1))
        self._propellerTestButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("health.startPropTest", '1'))
        self._batteryTestButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("health.startBatTest", '1'))
        self._storageStatsButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("system.storageStats", '1'))

    def printText(self, text):
        # Make sure we get printouts from the Crazyflie into the log (such as
        # build version and test ok/fail)
        logger.debug("[%s]", text)
        scrollbar = self.console.verticalScrollBar()
        prev_scroll = scrollbar.value()
        prev_cursor = self.console.textCursor()
        was_maximum = prev_scroll == scrollbar.maximum()

        self.console.moveCursor(QTextCursor.MoveOperation.End)
        self.console.insertPlainText(text)

        self.console.setTextCursor(prev_cursor)

        if was_maximum and not prev_cursor.hasSelection():
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(prev_scroll)

    def clear(self):
        self.console.clear()

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        self._dumpSystemLoadButton.setEnabled(True)
        self._propellerTestButton.setEnabled(True)
        self._batteryTestButton.setEnabled(True)
        self._storageStatsButton.setEnabled(True)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        self._dumpSystemLoadButton.setEnabled(False)
        self._dumpAssertInformation.setEnabled(False)
        self._propellerTestButton.setEnabled(False)
        self._batteryTestButton.setEnabled(False)
        self._storageStatsButton.setEnabled(False)

    def _link_established(self, link_uri):
        """Callback when the first packet on a new link is received"""
        # Enable the assert dump button as early as possible. After an assert we will never get the connected() cb.
        self._dumpAssertInformation.setEnabled(True)
