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
Container for the simple plot with functionality for data legend, saving data
and manipulating the plot.

For more advanced plotting save the data and use an external application.
"""

from PyQt5 import QtWidgets, uic

from time import time

import logging

from PyQt5.QtWidgets import QButtonGroup
from PyQt5.QtCore import *  # noqa
from PyQt5.QtWidgets import *  # noqa
from PyQt5.Qt import *  # noqa

import cfclient

__author__ = 'Bitcraze AB'
__all__ = ['PlotWidget']

logger = logging.getLogger(__name__)

(plot_widget_class, connect_widget_base_class) = (
    uic.loadUiType(cfclient.module_path + '/ui/widgets/plotter.ui'))

# Try the imports for PyQtGraph to see if it is installed
try:
    import pyqtgraph as pg
    from pyqtgraph import ViewBox
    import pyqtgraph.console  # noqa
    import numpy as np  # noqa

    _pyqtgraph_found = True
except Exception:
    import traceback

    logger.warning("PyQtGraph (or dependency) failed to import:\n%s",
                   traceback.format_exc())
    _pyqtgraph_found = False

# This is required to force py2exe to pull in the correct dependencies on
# Windows. But for Linux this is not required and might not be installed with
# the PyQtGraph package.
try:
    from scipy.stats import futil  # noqa
    from scipy.sparse.csgraph import _validation  # noqa
    from scipy.special import _ufuncs_cxx  # noqa
except Exception:
    pass


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
        """
        Set what data should be shown from the curve. This is done to keep
        performance when many points have been added.
        """
        limit = min(stop, len(self.data))
        self.curve.setData(y=self.data[start:limit], x=self.ts[start:limit])
        return [self.ts[start], self.ts[limit - 1]]


class PlotWidget(QtWidgets.QWidget, plot_widget_class):
    """Wrapper widget for PyQtGraph adding some extra buttons"""

    def __init__(self, parent=None, fps=100, title="", *args):
        super(PlotWidget, self).__init__(*args)
        self.setupUi(self)

        # Limit the plot update to 10Hz
        self._ts = time()
        self._delay = 0.1

        # Check if we could import PyQtGraph, if not then stop here
        if not _pyqtgraph_found:
            self.can_enable = False
            return
        else:
            self.can_enable = True

        self._items = {}
        self._last_item = 0

        self.setSizePolicy(QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding))

        self.setMinimumSize(self.minimumSizeHint())
        self.parent = parent

        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.hideButtons()
        self._plot_widget.setLabel('bottom', "Time", "ms")
        self._plot_widget.addLegend()
        self._plot_widget.getViewBox().disableAutoRange(ViewBox.XAxis)
        self._plot_widget.getViewBox().sigRangeChangedManually.connect(
            self._manual_range_change)
        self._plot_widget.getViewBox().setMouseEnabled(x=False, y=True)
        self._plot_widget.getViewBox().setMouseMode(ViewBox.PanMode)

        self.plotLayout.addWidget(self._plot_widget)

        # self.saveToFile.clicked.connect(self.saveToFileSignal)
        self._x_min = 0
        self._x_max = 500
        self._enable_auto_y.setChecked(True)
        self._enable_samples_x.setChecked(True)
        self._last_ts = None
        self._dtime = None

        self._x_range = (
            float(self._range_x_min.text()), float(self._range_x_max.text()))
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

        self._draw_graph = True
        self._auto_redraw.stateChanged.connect(self._auto_redraw_change)

    def _auto_redraw_change(self, state):
        """Callback from the auto redraw checkbox"""
        if state == 0:
            self._draw_graph = False
        else:
            self._draw_graph = True

    def _y_mode_change(self, box):
        """Callback when user changes the Y-axis mode"""
        if box == self._enable_range_y:
            self._range_y_min.setEnabled(True)
            self._range_y_max.setEnabled(True)
            y_range = (
                float(self._range_y_min.value()),
                float(self._range_y_max.value()))
            self._plot_widget.getViewBox().setRange(yRange=y_range)
        else:
            self._range_y_min.setEnabled(False)
            self._range_y_max.setEnabled(False)

        if box == self._enable_auto_y:
            self._plot_widget.getViewBox().enableAutoRange(ViewBox.YAxis)

    def _manual_range_change(self, obj):
        """
        Callback from pyqtplot when users changes the range of the plot using
        the mouse
        """
        [[x_min, x_max],
         [y_min, y_max]] = self._plot_widget.getViewBox().viewRange()
        self._range_y_min.setValue(y_min)
        self._range_y_max.setValue(y_max)
        self._range_y_min.setEnabled(True)
        self._range_y_max.setEnabled(True)
        self._enable_range_y.setChecked(True)

    def _y_range_changed(self, val):
        """Callback when user changes Y range manually"""
        _y_range = (
            float(self._range_y_min.value()),
            float(self._range_y_max.value()))
        self._plot_widget.getViewBox().setRange(yRange=_y_range, padding=0)

    def _nbr_samples_changed(self, val):
        """Callback when user changes the number of samples to be shown"""
        self._nbr_samples = val

    def set_title(self, title):
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
        self._items[title] = PlotItemWrapper(
            self._plot_widget.plot(name=title, pen=pen))

    def add_data(self, data, ts):
        """
        Add new data to the plot.

        data - dictionary sent from logging layer containing variable/value
               pairs
        ts - timestamp of the data in ms
        """
        if not self._last_ts:
            self._last_ts = ts
        elif not self._last_ts:
            self._dtime = ts - self._last_ts
            self._last_ts = ts

        x_min_limit = 0
        x_max_limit = 0
        # We are adding new datasets, calculate what we should show.
        if self._enable_samples_x.isChecked():
            x_min_limit = max(0, self._last_item - self._nbr_samples)
            x_max_limit = max(self._last_item, self._nbr_samples)

        for name in self._items:
            self._items[name].add_point(data[name], ts)
            if self._draw_graph and time() > self._ts + self._delay:
                [self._x_min, self._x_max] = self._items[name].show_data(
                    x_min_limit, x_max_limit)
        if time() > self._ts + self._delay:
            self._ts = time()
        if (self._enable_samples_x.isChecked() and self._dtime and
                self._last_item < self._nbr_samples):
            self._x_max = self._x_min + self._nbr_samples * self._dtime

        self._last_item = self._last_item + 1
        self._plot_widget.getViewBox().setRange(
            xRange=(self._x_min, self._x_max))

    def removeAllDatasets(self):
        """Reset the plot by removing all the datasets"""
        for item in self._items:
            self._plot_widget.removeItem(self._items[item])

        self._clear_legend()

        self._items = {}
        self._last_item = 0
        self._last_ts = None
        self._dtime = None
        self._plot_widget.clear()

    def _clear_legend(self):
        legend = self._plot_widget.plotItem.legend

        while legend.layout.count() > 0:
            item = legend.items[0]
            name = item[1].text
            legend.removeItem(name)
