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
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *
from rtplotwidget import FastPlotWidget, PlotDataSet

(plot_widget_class,
connect_widget_base_class) = (uic.loadUiType(
                             sys.path[0] + '/cfclient/ui/widgets/plotter.ui'))


class PlotWidget(QtGui.QWidget, plot_widget_class):

    LEGEND_ON_BOTTOM = 1
    LEGEND_ON_RIGHT = 2

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
    # isSavingToFileSignal = pyqtSignal()

    def __init__(self, parent=None, fps=100, title="", *args):
        # super(FastPlotWidget, self).__init__(parent)
        super(PlotWidget, self).__init__(*args)
        self.setupUi(self)

        self.setSizePolicy(QtGui.QSizePolicy(
                                         QtGui.QSizePolicy.MinimumExpanding,
                                         QtGui.QSizePolicy.MinimumExpanding))

        self.setMinimumSize(self.minimumSizeHint())
        self.parent = parent

        self.plotCaption.setText(title)
        self.plotCaption.setFont(QtGui.QFont('SansSerif', 16))
        self.fpw = FastPlotWidget()

        self.plotLayout.addWidget(self.fpw)

        self.enableUpdate.toggled.connect(self.fpw.setEnabled)

        self.saveToFile.clicked.connect(self.saveToFileSignal)
        self.hcount = 0
        self.vcount = 0
        self.zoom = 1.0

        self.zoomInBtn.clicked.connect(self.zoomIn)
        self.zoomOutBtn.clicked.connect(self.zoomOut)

    def zoomIn(self):
        self.zoom = self.zoom + 0.2
        self.fpw.setZoom(self.zoom)

    def zoomOut(self):
        self.zoom = self.zoom - 0.2
        if self.zoom < 0.1:
            self.zoom = 0.1
        self.fpw.setZoom(self.zoom)

    def stopSaving(self):
        self.saveToFile.setText("Start saving to file")
        self.saveToFile.clicked.disconnect(self.stopSaving)
        self.saveToFile.clicked.connect(self.saveToFileSignal)
        self.stopSavingSignal.emit()

    def isSavingToFile(self):
        self.saveToFile.setText("Stop saving")
        self.saveToFile.clicked.disconnect(self.saveToFileSignal)
        self.saveToFile.clicked.connect(self.stopSaving)

    def setTitle(self, newTitle):
        self.plotCaption.setText(newTitle)

    def addDataset(self, dataset):
        self.fpw.addDataset(dataset)

        newLayout = QHBoxLayout()
        dsEnabled = QCheckBox(dataset.title)
        dsEnabled.setChecked(True)
        dsEnabled.toggled.connect(dataset.setEnabled)
        newLayout.addWidget(dsEnabled)
        self.legend.addLayout(newLayout, self.hcount, self.vcount)
        self.hcount = self.hcount + 1
        logger.debug("Creating new layout for [%s] at %d,%d",
                     dataset.title, self.hcount, self.vcount)
        if (self.hcount == 2):
            self.vcount = self.vcount + 1
            self.hcount = 0

    def removeDataset(self, dataset):
        logger.warning("removeDataset() not implemented")

    def removeAllDatasets(self):
        self.fpw.datasets = []
        # TODO: Fix this!
        for w in range(self.legend.count()):
            l = self.legend.itemAt(w)
            if (l != None):
                l.itemAt(0).widget().setVisible(False)
            # self.legend.removeItem(self.legend.itemAt(w))
            # self.legend.itemAt(w).hide()
            # print "Taking %d" % w
        self.hcount = 0
        self.vcount = 0
