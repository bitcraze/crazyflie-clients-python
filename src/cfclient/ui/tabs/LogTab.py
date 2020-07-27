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
Shows the Log TOC of available variables in the Crazyflie.
"""

import cfclient
from cfclient.ui.tab import Tab
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtCore import Qt

__author__ = 'Bitcraze AB'
__all__ = ['LogTab']

param_tab_class = uic.loadUiType(cfclient.module_path +
                                 "/ui/tabs/logTab.ui")[0]


class LogTab(Tab, param_tab_class):
    connectedSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(LogTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Log TOC"
        self.menuName = "Log TOC"

        self.helper = helper
        self.tabWidget = tabWidget

        self.cf = helper.cf

        # Init the tree widget
        self.logTree.setHeaderLabels(['Name', 'ID', 'Unpack', 'Storage'])
        self.logTree.setSortingEnabled(True)
        self.logTree.sortItems(0, Qt.AscendingOrder)

        self.cf.connected.add_callback(self.connectedSignal.emit)
        self.connectedSignal.connect(self.connected)

        # Clear the log TOC list when the Crazyflie is disconnected
        self.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.disconnectedSignal.connect(self.disconnected)

    @pyqtSlot('QString')
    def disconnected(self, linkname):
        self.logTree.clear()

    @pyqtSlot(str)
    def connected(self, linkURI):
        self.logTree.clear()

        toc = self.cf.log.toc

        for group in list(toc.toc.keys()):
            groupItem = QtWidgets.QTreeWidgetItem()
            groupItem.setData(0, Qt.DisplayRole, group)
            for param in list(toc.toc[group].keys()):
                item = QtWidgets.QTreeWidgetItem()
                item.setData(0, Qt.DisplayRole, param)
                item.setData(1, Qt.DisplayRole, toc.toc[group][param].ident)
                item.setData(2, Qt.DisplayRole, toc.toc[group][param].pytype)
                item.setData(3, Qt.DisplayRole, toc.toc[group][param].ctype)
                groupItem.addChild(item)

            self.logTree.addTopLevelItem(groupItem)
