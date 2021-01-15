#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2021 Bitcraze AB
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
Shows information from the Python logging framework
"""

import logging

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal

import cfclient
from cfclient.ui.tab import Tab

__author__ = 'Bitcraze AB'
__all__ = ['LogClientTab']

logger = logging.getLogger(__name__)

log_client_tab_class = uic.loadUiType(cfclient.module_path +
                                      "/ui/tabs/logClientTab.ui")[0]


class LogClientTab(Tab, log_client_tab_class, logging.StreamHandler):
    """
    A tab for showing client logging information, such
    as USB Gamepad connections or scan feedback.
    """
    _update = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(LogClientTab, self).__init__(*args)
        logging.StreamHandler.__init__(self)
        self.setupUi(self)

        self.tabName = "Log Client"
        self.menuName = "Log Client"

        self.tabWidget = tabWidget

        self._update.connect(self.printText)
        self._clearButton.clicked.connect(self.clear)
        #
        # We inherit from logging.StreamHandler and add ourself to the root
        # logger. This means that our implementation of emit() will be called
        # when a new LogRecord object is available on the stream.
        #
        cflogger = logging.getLogger(None)
        cflogger.addHandler(self)

    def emit(self, record):
        fmt = '%(levelname)s:%(name)s:%(message)s'
        formatter = logging.Formatter(fmt)
        #
        # Calling .emit() on the _update signal will make the callback
        # we registered in __init__ run.
        #
        self._update.emit(formatter.format(record))

    def printText(self, text):
        logger.debug("[%s]", text)
        self.syslog.insertPlainText(text + '\n')

    def clear(self):
        self.syslog.clear()
