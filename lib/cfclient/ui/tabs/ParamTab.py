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

import sys
from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL
from PyQt4.QtCore import QAbstractItemModel, QModelIndex, QString, QVariant
from PyQt4.QtGui import QApplication, QStyledItemDelegate, QAbstractItemView, QBrush, QColor
from PyQt4.QtGui import QSortFilterProxyModel

from cfclient.ui.tab import Tab

param_tab_class = uic.loadUiType(sys.path[0] +
                                 "/cfclient/ui/tabs/paramTab.ui")[0]

import logging
logger = logging.getLogger(__name__)

class ParamChildItem(object):
    """Represents a leaf-node in the tree-view (one parameter)"""
    def __init__(self, parent, name, crazyflie):
        """Initialize the node"""
        self.parent = parent
        self.name = name
        self.ctype = None
        self.access = None
        self.value = ""
        self._cf = crazyflie
        self.is_updating = True

    def updated(self, name, value):
        """Callback from the param layer when a parameter has been updated"""
        self.value = value
        self.is_updating = False
        self.parent.model.refresh()

    def set_value(self, value):
        """Send the update value to the Crazyflie. It will automatically be
        read again after sending and then the updated callback will be
        called"""
        complete_name = "%s.%s" % (self.parent.name, self.name)
        self._cf.param.set_value(complete_name, value)
        self.is_updating = True

    def child_count(self):
        """Return the number of children this node has"""
        return 0


class ParamGroupItem(object):
    """Represents a parameter group in the tree-view"""
    def __init__(self, name, model):
        """Initialize the parent node"""
        super(ParamGroupItem, self).__init__()
        self.parent = None
        self.children = []
        self.name = name
        self.model = model

    def child_count(self):
        """Return the number of children this node has"""
        return len(self.children)

class ParamBlockModel(QAbstractItemModel):
    """Model for handling the parameters in the tree-view"""
    def __init__(self, parent):
        """Create the empty model"""
        super(ParamBlockModel, self).__init__(parent)
        self._nodes = []
        self._column_headers = ['Name', 'Type', 'Access', 'Value']
        self._red_brush = QBrush(QColor("red"))

    def set_toc(self, toc, crazyflie):
        """Populate the model with data from the param TOC"""

        # No luck using proxy sorting, so do it here instead...
        for group in sorted(toc.keys()):
            new_group = ParamGroupItem(group, self)
            for param in sorted(toc[group].keys()):
                new_param = ParamChildItem(new_group, param, crazyflie)
                new_param.ctype = toc[group][param].ctype
                new_param.access = toc[group][param].get_readable_access()
                crazyflie.param.add_update_callback(
                    group=group, name=param, cb=new_param.updated)
                new_group.children.append(new_param)
            self._nodes.append(new_group)

        # Request updates for all of the parameters
        for group in self._nodes:
            for param in group.children:
                complete_name = "%s.%s" % (group.name, param.name)
                crazyflie.param.request_param_update(complete_name)

        self.layoutChanged.emit()

    def refresh(self):
        """Force a refresh of the view though the model"""
        self.layoutChanged.emit()

    def parent(self, index):
        """Re-implemented method to get the parent of the given index"""
        if not index.isValid():
            return QModelIndex()

        node = index.internalPointer()
        if node.parent is None:
            return QModelIndex()
        else:
            return self.createIndex(self._nodes.index(node.parent), 0,
                                    node.parent)

    def columnCount(self, parent):
        """Re-implemented method to get the number of columns"""
        return len(self._column_headers)

    def headerData(self, section, orientation, role):
        """Re-implemented method to get the headers"""
        if role == Qt.DisplayRole:
            return QString(self._column_headers[section])

    def rowCount(self, parent):
        """Re-implemented method to get the number of rows for a given index"""
        parent_item = parent.internalPointer()
        if parent.isValid():
            parent_item = parent.internalPointer()
            return parent_item.child_count()
        else:
            return len(self._nodes)

    def index(self, row, column, parent):
        """Re-implemented method to get the index for a specified
        row/column/parent combination"""
        if not self._nodes:
            return QModelIndex()
        node = parent.internalPointer()
        if not node:
            index = self.createIndex(row, column, self._nodes[row])
            self._nodes[row].index = index
            return index
        else:
            return self.createIndex(row, column, node.children[row])

    def data(self, index, role):
        """Re-implemented method to get the data for a given index and role"""
        node = index.internalPointer()
        parent = node.parent
        if not parent:
            if role == Qt.DisplayRole and index.column() == 0:
                return node.name
        elif role == Qt.DisplayRole:
            if index.column() == 0:
                return node.name
            if index.column() == 1:
                return node.ctype
            if index.column() == 2:
                return node.access
            if index.column() == 3:
                return node.value
        elif role == Qt.EditRole and index.column() == 3:
            return node.value
        elif (role == Qt.BackgroundRole and index.column() == 3
                and node.is_updating):
            return self._red_brush

        return QVariant()

    def setData(self, index, value, role):
        """Re-implemented function called when a value has been edited"""
        node = index.internalPointer()
        if role == Qt.EditRole:
            new_val = str(value.toString())
            # This will not update the value, only trigger a setting and
            # reading of the parameter from the Crazyflie
            node.set_value(new_val)
            return True
        return False


    def flags(self, index):
        """Re-implemented function for getting the flags for a certain index"""
        flag = super(ParamBlockModel, self).flags(index)
        node = index.internalPointer()
        if index.column() == 3 and node.parent and node.access=="RW":
            flag |= Qt.ItemIsEditable
        return flag


    def reset(self):
        """Reset the model"""
        self._nodes = []
        self.layoutChanged.emit()


class ParamTab(Tab, param_tab_class):
    """
    Show all the parameters in the TOC and give the user the ability to edit
    them
    """
    _expand_all_signal = pyqtSignal()
    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        """Create the parameter tab"""
        super(ParamTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Parameters"
        self.menuName = "Parameters"

        self.helper = helper
        self.tabWidget = tabWidget
        self.cf = helper.cf

        self.cf.connectSetupFinished.add_callback(self._connected_signal.emit)
        self._connected_signal.connect(self._connected)
        self.cf.disconnected.add_callback(self._disconnected_signal.emit)
        self._disconnected_signal.connect(self._disconnected)

        self._model = ParamBlockModel(None)
        self.paramTree.setModel(self._model)

    def _connected(self, link_uri):
        self._model.set_toc(self.cf.param.toc.toc, self.helper.cf)
        self.paramTree.expandAll()

    def _disconnected(self, link_uri):
        self._model.reset()
