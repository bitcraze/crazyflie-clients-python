#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013 Bitcraze AB
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
Shows all the parameters available in the Crazyflie and also gives the ability
to edit them.
"""

__author__ = 'Bitcraze AB'
__all__ = ['LogBlockTab']

import time
import sys

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

from cfclient.ui.tab import Tab

logblock_tab_class = uic.loadUiType(sys.path[0] +
                                 "/cfclient/ui/tabs/logBlockTab.ui")[0]


class LogBlockTab(Tab, logblock_tab_class):
    """
    Used to show debug-information about logblock status.
    """

    _blocks_updated_signal = pyqtSignal(bool)
    _disconnected_signal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(LogBlockTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "LogBlocks"
        self.menuName = "LogBlocks"

        self._helper = helper
        self.tabWidget = tabWidget

        self._helper.cf.log.block_added_cb.add_callback(self._block_added)
        self._disconnected_signal.connect(self._disconnected)
        self._helper.cf.disconnected.add_callback(self._disconnected_signal.emit)
        self._blocks_updated_signal.connect(self._update_tree)

        self._block_tree.setHeaderLabels(['Id', 'Name', 'Period (ms)', 'Added', 'Started', 'Error', 'Contents'])
        self._block_tree.sortItems(0, QtCore.Qt.AscendingOrder)

    def _block_added(self, block):
        """Callback when a new logblock has been created"""
        block.added_cb.add_callback(self._blocks_updated_signal.emit)
        block.started_cb.add_callback(self._blocks_updated_signal.emit)

    def _update_tree(self):
        """Update the block tree"""
        self._block_tree.clear()
        for block in self._helper.cf.log.log_blocks:
            item = QtGui.QTreeWidgetItem()
            item.setFlags(Qt.ItemIsEnabled |
                          Qt.ItemIsSelectable)
            item.setData(0, Qt.DisplayRole, block.block_id)
            item.setData(1, Qt.EditRole, block.logconf.configName)
            item.setData(2, Qt.DisplayRole, (block.period_in_ms))
            item.setData(3, Qt.DisplayRole, block.added)
            item.setData(4, Qt.EditRole, block.started)
            item.setData(5, Qt.EditRole, block.err_no)
            for var in block.logconf.getVariables():
                subItem = QtGui.QTreeWidgetItem()
                subItem.setFlags(Qt.ItemIsEnabled |
                              Qt.ItemIsSelectable)
                subItem.setData(6, Qt.EditRole, var.getName())
                item.addChild(subItem)                

            self._block_tree.addTopLevelItem(item)
            self._block_tree.expandItem(item)

    def _disconnected(self, link_uri):
        """Callback when the Crazyflie is disconnected"""
        self._block_tree.clear()