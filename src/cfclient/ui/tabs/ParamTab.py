#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2022 Bitcraze AB
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
Shows all the parameters available in the Crazyflie and also gives the ability
to edit them.
"""

import logging

from PyQt5 import uic, QtCore
from PyQt5.QtCore import QSortFilterProxyModel, Qt, pyqtSignal
from PyQt5.QtCore import QAbstractItemModel, QModelIndex, QVariant
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QHeaderView

from cflib.crazyflie.param import PersistentParamState

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox

__author__ = 'Bitcraze AB'
__all__ = ['ParamTab']

param_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/paramTab.ui")[0]

logger = logging.getLogger(__name__)


def round_if_float(value):
    """If the value is float, we limit to 5 significat numbers"""
    try:
        value = float(value)
        value = f'{value:.5g}'
    except ValueError:
        pass
    return value


class ParamChildItem(object):
    """Represents a leaf-node in the tree-view (one parameter)"""

    def __init__(self, parent, name, persistent, crazyflie):
        """Initialize the node"""
        self.parent = parent
        self.name = name
        self.ctype = None
        self.access = None
        self.persistent = False
        self.value = ""
        self._cf = crazyflie
        self.is_updating = True
        self.state = None

    def updated(self, name, value):
        """Callback from the param layer when a parameter has been updated"""
        self.value = round_if_float(value)
        self.is_updating = False
        self.parent.model.proxy.dataChanged.emit(QModelIndex(), QModelIndex())

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

    def __init__(self, parent, mainUI):
        """Create the empty model"""
        super(ParamBlockModel, self).__init__(parent)
        self._nodes = []
        self._column_headers = ['Name', 'Type', 'Access', 'Persistent', 'Value']
        self._red_brush = QBrush(QColor("red"))
        self._enabled = False
        self._mainUI = mainUI
        self.proxy = None

    def set_proxy(self, proxy):
        self.proxy = proxy

    def set_enabled(self, enabled):
        if self._enabled != enabled:
            self._enabled = enabled
            self.layoutChanged.emit()

    def set_toc(self, toc, crazyflie):
        """Populate the model with data from the param TOC"""

        # No luck using proxy sorting, so do it here instead...
        for group in sorted(toc.keys()):
            new_group = ParamGroupItem(group, self)
            for param in sorted(toc[group].keys()):
                elem = toc[group][param]
                is_persistent = elem.is_persistent()
                new_param = ParamChildItem(new_group, param, is_persistent, crazyflie)
                new_param.ctype = elem.ctype
                new_param.access = elem.get_readable_access()
                new_param.persistent = elem.is_persistent()

                crazyflie.param.add_update_callback(
                    group=group, name=param, cb=new_param.updated)
                new_group.children.append(new_param)
            self._nodes.append(new_group)

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
            return self._column_headers[section]

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

        if role == Qt.BackgroundColorRole:
            if index.row() % 2 == 0:
                return QVariant(self._mainUI.bgColor)
            else:
                multiplier = 1.15 if self._mainUI.isDark else 0.95
                return QVariant(
                    QColor(
                        int(self._mainUI.bgColor.red() * multiplier),
                        int(self._mainUI.bgColor.green() * multiplier),
                        int(self._mainUI.bgColor.blue() * multiplier)
                    )
                )

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
                return 'Yes' if node.persistent else 'No'
            if index.column() == 4:
                return node.value
        elif (role == Qt.BackgroundRole and index.column() == 4 and
              node.is_updating):
            return self._red_brush

        return None

    def flags(self, index):
        """Re-implemented function for getting the flags for a certain index"""
        flag = super(ParamBlockModel, self).flags(index)

        if not self._enabled:
            return Qt.NoItemFlags

        return flag

    def reset(self):
        """Reset the model"""
        super(ParamBlockModel, self).beginResetModel()
        self._nodes = []
        super(ParamBlockModel, self).endResetModel()
        self.layoutChanged.emit()


class ParamTreeFilterProxy(QSortFilterProxyModel):
    """
    Implement a filtering proxy model that show all children if the group matches.
    """
    def __init__(self, paramTree):
        super(ParamTreeFilterProxy, self).__init__(paramTree)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        '''
        When a group match the filter, make sure all children matches as well.
        '''
        if not source_parent.isValid():
            return super().filterAcceptsRow(source_row, source_parent)

        return super().filterAcceptsRow(source_parent.row(), source_parent.parent())


class ParamTab(TabToolbox, param_tab_class):
    """
    Show all the parameters in the TOC and give the user the ability to edit
    them
    """
    _expand_all_signal = pyqtSignal()
    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)

    _set_param_value_signal = pyqtSignal()
    _persistent_state_signal = pyqtSignal(PersistentParamState)
    _param_default_signal = pyqtSignal(object)
    _reset_param_signal = pyqtSignal(str)

    def __init__(self, helper):
        """Create the parameter tab"""
        super(ParamTab, self).__init__(helper, 'Parameters')
        self.setupUi(self)

        self.cf = helper.cf

        self.cf.connected.add_callback(self._connected_signal.emit)
        self._connected_signal.connect(self._connected)
        self.cf.disconnected.add_callback(self._disconnected_signal.emit)
        self._disconnected_signal.connect(self._disconnected)

        self._model = ParamBlockModel(None, self._helper.mainUI)
        self._persistent_state_signal.connect(self._persistent_state_cb)
        self._set_param_value_signal.connect(self._set_param_value)
        self.setParamButton.clicked.connect(self._set_param_value_signal.emit)
        self.currentValue.returnPressed.connect(self._set_param_value_signal.emit)
        self._param_default_signal.connect(self._param_default_cb)

        self._reset_param_signal.connect(lambda text: self.currentValue.setText(text))
        self.resetDefaultButton.clicked.connect(lambda: self._reset_param_signal.emit(self.defaultValue.text()))
        self.persistentButton.clicked.connect(self._persistent_button_cb)

        self.proxyModel = ParamTreeFilterProxy(self.paramTree)
        self.proxyModel.setSourceModel(self._model)
        self.proxyModel.setRecursiveFilteringEnabled(True)
        self._model.set_proxy(self.proxyModel)

        @QtCore.pyqtSlot(str)
        def onFilterChanged(text):
            self.proxyModel.setFilterRegExp(text)

        self.filterBox.textChanged.connect(onFilterChanged)

        self.paramTree.setModel(self.proxyModel)
        self.paramTree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.paramTree.selectionModel().selectionChanged.connect(self._paramChanged)

    def _param_default_cb(self, default_value):
        if default_value is not None:
            self.defaultValue.setText(str(default_value))
        else:
            self.defaultValue.setText('-')

    def _persistent_button_cb(self, _):
        def success_cb(name, success):
            print(f'store {success}!')
            if success:
                self.cf.param.persistent_get_state(name, lambda _, state: self._persistent_state_signal.emit(state))

        complete = self.paramDetailsLabel.text()
        if self.persistentButton.text() == 'Clear':
            self.cf.param.persistent_clear(complete, success_cb)
        else:
            self.cf.param.persistent_store(complete, success_cb)

    def _persistent_state_cb(self, state):
        print(f'persistent callback! state: {state}')
        self.persistentFrame.setVisible(True)

        if state.is_stored:
            self.storedValue.setText(str(state.stored_value))
        else:
            self.storedValue.setText('Not stored')

        self.persistentButton.setText('Clear' if state.is_stored else 'Store')

    def _set_param_value(self):
        name = self.paramDetailsLabel.text()
        value = self.currentValue.text()
        try:
            self.cf.param.set_value(name, value)
            self.currentValue.setStyleSheet('')
        except Exception:
            self.currentValue.setStyleSheet('border: 1px solid red')

    def _paramChanged(self):
        indexes = self.paramTree.selectionModel().selectedIndexes()
        selectedIndex = indexes[0]

        self.persistentFrame.setVisible(False)

        param = None
        if selectedIndex.parent().isValid():
            group = selectedIndex.parent().data()
            param = selectedIndex.data()
        else:
            group = selectedIndex.data()

        self.paramDetailsLabel.setText(f'{group}.{param}' if param is not None else group)
        if cfclient.log_param_doc is not None:
            try:
                desc = str()
                group_doc = cfclient.log_param_doc['params'][group]
                if param is None:
                    desc = group_doc['desc']
                else:
                    desc = group_doc['variables'][param]['short_desc']

                self.paramDetailsDescription.setWordWrap(True)
                self.paramDetailsDescription.setText(desc.replace('\n', ''))
            except:  # noqa
                self.paramDetailsDescription.setText('')

        self.valueFrame.setVisible(param is not None)
        if param:
            complete = f'{group}.{param}'
            elem = self.cf.param.toc.get_element_by_complete_name(complete)
            value = round_if_float(self.cf.param.get_value(complete))
            self.currentValue.setText(value)
            self.currentValue.setStyleSheet('')
            self.currentValue.setCursorPosition(0)
            self.defaultValue.setText('-')
            self.cf.param.get_default_value(complete, lambda _, value: self._param_default_signal.emit(value))

            writable = elem.get_readable_access() == 'RW'
            self.currentValue.setEnabled(writable)
            self.setParamButton.setEnabled(writable)
            self.resetDefaultButton.setEnabled(writable)

            if elem.is_persistent():
                self.cf.param.persistent_get_state(complete, lambda _, state: self._persistent_state_signal.emit(state))

    def _connected(self, link_uri):
        self._model.reset()
        self._model.set_toc(self.cf.param.toc.toc, self._helper.cf)
        self._model.set_enabled(True)
        self._helper.cf.param.request_update_of_all_params()

    def _disconnected(self, link_uri):
        #
        # This will gray out all rows
        #
        self._model.set_enabled(False)
