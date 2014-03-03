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
__all__ = ['GpsTab']

import glob
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from pprint import pprint
import datetime

#from cfclient.ui.widgets.plotwidget import PlotWidget

from cflib.crazyflie.log import Log, LogVariable, LogConfig

from cfclient.ui.tab import Tab

from PyQt4.QtCore import *
from PyQt4.QtGui import *

try:
    from PyKDE4.marble import *
    should_enable_tab = True
except:
    should_enable_tab = False

import sys

gps_tab_class = uic.loadUiType(sys.path[0] +
                                "/cfclient/ui/tabs/gpsTab.ui")[0]

class GpsTab(Tab, gps_tab_class):
    """Tab for plotting logging data"""

    _log_data_signal = pyqtSignal(int, object, object)
    _log_error_signal = pyqtSignal(object, str)

    _disconnected_signal = pyqtSignal(str)
    _connected_signal = pyqtSignal(str)
    _console_signal = pyqtSignal(str)


    def __init__(self, tabWidget, helper, *args):
        super(GpsTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "GPS"
        self.menuName = "GPS"

        self.tabWidget = tabWidget
        self.helper = helper
        self._cf = helper.cf
        self._got_home_point = False
        self._line = ""

        if not should_enable_tab:
            self.enabled = False

        if self.enabled:
           # create the marble widget
            self._marble = Marble.MarbleWidget()

            # Load the OpenStreetMap map
            self._marble.setMapThemeId("earth/openstreetmap/openstreetmap.dgml")

            # Enable the cloud cover and enable the country borders
            self._marble.setShowClouds(True)
            self._marble.setShowBorders(True)

            # Hide the FloatItems: Compass and StatusBar
            self._marble.setShowOverviewMap(False)
            self._marble.setShowScaleBar(False)
            self._marble.setShowCompass(False)

            # Change the map to center on Australia

            self._marble.zoomView(10)

            # create the slider
            self.zoomSlider = QSlider(Qt.Horizontal)
            # set the limits of the slider
            #self.zoomSlider.setMinimum(1)
            #self.zoomSlider.setMaximum(5000)
            # set a default zoom value
            #self.zoomSlider.setValue(1200)

            # add all the components
            self.gpslayout.addWidget(self._marble)

            # Connect the signals
            self._log_data_signal.connect(self._log_data_received)
            self._log_error_signal.connect(self._logging_error)
            self._connected_signal.connect(self._connected)
            self._disconnected_signal.connect(self._disconnected)
            self._console_signal.connect(self._console_data)

            # Connect the callbacks from the Crazyflie API
            self.helper.cf.disconnected.add_callback(
                self._disconnected_signal.emit)
            self.helper.cf.connected.add_callback(
                self._connected_signal.emit)

            self.helper.cf.console.receivedChar.add_callback(self._console_signal.emit)
        else:
            logger.warning("GPS tab not enabled since no Python"
                           "bindings for Marble was found")

    def _connected(self, link_uri):
        lg = LogConfig("GPS", 1000)
        lg.add_variable("gps.lat", "float")
        lg.add_variable("gps.long", "float")
        lg.add_variable("gps.alt", "float")
        self._cf.log.add_config(lg)
        if lg.valid:
            lg.data_received_cb.add_callback(self._log_data_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        else:
            logger.warning("Could not setup logging block for GPS!")

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        self._got_home_point = False
        return

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(self, "Plot error", "Error when starting log config"
                " [%s]: %s" % (log_conf.name, msg))

    def _console_data(self, s):

        # For simulation don't use two sources, just return here unless
        # you are actually connecting to a Crazyflie

        return

        self._line += s

        if self._line[-1:] == '\n':
            try:
                parts = self._line.split(",")
                if len(parts) > 1:
                    if "$GPGGA" in parts[0]:
                        #logger.info(self._line)
                        if int(parts[6]) > 0:
                            d = {}

                            d["gps.long"] = float(parts[4][0:3])
                            d["gps.long"] += float(parts[4][3:])/60.0

                            d["gps.lat"] = float(parts[2][0:2])
                            d["gps.lat"] += float(parts[2][2:])/60.0

                            d["gps.alt"] = float(parts[11])

                            #logger.info("Calc long: %.6f", d["gps.long"])
                            #logger.info("Calc lat: %.6f", d["gps.lat"])
                            #logger.info("Calc alt: %.6f", d["gps.alt"])

                            self._log_data_received(0, d, None) # Not ok...
                self._line = ""
            except:
                self._line = ""


    def _log_data_received(self, timestamp, data, logconf):
        """Callback when the log layer receives new data"""

        long = float(data["gps.long"])
        lat = float(data["gps.lat"])
        alt = float(data["gps.alt"])

        point = Marble.GeoDataCoordinates(long, lat, alt,
                                             Marble.GeoDataCoordinates.Degree)
        if not self._got_home_point:
            self._got_home_point = True

            self._marble.centerOn(point, True)
            self._marble.zoomView(4000, Marble.Jump)

            self._cf_marker = Marble.GeoDataPlacemark("Crazyflie")
            self._doc = Marble.GeoDataDocument()
            self._doc.append(self._cf_marker)
            self._marble.model().treeModel().addDocument(self._doc)

        self._cf_marker.setCoordinate(point)
        self._marble.model().treeModel().updateFeature(self._cf_marker)