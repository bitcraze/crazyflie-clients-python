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
This tab plots different logging data defined by configurations that has been
pre-configured.
"""

import logging

from cfclient.ui.tab_toolbox import TabToolbox
from cfclient.ui.widgets.plotwidget import PlotWidget
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QAbstractItemModel
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox

import cfclient

__author__ = 'Bitcraze AB'
__all__ = ['PlotTab']

logger = logging.getLogger(__name__)

plot_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/plotTab.ui")[0]


class LogConfigModel(QAbstractItemModel):
    """Model for log configurations in the ComboBox"""

    def __init__(self, parent=None):
        super(LogConfigModel, self).__init__(parent)
        self._nodes = []

    def add_block(self, block):
        self._nodes.append(block)
        self.layoutChanged.emit()
        self._nodes.sort(key=lambda conf: conf.name.lower())

    def parent(self, index):
        """Re-implemented method to get the parent of the given index"""
        return QModelIndex()

    def remove_block(self, block):
        """Remove a block from the view"""
        self._nodes.remove(block)

    def columnCount(self, parent):
        """Re-implemented method to get the number of columns"""
        return 1

    def rowCount(self, parent):
        """Re-implemented method to get the number of rows for a given index"""
        parent_item = parent.internalPointer()
        if parent.isValid():
            parent_item = parent.internalPointer()  # noqa
            return 0
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
            return index
        else:
            return self.createIndex(row, column, node.get_child(row))

    def data(self, index, role):
        """Re-implemented method to get the data for a given index and role"""
        node = index.internalPointer()  # noqa
        if not index.isValid() or not 0 <= index.row() < len(self._nodes):
            return None
        if role == Qt.DisplayRole:
            return self._nodes[index.row()].name
        return None

    def reset(self):
        """Reset the model"""
        self._nodes = []
        self.layoutChanged.emit()

    def get_config(self, i):
        return self._nodes[i]


class PlotTab(TabToolbox, plot_tab_class):
    """Tab for plotting logging data"""

    _log_data_signal = pyqtSignal(int, object, object)
    _log_error_signal = pyqtSignal(object, str)
    _disconnected_signal = pyqtSignal(str)
    _connected_signal = pyqtSignal(str)

    colors = [
        (60, 200, 60),    # green
        (40, 100, 255),   # blue
        (255, 130, 240),  # magenta
        (255, 26, 28),    # red
        (255, 170, 0),    # orange
        (40, 180, 240),   # cyan
        (153, 153, 153),  # grey
        (176, 96, 50),    # brown
        (180, 60, 240),   # purple
    ]

    def __init__(self, helper):
        super(PlotTab, self).__init__(helper, 'Plotter')
        self.setupUi(self)

        self._log_error_signal.connect(self._logging_error)

        self._plot = PlotWidget(fps=30)
        # Check if we could find the PyQtImport. If not, then
        # set this tab as disabled
        is_enabled = self._plot.can_enable

        self._model = LogConfigModel()
        self.dataSelector.setModel(self._model)
        self._log_data_signal.connect(self._log_data_received)
        self.plotLayout.addWidget(self._plot)

        # Connect external signals if we can use the tab
        if is_enabled:
            self._disconnected_signal.connect(self._disconnected)
            self._helper.cf.disconnected.add_callback(
                self._disconnected_signal.emit)

            self._connected_signal.connect(self._connected)
            self._helper.cf.connected.add_callback(
                self._connected_signal.emit)

            self._helper.cf.log.block_added_cb.add_callback(self._config_added)
            self.dataSelector.currentIndexChanged.connect(
                self._selection_changed)

        self._previous_config = None
        self._started_previous = False

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        self._plot.removeAllDatasets()
        self._plot.set_title("")

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        self._model.beginResetModel()
        self._model.reset()
        self._model.endResetModel()
        self.dataSelector.setCurrentIndex(-1)
        self._previous_config = None
        self._started_previous = False

    def _log_data_signal_wrapper(self, ts, data, logconf):
        """Wrapper for signal"""

        # For some reason the *.emit functions are not
        # the same over time (?!) so they cannot be registered and then
        # removed as callbacks.
        self._log_data_signal.emit(ts, data, logconf)

    def _log_error_signal_wrapper(self, config, msg):
        """Wrapper for signal"""

        # For some reason the *.emit functions are not
        # the same over time (?!) so they cannot be registered and then
        # removed as callbacks.
        self._log_error_signal.emit(config, msg)

    def _selection_changed(self, i):
        """Callback from ComboBox when a new item has been selected"""

        # Check if we have disconnected
        if i < 0:
            return
        # First check if we need to stop the old block
        if self._started_previous and self._previous_config:
            logger.debug("Should stop config [%s], stopping!",
                         self._previous_config.name)
            self._previous_config.delete()

        # Remove our callback for the previous config
        if self._previous_config:
            self._previous_config.data_received_cb.remove_callback(
                self._log_data_signal_wrapper)
            self._previous_config.error_cb.remove_callback(
                self._log_error_signal_wrapper)

        lg = self._model.get_config(i)
        if not lg.started:
            logger.debug("Config [%s] not started, starting!", lg.name)
            self._started_previous = True
            lg.start()
        else:
            self._started_previous = False
        self._plot.removeAllDatasets()
        color_selector = 0

        self._plot.set_title(lg.name)

        for d in lg.variables:
            self._plot.add_curve(d.name, self.colors[
                color_selector % len(self.colors)])
            color_selector += 1
        lg.data_received_cb.add_callback(self._log_data_signal_wrapper)
        lg.error_cb.add_callback(self._log_error_signal_wrapper)

        self._previous_config = lg

    def _config_added(self, logconfig):
        """Callback from the log layer when a new config has been added"""
        logger.debug("Callback for new config [%s]", logconfig.name)
        self._model.add_block(logconfig)

    def remove_config(self, logconfig):
        self._model.remove_block(logconfig)

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(
            self, "Plot error", "Error when starting log config [%s]: %s" % (
                log_conf.name, msg))

    def _log_data_received(self, timestamp, data, logconf):
        """Callback when the log layer receives new data"""

        # Check so that the incoming data belongs to what we are currently
        # logging
        if self._previous_config:
            if self._previous_config.name == logconf.name:
                self._plot.add_data(data, timestamp)
