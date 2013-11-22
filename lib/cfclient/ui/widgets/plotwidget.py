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
from rtplotwidget import FastPlotWidget, PlotDataSet

(plot_widget_class,
connect_widget_base_class) = (uic.loadUiType(
                             sys.path[0] + '/cfclient/ui/widgets/plotter.ui'))

import pyqtgraph as pg
from pyqtgraph import ViewBox
from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.console
import numpy as np

class PlotItemWrapper:

    def __init__(self, curve):
        self.data = []
        self.ts = []
        self.curve = curve

    def add_point(self, p, ts):
        # Role axis instead ofcapping
        self.data.append(p)
        self.ts.append(ts)
        #if len(self.data) > 1000:
        #    self.data.pop(0)
    def show_data(self, start, stop):
        #logger.info("Showing %d-%d", start, stop)
        limit = min(stop, len(self.data))
        self.curve.setData(y=self.data[start:limit], x=self.ts[start:limit])
        return [self.ts[start], self.ts[limit-1]]

AUTO_MODE = 0
SAMPLES_MODE = 1
RANGE_MODE = 2
MANUAL_MODE = 3

class PlotWidget(QtGui.QWidget, plot_widget_class):

    # Add support for
    # * Multipe axis
    # * Klicking to pause
    # * Klicking to show data value (or mouse of if ok CPU wise..)
    # * Scrolling when paused
    # * Zooming
    # * Change axis
    # * Auto size of min/max X-axis
    # * Redraw of resize (stop on minimum size)
    # * Fill parent as much as possible
    # * Add legend (either hard, option or mouse over)
    saveToFileSignal = pyqtSignal()

    stopSavingSignal = pyqtSignal()

    _autorange_y_checked_signal = pyqtSignal(bool)
    _autorange_x_checked_signal = pyqtSignal(bool)
    _set_x_range_signal = pyqtSignal(float, float)

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

        #self._range_auto_x.stateChanged.connect(self._autorange_x_toggled)
        #self._enable_auto_y.toggled.connect(self._autorange_y_toggled)

        self._enable_samples_x.toggled.connect(self._enable_samples_x_toggled)
        self._enable_manual_x.toggled.connect(self._enable_manual_x_toggled)
        self._enable_range_x.toggled.connect(self._enable_range_x_toggled)
        #self._enable_range_x.stateChanged.connect(self._enable_range_x_changed)

        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.hideButtons()
        self._plot_widget.setLabel('bottom', "Time", "ms")
        # This will change in the future
        #self._plot_widget.setLabel('left', "Data", "?")
        self._plot_widget.addLegend()
        self._plot_widget.getViewBox().disableAutoRange(ViewBox.XAxis)
        #self._plot_widget.getViewBox().setRange(xRange=(1,1000), padding=0)
        
        self._plot_widget.sigXRangeChanged.connect(self._plot_x_range_changed)
        self._plot_widget.getViewBox().sigRangeChangedManually.connect(self._manual_range_change)
        self._plot_widget.getViewBox().setMouseEnabled(x=False, y=True)
        self._plot_widget.getViewBox().setMouseMode(ViewBox.PanMode)
        #sigXRangeChanged	wrapped from ViewBox

        self.plotLayout.addWidget(self._plot_widget)

        #self.saveToFile.clicked.connect(self.saveToFileSignal)
        self.hcount = 0
        self.vcount = 0
        self._x_min = 0
        self._x_max = 500
        self._x_mode = SAMPLES_MODE
        self._enable_auto_y.setChecked(True)
        self._enable_samples_x.setChecked(True)
        self._last_ts = None
        self._dtime = None

        self._x_range = (float(self._range_x_min.text()), float(self._range_x_max.text()))
        self._nbr_samples = int(self._nbr_of_samples_x.text())
        self._set_x_range_signal.connect(self._set_x_range)

        #def _enable_samples_x_changed(self, state):
        self._nbr_of_samples_x.valueChanged.connect(self._nbr_samples_changed)
        self._x_btn_group = QButtonGroup()

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

        #def _enable_range_x_changed(self, state):

    def _x_mode_change(self, box):
        if box == self._enable_range_x:
            logger.info("Enable range x")
            self._x_range = (float(self._range_x_min.text()), float(self._range_x_max.text()))
        else:
            self._range_x_min.setEnabled(False)
            self._range_x_max.setEnabled(False)

        if box == self._enable_samples_x:
            logger.info("Enable samples x")

    def _y_mode_change(self, box):
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
        [[x_min,x_max],[y_min,y_max]] = self._plot_widget.getViewBox().viewRange()
        self._range_y_min.setText("%.2f" % y_min)
        self._range_y_max.setText("%.2f" % y_max)
        self._range_y_min.setEnabled(True)
        self._range_y_max.setEnabled(True)
        self._enable_range_y.setChecked(True)

    def _nbr_samples_changed(self, val):
        self._nbr_samples = val

    def _set_x_range(self, x_min, x_max):
        logger.info("Setting new range %.2f-%.2f", x_min, x_max)
        self._plot_widget.getViewBox().setRange(xRange=(x_min, x_max), padding=0)

    def _enable_samples_x_toggled(self, enabled):
        if enabled:
            self._enable_manual_x.setChecked(False)
            self._enable_range_x.setChecked(False)
            self._nbr_of_samples_x.setEnabled(True)
            self._x_mode = SAMPLES_MODE
            self._nbr_samples = int(self._nbr_of_samples_x.text())
            #self._plot_widget.getViewBox().setRange(xRange=(max(0, self._last_item-self._nbr_samples), self._last_item))
        else:
            self._nbr_of_samples_x.setEnabled(False)

    def _enable_range_x_toggled(self, enabled):
        if enabled:
            self._enable_manual_x.setChecked(False)
            self._enable_samples_x.setChecked(False)
            self._x_mode = RANGE_MODE
            self._range_x_min.setEnabled(True)
            self._range_x_max.setEnabled(True)
            self._x_range = (float(self._range_x_min.text()), float(self._range_x_max.text()))
            self._plot_widget.getViewBox().setRange(xRange=self._x_range, padding=0)
        else:
            self._range_x_min.setEnabled(False)
            self._range_x_max.setEnabled(False)

    def _enable_manual_x_toggled(self, enabled):
        if enabled:
            self._enable_samples_x.setChecked(False)
            self._enable_range_x.setChecked(False)
            self._x_mode = MANUAL_MODE

    def _plot_x_range_changed(self):
        #logger.info("Range changed")
        [[x_min,x_max],[y_min,y_max]] = self._plot_widget.getViewBox().viewRange()
        samples = x_max - x_min

        #if self._x_mode == SAMPLES_MODE and x_min != self._x_min and x_max != self._x_max:
            #logger.info("In samples mode, force back range (%.2f,%.2f)vs(%.2f,%.2f))", self._x_min, self._x_max, x_min, x_max)
            #self._set_x_range_signal.emit(max(0, self._last_item-self._nbr_samples), self._last_item)
            #self._plot_widget.getViewBox().setRange(xRange=(self._x_min, self._x_max), disableAutoRange=False, padding=0)
        if self._x_mode == RANGE_MODE and self._x_mode == RANGE_MODE and self._x_range[0] == x_min and self._x_range[1] == x_max:
            logger.info("In range mode, force back range")
            logger.info("Setting range to %s", str(self._x_range))
            self._plot_widget.getViewBox().setRange(xRange=self._x_range, padding=0)
        #if self._x_mode != MANUAL_MODE:
        #    # Check with the current range if
        #    # the mouse changed something or
        #    # we are changing it
        #    [[x_min,x_max],[y_min,y_max]] = self._plot_widget.getViewBox().viewRange()
        #    logger.info("Range is %.2f-%.2f", x_min, x_max)
        #    logger.info(self._x_range)
        #    samples = x_max - x_min
        #    logger.info("Samples are %d", samples)
        #    if self._x_mode == SAMPLES_MODE and self._nbr_samples == samples:
        #        logger.info("Match on samples")
        #    if self._x_mode == RANGE_MODE and self._x_range[0] == x_min and self._x_range[1] == x_max:
        #        logger.info("Match on range")
        #    if not (self._x_mode == SAMPLES_MODE and self._nbr_samples == samples) and not (self._x_mode == RANGE_MODE and self._x_range[0] == x_min and self._x_range[1] == x_max):
        #        # This change was not because we changed the settings
        #        self._x_mode = MANUAL_MODE
        #        logger.info("Entering free mode")
        #    else:
        #        logger.info("We requested a change")

    def _autorange_x_toggled(self, state):
        self._enable_range_x.setEnabled(not state)
        self._range_x_min.setEnabled(not state)
        self._range_x_max.setEnabled(not state)
        self._enable_samples_x.setEnabled(not state)
        self._nbr_of_samples_x.setEnabled(not state)
        if not state:
            [[x_min,x_max],[y_min,y_max]] = self._plot_widget.getViewBox().viewRange()
            self._range_x_min.setText(str(x_min))
            self._range_x_max.setText(str(x_max))
            self._plot_widget.getViewBox().disableAutoRange(ViewBox.XAxis)
        else:
            self._range_x_min.setText("")
            self._range_x_max.setText("")
            self._plot_widget.getViewBox().enableAutoRange(ViewBox.XAxis)

    def _autorange_y_toggled(self, state):
        self._enable_range_y.setEnabled(not state)
        self._range_y_min.setEnabled(not state)
        self._range_y_max.setEnabled(not state)
        self._enable_samples_y.setEnabled(not state)
        if not state:
            [[x_min,x_max],[y_min,y_max]] = self._plot_widget.getViewBox().viewRange()
            self._range_y_min.setText(str(y_min))
            self._range_y_max.setText(str(y_max))
            self._plot_widget.getViewBox().disableAutoRange(ViewBox.YAxis)
        else:
            self._range_y_min.setText("")
            self._range_y_max.setText("")
            self._plot_widget.getViewBox().enableAutoRange(ViewBox.YAxis)

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

    def setTitle(self, newTitle):
        self._plot_widget.setTitle(newTitle)

    def add_curve(self, title, pen='r'):
        self._items.append(PlotItemWrapper(self._plot_widget.plot(name=title, pen=pen)))

    def add_data(self, data, ts):
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
            #logger.info("%.2f-%d", self._x_min, x_min_limit)
            self._x_max = self._x_min + self._nbr_samples * self._dtime

        self._last_item = self._last_item + 1
        self._plot_widget.getViewBox().setRange(xRange=(self._x_min, self._x_max))
        #logger.info("--->%.2f", self._x_max - self._x_min) 
            #    self._plot_widget.getViewBox().enableAutoRange(ViewBox.XAxis)
            #    self._plot_widget.getViewBox().setRange(xRange=(max(0, self._last_item-self._nbr_samples), self._last_item))

    def removeDataset(self, dataset):
        logger.warning("removeDataset() not implemented")

    def removeAllDatasets(self):
        for item in self._items:
            self._plot_widget.removeItem(item)
        self._plot_widget.plotItem.legend.items = []
        self._items = []
        self._last_item = 0
        self._last_ts = None
        self._dtime = None
