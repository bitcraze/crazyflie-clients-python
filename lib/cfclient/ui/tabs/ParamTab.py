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
Shows all the parameters available in the Crazyflie and also gives the ability
to edit them.
"""

__author__ = 'Bitcraze AB'
__all__ = ['ParamTab']

import time
import sys

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

from cfclient.ui.tab import Tab

param_tab_class = uic.loadUiType(sys.path[0] +
                                 "/cfclient/ui/tabs/paramTab.ui")[0]


class ParamTab(Tab, param_tab_class):
    """
    Show all the parameters in the TOC and give the user the ability to edit
    them
    """
    paramUpdatedSignal = pyqtSignal(str, str)
    connectionDoneSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(ParamTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Parameters"
        self.menuName = "Parameters"

        self.helper = helper
        self.tabWidget = tabWidget

        self.cf = helper.cf

        self.cf.connectSetupFinished.add_callback(
                                              self.connectionDoneSignal.emit)
        self.connectionDoneSignal.connect(self.connectionDone)

        # Clear the log TOC list when the Crazyflie is disconnected
        self.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.disconnectedSignal.connect(self.disconnected)

        self.paramUpdatedSignal.connect(self.paramUpdated)
        self.paramTree.setHeaderLabels(['Name', 'Type', 'Access', 'Value'])
        self.paramTree.sortItems(0, QtCore.Qt.AscendingOrder)

        self.sendUpdatedValues.clicked.connect(self.sendAllValues)

        self.editItems = {}

    def paramUpdatedWrapper(self, name, value):
        # The reason for this wrapper (and not using emit directly for the
        # callback) is that for some reason every time we get connectionDone
        # and register the callbacks the self.paramUpdatedSignal.emit is on a
        # different address which throws off the duplicate checking in Caller
        # and this results in the number of callbacks per connect growing by
        # one...
        self.paramUpdatedSignal.emit(name, value)

    def connectionDone(self, linkURI):
        self.paramTree.clear()
        self.editItems = {}

        toc = self.cf.param.toc.toc
        for group in toc.keys():
            groupItem = QtGui.QTreeWidgetItem()
            groupItem.setData(0, Qt.DisplayRole, group)
            for param in toc[group].keys():
                item = QtGui.QTreeWidgetItem()
                item.setFlags(Qt.ItemIsEnabled |
                              Qt.ItemIsEditable |
                              Qt.ItemIsSelectable)
                item.setData(0, Qt.DisplayRole, param)
                item.setData(1, Qt.DisplayRole, toc[group][param].ctype)
                item.setData(2, Qt.DisplayRole,
                                toc[group][param].get_readable_access())
                item.setData(3, Qt.EditRole, "N/A")
                completeName = "%s.%s" % (group, param)
                self.editItems[completeName] = item
                groupItem.addChild(item)
                # Request update for this parameter value
                self.cf.param.add_update_callback(group=group, name=param,
                                                  cb=self.paramUpdatedWrapper)
                self.cf.param.request_param_update(completeName)

            self.paramTree.addTopLevelItem(groupItem)
            self.paramTree.expandItem(groupItem)

    def paramUpdated(self, completeName, value):
        self.editItems[str(completeName)].setData(3, Qt.EditRole, value)

    def sendAllValues(self):
        # TODO: Use send button for now since we need to detect if it's an edit
        # update or an update through a callback if the calue is updated and we
        # connect to dataChanged signal on tree
        for key in self.editItems.keys():
            item = self.editItems[key]
            self.helper.cf.param.set_value(key, str(item.text(3)))

    @pyqtSlot(str)
    def disconnected(self, linkname):
        self.paramTree.clear()
