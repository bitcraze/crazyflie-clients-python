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
This tab plots different logging data defined by configurations that has been
pre-configured.
"""

__author__ = 'Bitcraze AB'
__all__ = ['PlotTab']

import glob
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import pyqtSlot, pyqtSignal, QThread
from pprint import pprint
import datetime

# from FastPlotWidget import FastPlotWidget, PlotDataSet
from cfclient.ui.widgets.plotwidget import PlotWidget
from cfclient.ui.widgets.rtplotwidget import PlotDataSet

from cflib.crazyflie.log import Log

from cfclient.ui.tab import Tab

plot_tab_class = uic.loadUiType(sys.path[0] +
                                "/cfclient/ui/tabs/plotTab.ui")[0]


class PlotTab(Tab, plot_tab_class):
    """Tab for plotting logging data"""

    logDataSignal = pyqtSignal(object, int)

    colors = [QtCore.Qt.green, QtCore.Qt.blue, QtCore.Qt.magenta,
              QtCore.Qt.red, QtCore.Qt.black, QtCore.Qt.cyan, QtCore.Qt.yellow]

    dsList = []

    connectedSignal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(PlotTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Plotter"
        self.menuName = "Plotter"

        self.previousLog = None

        self.dsList = helper.logConfigReader.getLogConfigs()
        self.plot = PlotWidget(fps=50)

        self.dataSelector.currentIndexChanged.connect(self.newLogSetupSelected)

        self.logDataSignal.connect(self.logDataReceived)

        self.tabWidget = tabWidget
        self.helper = helper
        # self.layout().addWidget(self.dataSelector)
        self.plotLayout.addWidget(self.plot)

        # Connect external signals
        self.helper.cf.connectSetupFinished.add_callback(
                                                     self.connectedSignal.emit)
        self.connectedSignal.connect(self.connected)

        self.datasets = []
        self.logEntrys = []

        self.plot.saveToFileSignal.connect(self.saveToFile)
        self.plot.stopSavingSignal.connect(self.savingStopped)
        self.saveFile = None

    def saveToFile(self):
        filename = "%s-%s.csv" % (datetime.datetime.now(),
                                  self.dataSelector.currentText())
        filename = filename.replace(":", ".")
        savePath = os.path.join(os.path.expanduser("~"), filename)
        logger.info("Saving logdata to [%s]", savePath)
        self.saveFile = open(savePath, 'w')
        s = "Timestamp,"
        for v in self.dsList[self.dataSelector.currentIndex()].getVariables():
            s += v.getName() + ","
        s += '\n'
        self.saveFile.write(s)
        self.plot.isSavingToFile()

    def savingStopped(self):
        self.saveFile.close()
        logger.info("Stopped saving logdata")
        self.saveFile = None

    def newLogSetupSelected(self, item):

        if (len(self.logEntrys) > 0):
            log = self.logEntrys[item]
            if (self.previousLog != None):
                self.previousLog.stop()
            log.start()
            self.previousLog = log

            # Setup the plot
            self.plot.removeAllDatasets()
            self.datasets = []
            colorSelector = 0

            info = self.dsList[self.dataSelector.currentIndex()]
            self.plot.setTitle(info.getName())
            minVal = info.getDataRangeMin()
            maxVal = info.getDataRangeMax()

            for d in info.getVariables():
                ds = PlotDataSet(d.getName(),
                                 self.colors[colorSelector % len(self.colors)],
                                 [minVal, maxVal])
                self.datasets.append(ds)
                self.plot.addDataset(ds)
                colorSelector += 1
                pprint(ds)
        if (self.saveFile != None):
            self.plot.stopSaving()

    def loggingError(self, err):
        logger.warning("logging error: %s", err)

    def connected(self, link):
        self.logEntrys = []
        self.dataSelector.clear()
        for d in self.dsList:
            logEntry = self.helper.cf.log.create_log_packet(d)
            if (logEntry != None):
                self.dataSelector.addItem(d.getName())
                self.logEntrys.append(logEntry)
                logEntry.data_received.add_callback(self.logDataSignal.emit)
                logEntry.error.add_callback(self.loggingError)
            else:
                logger.warning("Could not setup log configuration!")

        # TODO: Make this pretty ?
        if (len(self.logEntrys) > 0):
            # self.newLogSetupSelected(self.dataSelector.currentIndex())
            self.dataSelector.currentIndexChanged.emit(0)

    def logDataReceived(self, data, timestamp):
        try:
            dataIndex = 0
            s = "%d," % timestamp
            for d in data:
                self.datasets[dataIndex].addData(data[d])
                s += str(data[d]) + ","
                dataIndex += 1
            s += '\n'
            if (self.saveFile != None):
                self.saveFile.write(s)
        except Exception as e:
            # When switching what to log we might still get logging packets...
            # and that will not be pretty so let's just ignore the problem ;-)
            logger.warning("Exception for plot data: %s", e)
