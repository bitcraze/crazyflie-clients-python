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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
This tab shows all log blocks that are registered and can be used to start the
logging and also to write the logging data to file.
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

import logging
logger = logging.getLogger(__name__)

from PyQt4.QtGui import QApplication, QStyledItemDelegate, QAbstractItemView
from PyQt4.QtGui import QStyleOptionButton, QStyle
from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import pyqtSlot, pyqtSignal, QThread
from PyQt4.QtCore import QAbstractItemModel, QModelIndex, QString, QVariant

from cfclient.utils.logdatawriter import LogWriter


class LogBlockChildItem(object):
    """Class that acts as a child in the tree and represents one variable in
    a log block"""
    def __init__(self, parent, name):
        """Initialize the node"""
        self.parent = parent
        self.name = name

    def child_count(self):
        """Return the number of children this node has"""
        return 0


class LogBlockItem(object):
    """Class that acts as a parent in the tree view and represents a complete
    log block"""

    def __init__(self, block, model):
        """Initialize the parent node"""
        super(LogBlockItem, self).__init__()
        self._block = block
        self.parent = None
        self.children = []
        self.name = block.name
        self.id = block.block_id
        self.period = block.period_in_ms
        self._model = model
        self._log_file_writer = LogWriter(block)

        self._block.started_cb.add_callback(self._set_started)
        self._block.added_cb.add_callback(self._set_added)
        self._block.error.add_callback(self._log_error)

        self._var_list = ""

        for b in block.variables:
            self.children.append(LogBlockChildItem(self, b.name))
            self._var_list += "%s/" % b.name
        self._var_list = self._var_list[:-1]

        self._block_started = False
        self._doing_transaction = False

    def _log_error(self, logconfig, msg):
        """Callback when there's an error starting the block in the Crazyflie"""
        # Do nothing here, a pop-up will notify the user that the
        # starting failed
        self._doing_transaction = False

    def _set_started(self, started):
        """Callback when a block has been started in the Crazyflie"""
        logger.info("%s started: %s", self.name, started)
        if started:
             self._block_started = True
        else:
             self._block_started = False
        self._doing_transaction = False
        self._model.refresh()

    def logging_started(self):
        """Return True if the block has been started, otherwise False"""
        return self._block_started

    def writing_to_file(self):
        """Return True if the block is being logged to file, otherwise False"""
        return self._log_file_writer.writing()

    def start_writing_to_file(self):
        """Start logging to file for this block"""
        self._log_file_writer.start()

    def stop_writing_to_file(self):
        """Stop logging to file for this block"""
        self._log_file_writer.stop()

    def start(self):
        """Start the logging of this block"""
        self._doing_transaction = True
        self._block.start()

    def stop(self):
        """Stop the logging of this block"""
        self._doing_transaction = True
        self._block.stop()

    def doing_transaction(self):
        """Return True if a block is being added or started, False when it's
        been added/started/failed"""
        return self._doing_transaction

    def _set_added(self, started):
        """Callback when a block has been added to the Crazyflie"""
        logger.info("%s added: %s", self.name, started)

    def var_list(self):
        """Return a string containing all the variable names of the children"""
        return self._var_list

    def child_count(self):
        """Return the number of children this node has"""
        return len(self.children)

    def get_child(self, index):
        return self.children[index]


class LogBlockModel(QAbstractItemModel):
    def __init__(self, view, parent=None):
        super(LogBlockModel, self).__init__(parent)
        self._nodes = []
        self._column_headers = ['Id', 'Name', 'Period (ms)', 'Start',
                                'Write to file', 'Contents']
        self._view = view

    def add_block(self, block):
        self._nodes.append(LogBlockItem(block, self))
        self.layoutChanged.emit()

    def refresh(self):
        """Force a refresh of the view though the model"""
        self.layoutChanged.emit()

    def clicked(self, index):
        """Callback when a cell has been clicked (mouse down/up on same cell)"""
        node = index.internalPointer()
        if not node.parent and index.column() == 3:
            if node.logging_started():
                node.stop()
            else:
                node.start()
        if not node.parent and index.column() == 4:
            if node.writing_to_file():
                node.stop_writing_to_file()
            else:
                node.start_writing_to_file()
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

    def remove_block(self, block):
        """Remove a block from the view"""
        raise NotImplementedError()

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
            return self.createIndex(row, column, node.get_child(row))

    def data(self, index, role):
        """Re-implemented method to get the data for a given index and role"""
        node = index.internalPointer()
        parent = node.parent
        if parent:
            if role == Qt.DisplayRole and index.column() == 5:
                return node.name
        elif not parent and role == Qt.DisplayRole and index.column() == 5:
            return node.var_list()
        elif not parent and role == Qt.DisplayRole:
            if index.column() == 0:
                return node.id
            if index.column() == 1:
                return node.name
            if index.column() == 2:
                return str(node.period)
        if role == Qt.TextAlignmentRole and \
                (index.column() == 4 or index.column() == 3):
            return Qt.AlignHCenter | Qt.AlignVCenter

        return QVariant()

    def reset(self):
        """Reset the model"""
        self._nodes = []
        self.layoutChanged.emit()


class CheckboxDelegate(QStyledItemDelegate):
    """Custom delegate for rending checkboxes in the table"""

    def paint(self, painter, option, index):
        """Re-implemented paint method"""
        item = index.internalPointer()
        col = index.column()
        if not item.parent and (col == 3 or col == 4):
            s = QStyleOptionButton()
            checkbox_rect = QApplication.style().\
                subElementRect(QStyle.SE_CheckBoxIndicator, option)
            s.rect = option.rect
            center_offset = s.rect.width() / 2 - checkbox_rect.width() / 2
            s.rect.adjust(center_offset, 0, 0, 0)

            if col == 3:
                if not item.doing_transaction():
                    s.state = QStyle.State_Enabled
                if item.logging_started():
                    s.state |= QStyle.State_On

            if col == 4:
                s.state = QStyle.State_Enabled
                if item.writing_to_file():
                    s.state |= QStyle.State_On

            QApplication.style().drawControl(
                QStyle.CE_CheckBox, s, painter)

        else:
            super(CheckboxDelegate, self).paint(painter, option, index)


class LogBlockTab(Tab, logblock_tab_class):
    """
    Used to show debug-information about logblock status.
    """

    _blocks_updated_signal = pyqtSignal(bool)
    _disconnected_signal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        """Initialize the tab"""
        super(LogBlockTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Log Blocks"
        self.menuName = "Log Blocks"

        self._helper = helper
        self.tabWidget = tabWidget

        self._helper.cf.log.block_added_cb.add_callback(self._block_added)
        self._disconnected_signal.connect(self._disconnected)
        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._model = LogBlockModel(self._block_tree)
        self._block_tree.setModel(self._model)
        self._block_tree.clicked.connect(self._model.clicked)
        self._block_tree.setItemDelegate(CheckboxDelegate())
        self._block_tree.setSelectionMode(QAbstractItemView.NoSelection)

    def _block_added(self, block):
        """Callback from logging layer when a new block is added"""
        self._model.add_block(block)

    def _disconnected(self, link_uri):
        """Callback when the Crazyflie is disconnected"""
        self._model.reset()