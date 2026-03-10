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
Shows all the parameters available in the Crazyflie and also gives the ability
to edit them.
"""

import logging
from collections import defaultdict

from PySide6 import QtCore
from PySide6.QtUiTools import loadUiType
from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtCore import QAbstractItemModel, QModelIndex
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QHeaderView, QMessageBox

import cfclient
from cfclient.gui import create_task
from cfclient.ui.tab_toolbox import TabToolbox

__author__ = "Bitcraze AB"
__all__ = ["ParamTab"]

param_tab_class = loadUiType(cfclient.module_path + "/ui/tabs/paramTab.ui")[0]

logger = logging.getLogger(__name__)


def round_if_float(value):
    """If the value is float, we limit to 5 significant numbers"""
    try:
        value = float(value)
        value = f"{value:.5g}"
    except (ValueError, TypeError):
        pass
    return value


class ParamChildItem:
    """Represents a leaf-node in the tree-view (one parameter)"""

    def __init__(self, parent, name):
        self.parent = parent
        self.name = name
        self.ctype = None
        self.writable = False
        self.persistent = False
        self.value = ""
        self.is_updating = True
        self.stored_value = ""

    def child_count(self):
        return 0


class ParamGroupItem:
    """Represents a parameter group in the tree-view"""

    def __init__(self, name, model):
        super().__init__()
        self.parent = None
        self.children = []
        self.name = name
        self.model = model

    def child_count(self):
        return len(self.children)


class ParamBlockModel(QAbstractItemModel):
    """Model for handling the parameters in the tree-view"""

    def __init__(self, parent, mainUI):
        super().__init__(parent)
        self._nodes = []
        self._column_headers = [
            "Name",
            "Type",
            "Access",
            "Persistent",
            "Value",
            "Stored Value",
        ]
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

    async def set_toc(self, param):
        """Populate the model with data from the cflib2 param subsystem"""
        groups = defaultdict(list)
        for complete_name in param.names():
            group, name = complete_name.split(".", 1)
            groups[group].append(name)

        for group in sorted(groups.keys()):
            new_group = ParamGroupItem(group, self)
            for name in sorted(groups[group]):
                complete_name = f"{group}.{name}"
                new_param = ParamChildItem(new_group, name)
                new_param.ctype = param.get_type(complete_name)
                new_param.writable = param.is_writable(complete_name)
                new_param.persistent = await param.is_persistent(complete_name)
                new_group.children.append(new_param)
            self._nodes.append(new_group)

        self.layoutChanged.emit()

    def refresh(self):
        self.layoutChanged.emit()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        node = index.internalPointer()
        if node.parent is None:
            return QModelIndex()
        else:
            return self.createIndex(self._nodes.index(node.parent), 0, node.parent)

    def columnCount(self, parent):
        return len(self._column_headers)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._column_headers[section]

    def rowCount(self, parent):
        parent_item = parent.internalPointer()
        if parent.isValid():
            parent_item = parent.internalPointer()
            return parent_item.child_count()
        else:
            return len(self._nodes)

    def index(self, row, column, parent):
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
        if role == Qt.ItemDataRole.BackgroundRole:
            bgColor = self._mainUI.palette().color(self._mainUI.backgroundRole())
            if index.row() % 2 == 0:
                return bgColor
            else:
                isDark = bgColor.lightness() < 128
                multiplier = 1.15 if isDark else 0.95
                return QColor(
                    int(bgColor.red() * multiplier),
                    int(bgColor.green() * multiplier),
                    int(bgColor.blue() * multiplier),
                )

        node = index.internalPointer()
        parent = node.parent
        if not parent:
            if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
                return node.name
        elif role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return node.name
            if index.column() == 1:
                return node.ctype
            if index.column() == 2:
                return "RW" if node.writable else "RO"
            if index.column() == 3:
                return "Yes" if node.persistent else "No"
            if index.column() == 4:
                return node.value
            if index.column() == 5:
                return node.stored_value
        elif (
            role == Qt.ItemDataRole.BackgroundRole
            and index.column() == 4
            and node.is_updating
        ):
            return self._red_brush

        return None

    def find_node(self, group_name, param_name):
        """Find and return a parameter node by group and param name."""
        for group in self._nodes:
            if group.name == group_name:
                for node in group.children:
                    if node.name == param_name:
                        return node
        return None

    def iter_all_nodes(self):
        """Yield (complete_name, node) for every parameter node."""
        for group in self._nodes:
            for node in group.children:
                yield f"{group.name}.{node.name}", node

    def notify_value_changed(self, node):
        """Refresh only column 4 (Value) for the given node."""
        self._emit_column_changed(node, 4)

    def notify_stored_value_changed(self, node):
        """Refresh only column 5 (Stored Value) for the given node."""
        self._emit_column_changed(node, 5)

    def _emit_column_changed(self, node, col):
        source_row = node.parent.children.index(node)
        parent_row = self._nodes.index(node.parent)
        row_index = self.index(
            source_row, col, self.createIndex(parent_row, 0, node.parent)
        )
        proxy_index = self.proxy.mapFromSource(row_index)
        if proxy_index.isValid():
            self.proxy.dataChanged.emit(proxy_index, proxy_index)

    def flags(self, index):
        flag = super().flags(index)
        if not self._enabled:
            return Qt.ItemFlag.NoItemFlags
        return flag

    def reset(self):
        super().beginResetModel()
        self._nodes = []
        super().endResetModel()
        self.layoutChanged.emit()


class ParamTreeFilterProxy(QSortFilterProxyModel):
    """
    Implement a filtering proxy model that shows all children if the group matches.
    """

    def __init__(self, paramTree):
        super().__init__(paramTree)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not source_parent.isValid():
            return super().filterAcceptsRow(source_row, source_parent)
        return super().filterAcceptsRow(source_parent.row(), source_parent.parent())


class ParamTab(TabToolbox, param_tab_class):
    """
    Show all the parameters in the TOC and give the user the ability to edit
    them
    """

    def __init__(self, helper):
        super().__init__(helper, "Parameters")
        self.setupUi(self)

        self._cf = None
        self._load_params_task = None
        self._fetch_details_task = None
        self._model = ParamBlockModel(None, self._helper.mainUI)

        self.setParamButton.clicked.connect(self._set_param_value_clicked)
        self.currentValue.returnPressed.connect(self._set_param_value_clicked)

        self.resetDefaultButton.clicked.connect(
            lambda: self.currentValue.setText(self.defaultValue.text())
        )
        self.persistentButton.clicked.connect(self._persistent_button_clicked)

        self.proxyModel = ParamTreeFilterProxy(self.paramTree)
        self.proxyModel.setSourceModel(self._model)
        self.proxyModel.setRecursiveFilteringEnabled(True)
        self._model.set_proxy(self.proxyModel)

        @QtCore.Slot(str)
        def onFilterChanged(text):
            self.proxyModel.setFilterRegExp(text)

        self.filterBox.textChanged.connect(onFilterChanged)

        self.paramTree.setModel(self.proxyModel)
        self.paramTree.header().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.paramTree.selectionModel().selectionChanged.connect(self._paramChanged)

        # TODO: implement storing and loading of persistent parameters, for now we just disable the buttons
        self._load_param_button.setEnabled(False)
        self._dump_param_button.setEnabled(False)
        self._clear_param_button.clicked.connect(
            self._clear_stored_persistent_params_button_clicked
        )

        self._is_connected = False
        self._update_param_io_buttons()

    def connected(self, cf):
        self._cf = cf
        param = cf.param()
        self._model.reset()
        self._load_params_task = create_task(self._load_params(param))
        self._is_connected = True
        self._update_param_io_buttons()

    def disconnected(self):
        if self._load_params_task is not None:
            self._load_params_task.cancel()
            self._load_params_task = None
        if self._fetch_details_task is not None:
            self._fetch_details_task.cancel()
            self._fetch_details_task = None
        self._cf = None
        self._is_connected = False
        self._update_param_io_buttons()
        self._model.reset()
        self._paramChanged()
        self._model.set_enabled(False)

    async def _load_params(self, param):
        """Load TOC, then fetch all parameter values."""
        await self._model.set_toc(param)
        self._model.set_enabled(True)
        for complete_name, node in self._model.iter_all_nodes():
            value = await param.get(complete_name)
            node.value = round_if_float(value)
            node.is_updating = False
        self._model.layoutChanged.emit()

    def _set_param_value_clicked(self):
        name = self.paramDetailsLabel.text()
        value = self.currentValue.text()
        create_task(self._async_set_param(name, value))

    async def _async_set_param(self, name, value):
        if self._cf is None:
            return
        # Convert to appropriate numeric type
        try:
            numeric_value = int(value)
        except ValueError:
            try:
                numeric_value = float(value)
            except ValueError:
                logger.warning("Invalid parameter value: %s", value)
                return
        param = self._cf.param()
        await param.set(name, numeric_value)
        # Read back updated value
        new_value = await param.get(name)
        self._update_node_value(name, new_value)

    def _update_node_value(self, complete_name, value):
        """Update a node's displayed value after a set."""
        node = self._find_node_by_complete_name(complete_name)
        if node:
            node.value = round_if_float(value)
            node.is_updating = False
            self._model.notify_value_changed(node)

    def _paramChanged(self):
        group = None
        param = None
        indexes = self.paramTree.selectionModel().selectedIndexes()
        if len(indexes) > 0:
            selectedIndex = indexes[0]
            if selectedIndex.parent().isValid():
                group = selectedIndex.parent().data()
                param = selectedIndex.data()
            else:
                group = selectedIndex.data()

        # Made visible in _show_persistent_state()
        self.persistentFrame.setVisible(False)

        are_details_visible = param is not None
        self.valueFrame.setVisible(are_details_visible)
        self.paramDetailsLabel.setVisible(are_details_visible)
        self.paramDetailsDescription.setVisible(are_details_visible)

        if param and self._cf is not None:
            complete = f"{group}.{param}"
            self.paramDetailsLabel.setText(complete)

            if cfclient.log_param_doc is not None:
                try:
                    group_doc = cfclient.log_param_doc["params"][group]
                    desc = group_doc["variables"][param]["short_desc"]
                    self.paramDetailsDescription.setWordWrap(True)
                    self.paramDetailsDescription.setText(desc.replace("\n", ""))
                except (KeyError, TypeError, AttributeError):
                    self.paramDetailsDescription.setText("")

            # Find the node to get writable status
            node = self._model.find_node(group, param)
            if node is None:
                return

            self.currentValue.setText(str(node.value))
            self.currentValue.setStyleSheet("")
            self.currentValue.setCursorPosition(0)
            self.defaultValue.setText("-")

            self.currentValue.setEnabled(node.writable)
            self.setParamButton.setEnabled(node.writable)
            self.resetDefaultButton.setEnabled(node.writable)

            # Cancel any in-flight detail fetch before starting a new one
            if self._fetch_details_task is not None:
                self._fetch_details_task.cancel()
            self._fetch_details_task = create_task(
                self._async_fetch_param_details(complete, node)
            )

    async def _async_fetch_param_details(self, complete_name, node):
        """Fetch default value and persistent state for the selected param."""
        if self._cf is None:
            return
        param = self._cf.param()
        # Capture our task identity so we can detect if the user selected
        # a different param while we were awaiting.
        my_task = self._fetch_details_task

        if param.is_writable(complete_name):
            default_value = await param.get_default_value(complete_name)
            if self._fetch_details_task is not my_task:
                return  # A newer selection replaced us
            self.defaultValue.setText(
                str(default_value) if default_value is not None else "-"
            )

        if node.persistent:
            state = await param.persistent_get_state(complete_name)
            if self._fetch_details_task is not my_task:
                return  # A newer selection replaced us
            self._show_persistent_state(state)
            if state.is_stored:
                node.stored_value = round_if_float(state.stored_value)
            else:
                node.stored_value = ""
            self._model.notify_stored_value_changed(node)

    def _show_persistent_state(self, state):
        self.persistentFrame.setVisible(True)
        if state.is_stored:
            self.storedValue.setText(str(state.stored_value))
        else:
            self.storedValue.setText("Not stored")
        self.persistentButton.setText("Clear" if state.is_stored else "Store")

    def _persistent_button_clicked(self, _):
        complete = self.paramDetailsLabel.text()
        create_task(self._async_persistent_action(complete))

    async def _async_persistent_action(self, complete_name):
        if self._cf is None:
            return
        param = self._cf.param()

        if self.persistentButton.text() == "Clear":
            await param.persistent_clear(complete_name)
        else:
            await param.persistent_store(complete_name)

        # Refresh state
        state = await param.persistent_get_state(complete_name)
        self._show_persistent_state(state)

        # Update model node
        node = self._find_node_by_complete_name(complete_name)
        if node:
            if state.is_stored:
                node.stored_value = round_if_float(state.stored_value)
            else:
                node.stored_value = ""
            self._model.notify_stored_value_changed(node)

    def _find_node_by_complete_name(self, complete_name):
        group_name, param_name = complete_name.split(".", 1)
        return self._model.find_node(group_name, param_name)

    def _update_param_io_buttons(self):
        self._clear_param_button.setEnabled(self._is_connected)

    def _clear_stored_persistent_params_button_clicked(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Clear Stored Parameters Confirmation")
        dlg.setText("Are you sure you want to clear your stored persistent parameters?")
        dlg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        button = dlg.exec()

        if button == QMessageBox.StandardButton.Yes:
            create_task(self._async_clear_all_persistent())

    async def _async_clear_all_persistent(self):
        if self._cf is None:
            return
        param = self._cf.param()

        for complete_name in param.names():
            if await param.is_persistent(complete_name):
                state = await param.persistent_get_state(complete_name)
                if state.is_stored:
                    await param.persistent_clear(complete_name)
                    node = self._find_node_by_complete_name(complete_name)
                    if node:
                        node.stored_value = ""
                        self._model.notify_stored_value_changed(node)
