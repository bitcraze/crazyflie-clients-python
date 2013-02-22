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
The console tab is used as a console for printouts from the Crazyflie.
"""

__author__ = 'Bitcraze AB'
__all__ = ['ConsoleTab']

import sys, time

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import pyqtSlot, pyqtSignal

from ui.tab import Tab

console_tab_class = uic.loadUiType("ui/tabs/consoleTab.ui")[0]

class ConsoleTab(Tab, console_tab_class):
    """Console tab for showing printouts from Crazyflie"""
    update = pyqtSignal(str)
    
    def __init__(self, tabWidget, helper, *args):
        super(ConsoleTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Console"
        self.menuName = "Console"

        self.tabWidget = tabWidget
        self.helper = helper
        
        self.update.connect(self.console.insertPlainText)
        
        self.helper.cf.console.receivedChar.addCallback(self.update.emit)

