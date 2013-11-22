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
Container for the simple plot with functionality for data legend, saving data
and manipulating the plot.

For more advanced plotting save the data and use an external application.
"""

__author__ = 'Bitcraze AB'
__all__ = ['PlotWidget']

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, QLine, QPoint, QPointF, QSize, QRectF

from time import time
import math

import logging

logger = logging.getLogger(__name__)

import sys

from PyQt4 import Qt, QtCore, QtGui, uic
from PyQt4.QtGui import QButtonGroup
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *

(plot_widget_class,
connect_widget_base_class) = (uic.loadUiType(
                             sys.path[0] + '/cfclient/ui/widgets/plotter.ui'))

import pyqtgraph as pg
from pyqtgraph import ViewBox
from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.console
import numpy as np

class PlotItemWrapper:
    """Wrapper for PlotDataItem to handle what data is shown"""
    def __init__(self, curve):
        """Initialize"""
        self.data = []
        self.ts = []
        self.curve = curve

    def add_point(self, p, ts):
        """
        Add a point to the curve.

        p - point
        ts - timestamp in ms
        """
        self.data.append(p)
        self.ts.append(ts)

    def show_data(self, start, stop):
        """Set what data should be shown from the curve. This is done to keep performance when many
        points have been added."""
        limit = min(stop, len(self.data))
        self.curve.setData(y=self.data[start:limit], x=self.ts[start:limit])
        return [self.ts[start], self.ts[limit-1]]

class PlotWidget(QtGui.QWidget, plot_widget_class):
    """Wrapper widget for PyQtGraph adding some extra buttons"""

    saveToFileSignal = pyqtSignal()
    stopSavingSignal = pyqtSignal()

    def __init__(self, parent=None, fps=100, title="", *args):
        super(PlotWidget, self).__init__(*args)
        self.setupUi(self)

        self._items = []
        self._last_item = 0

        self.setSizePolicy(QtGui.QSizePolicy(
                                         QtGui.QSizePolicy.MinimumExpanding,
                                         QtGui.QSizePolicy.MinimumExpanding))

        self.setMinimumSize(self.minimumSizeHint())
        self.parent = parent

        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.hideButtons()
        self._plot_widget.setLabel('bottom', "Time", "ms")
        self._plot_widget.addLegend()
        self._plot_widget.getViewBox().disableAutoRange(ViewBox.XAxis)
        self._plot_widget.getViewBox().sigRangeChangedManually.connect(self._manual_range_change)
        self._plot_widget.getViewBox().setMouseEnabled(x=False, y=True)
        self._plot_widget.getViewBox().setMouseMode(ViewBox.PanMode)

        self.plotLayout.addWidget(self._plot_widget)

        #self.saveToFile.clicked.connect(self.saveToFileSignal)
        self._x_min = 0
        self._x_max = 500
        self._enable_auto_y.setChecked(True)
        self._enable_samples_x.setChecked(True)
        self._last_ts = None
        self._dtime = None

        self._x_range = (float(self._range_x_min.text()), float(self._range_x_max.text()))
        self._nbr_samples = int(self._nbr_of_samples_x.text())

        self._nbr_of_samples_x.valueChanged.connect(self._nbr_samples_changed)
        self._range_y_min.valueChanged.connect(self._y_range_changed)
        self._range_y_max.valueChanged.connect(self._y_range_changed)

        self._y_btn_group = QButtonGroup()
        self._y_btn_group.addButton(self._enable_auto_y)
        self._y_btn_group.addButton(self._enable_range_y)
        self._y_btn_group.setExclusive(True)
        self._y_btn_group.buttonClicked.connect(self._y_mode_change)

        self._x_btn_group = QButtonGroup()
        self._x_btn_group.addButton(self._enable_range_x)
        self._x_btn_group.addButton(self._enable_samples_x)
        self._x_btn_group.addButton(self._enable_seconds_x)
        self._x_btn_group.addButton(self._enable_manual_x)
        self._x_btn_group.setExclusive(True)
        self._x_btn_group.buttonClicked.connect(self._x_mode_change)

    def _x_mode_change(self, box):
        """Callback when user changes the X-axis mode"""
        if box == self._enable_range_x:
            logger.info("Enable range x")
            self._x_range = (float(self._range_x_min.text()), float(self._range_x_max.text()))
        else:
            self._range_x_min.setEnabled(False)
            self._range_x_max.setEnabled(False)

    def _y_mode_change(self, box):
        """Callback when user changes the Y-axis mode"""
        if box == self._enable_range_y:
            logger.info("Enabling range y")
            self._range_y_min.setEnabled(True)
            self._range_y_max.setEnabled(True)
            y_range = (float(self._range_y_min.text()), float(self._range_y_max.text()))
            self._plot_widget.getViewBox().setRange(yRange=y_range)
        else:
            self._range_y_min.setEnabled(False)
            self._range_y_max.setEnabled(False)

        if box == self._enable_auto_y:
            self._plot_widget.getViewBox().enableAutoRange(ViewBox.YAxis)

    def _manual_range_change(self, obj):
        """Callback from pyqtplot when users changes the range of the plot using the mouse"""
        [[x_min,x_max],[y_min,y_max]] = self._plot_widget.getViewBox().viewRange()
        self._range_y_min.setValue(y_min)
        self._range_y_max.setValue(y_max)
        self._range_y_min.setEnabled(True)
        self._range_y_max.setEnabled(True)
        self._enable_range_y.setChecked(True)

    def _y_range_changed(self, val):
        """Callback when user changes Y range manually"""
        _y_range = (float(self._range_y_min.value()), float(self._range_y_max.value()))
        self._plot_widget.getViewBox().setRange(yRange=_y_range, padding=0)

    def _nbr_samples_changed(self, val):
        """Callback when user changes the number of samples to be shown"""
        self._nbr_samples = val

    def stopSaving(self):
        #self.saveToFile.setText("Start saving to file")
        #self.saveToFile.clicked.disconnect(self.stopSaving)
        #self.saveToFile.clicked.connect(self.saveToFileSignal)
        #self.stopSavingSignal.emit()
        return

    def isSavingToFile(self):
        #self.saveToFile.setText("Stop saving")
        #self.saveToFile.clicked.disconnect(self.saveToFileSignal)
        #self.saveToFile.clicked.connect(self.stopSaving)
        return

    def setTitle(self, title):
        """
        Set the title of the plot.

        title - the new title
        """
        self._plot_widget.setTitle(title)

    def add_curve(self, title, pen='r'):
        """
        Add a new curve to the plot.

        title - the name of the data
        pen - color of curve (using r for red and so on..)
        """
        self._items.append(PlotItemWrapper(self._plot_widget.plot(name=title, pen=pen)))

    def add_data(self, data, ts):
        """
        Add new data to the plot.

        data - dictionary sent from logging layer containing variable/value pairs
        ts - timestamp of the data in ms
        """
        if not self._last_ts:
            self._last_ts = ts
        elif not self._last_ts:
            self._dtime = ts - self._last_ts
            self._last_ts = ts

        di = 0
        x_min_limit = 0
        x_max_limit = 0
        # We are adding new datasets, calculate what we should show.
        if self._enable_samples_x.isChecked():
            x_min_limit = max(0, self._last_item-self._nbr_samples)
            x_max_limit = max(self._last_item, self._nbr_samples)

        for d in data:
            self._items[di].add_point(data[d], ts)
            [self._x_min, self._x_max] = self._items[di].show_data(x_min_limit, x_max_limit)
            di = di + 1
        if self._enable_samples_x.isChecked() and self._dtime and self._last_item < self._nbr_samples:
            self._x_max = self._x_min + self._nbr_samples * self._dtime

        self._last_item = self._last_item + 1
        self._plot_widget.getViewBox().setRange(xRange=(self._x_min, self._x_max))

    def removeAllDatasets(self):
        """Reset the plot by removing all the datasets"""
        for item in self._items:
            self._plot_widget.removeItem(item)
        self._plot_widget.plotItem.legend.items = []
        self._items = []
        self._last_item = 0
        self._last_ts = None
        self._dtime = None
