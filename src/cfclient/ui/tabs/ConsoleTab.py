#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2026 Bitcraze AB
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

from __future__ import annotations

import logging

from PySide6.QtUiTools import loadUiType
from PySide6.QtGui import QTextCursor

import cfclient
from cfclient.gui import create_task
from cfclient.ui.pluginhelper import PluginHelper
from cfclient.ui.tab_toolbox import TabToolbox
from cflib2 import Crazyflie
from cflib2.error import DisconnectedError

__author__ = "Bitcraze AB"
__all__ = ["ConsoleTab"]

logger = logging.getLogger(__name__)

console_tab_class = loadUiType(cfclient.module_path + "/ui/tabs/consoleTab.ui")[0]


class ConsoleTab(TabToolbox, console_tab_class):
    """Console tab for showing printouts from Crazyflie"""

    def __init__(self, helper: PluginHelper) -> None:
        super(ConsoleTab, self).__init__(helper, "Console")
        self.setupUi(self)

        self._cf = None
        self._console_task = None

        self._clearButton.clicked.connect(self.clear)
        self._dumpSystemLoadButton.clicked.connect(
            lambda: create_task(self._set_param("system.taskDump", 1))
        )
        self._dumpAssertInformation.clicked.connect(
            lambda: create_task(self._set_param("system.assertInfo", 1))
        )
        self._propellerTestButton.clicked.connect(
            lambda: create_task(self._set_param("health.startPropTest", 1))
        )
        self._batteryTestButton.clicked.connect(
            lambda: create_task(self._set_param("health.startBatTest", 1))
        )
        self._storageStatsButton.clicked.connect(
            lambda: create_task(self._set_param("system.storageStats", 1))
        )

        self._set_buttons_enabled(False)

    def connected(self, cf: Crazyflie) -> None:
        self._cf = cf
        self._set_buttons_enabled(True)
        self._console_task = create_task(self._console_loop())

    def disconnected(self) -> None:
        self._cf = None
        if self._console_task is not None:
            self._console_task.cancel()
            self._console_task = None
        self._set_buttons_enabled(False)

    async def _console_loop(self) -> None:
        console = self._cf.console()
        try:
            while True:
                lines = await console.get_lines()
                for line in lines:
                    self._print(line + "\n")
        except DisconnectedError:
            pass

    async def _set_param(self, name: str, value: int) -> None:
        if self._cf is not None:
            try:
                await self._cf.param().set(name, value)
            except DisconnectedError:
                pass

    def _print(self, text: str) -> None:
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

    def clear(self) -> None:
        self.console.clear()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._dumpSystemLoadButton.setEnabled(enabled)
        self._dumpAssertInformation.setEnabled(enabled)
        self._propellerTestButton.setEnabled(enabled)
        self._batteryTestButton.setEnabled(enabled)
        self._storageStatsButton.setEnabled(enabled)
