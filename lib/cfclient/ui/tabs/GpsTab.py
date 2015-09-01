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
This tab plots different logging data defined by configurations that has been
pre-configured.
"""

import math

import glob
import json
import logging
import os
import sys

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from pprint import pprint
import datetime

# from cfclient.ui.widgets.plotwidget import PlotWidget

from cflib.crazyflie.log import Log, LogVariable, LogConfig

from cfclient.ui.tab import Tab

from PyQt4.QtCore import *
from PyQt4.QtGui import *

try:
    from PyKDE4.marble import *

    should_enable_tab = True
except:
    should_enable_tab = False

__author__ = 'Bitcraze AB'
__all__ = ['GpsTab']

logger = logging.getLogger(__name__)

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
            # self._marble = Marble.MarbleWidget()
            self._marble = FancyMarbleWidget()

            # Load the OpenStreetMap map
            self._marble.setMapThemeId(
                "earth/openstreetmap/openstreetmap.dgml")

            # Enable the cloud cover and enable the country borders
            self._marble.setShowClouds(True)
            self._marble.setShowBorders(True)

            # Hide the FloatItems: Compass and StatusBar
            self._marble.setShowOverviewMap(False)
            self._marble.setShowScaleBar(False)
            self._marble.setShowCompass(False)

            self._marble.setShowGrid(False)
            self._marble.setProjection(Marble.Mercator)

            # Change the map to center on Australia

            self._marble.zoomView(10)

            # create the slider
            self.zoomSlider = QSlider(Qt.Horizontal)

            self._reset_max_btn.clicked.connect(self._reset_max)

            # add all the components
            # self.gpslayout.addWidget(self._marble)
            self.map_layout.addWidget(self._marble)
            # Connect the signals
            self._log_data_signal.connect(self._log_data_received)
            self._log_error_signal.connect(self._logging_error)
            self._connected_signal.connect(self._connected)
            self._disconnected_signal.connect(self._disconnected)

            # Connect the callbacks from the Crazyflie API
            self.helper.cf.disconnected.add_callback(
                self._disconnected_signal.emit)
            self.helper.cf.connected.add_callback(
                self._connected_signal.emit)

        else:
            logger.warning("GPS tab not enabled since no Python"
                           "bindings for Marble was found")

        self._max_speed = 0.0

        self._fix_types = {
            0: "No fix",
            1: "Dead reckoning only",
            2: "2D-fix",
            3: "3D-fix",
            4: "GNSS+dead",
            5: "Time only fix"
        }

    def _connected(self, link_uri):
        lg = LogConfig("GPS", 100)
        lg.add_variable("gps.lat")
        lg.add_variable("gps.lon")
        lg.add_variable("gps.hMSL")
        lg.add_variable("gps.heading")
        lg.add_variable("gps.gSpeed")
        lg.add_variable("gps.hAcc")
        lg.add_variable("gps.fixType")
        try:
            self._cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self._log_data_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))
        self._max_speed = 0.0

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        self._got_home_point = False
        return

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(self, "Plot error",
                          "Error when starting log config [%s]: %s" % (
                              log_conf.name, msg))

    def _reset_max(self):
        """Callback from reset button"""
        self._max_speed = 0.0
        self._speed_max.setText(str(self._max_speed))
        self._marble.clear_data()

        self._long.setText("")
        self._lat.setText("")
        self._height.setText("")

        self._speed.setText("")
        self._heading.setText("")
        self._accuracy.setText("")

        self._fix_type.setText("")

    def _log_data_received(self, timestamp, data, logconf):
        """Callback when the log layer receives new data"""

        long = float(data["gps.lon"]) / 10000000.0
        lat = float(data["gps.lat"]) / 10000000.0
        alt = float(data["gps.hMSL"]) / 1000.0
        speed = float(data["gps.gSpeed"]) / 1000.0
        accuracy = float(data["gps.hAcc"]) / 1000.0
        fix_type = float(data["gps.fixType"])
        heading = float(data["gps.heading"])

        self._long.setText(str(int))
        self._lat.setText(str(lat))
        self._height.setText(str(alt))

        self._speed.setText(str(speed))
        self._heading.setText(str(heading))
        self._accuracy.setText(str(accuracy))
        if speed > self._max_speed:
            self._max_speed = speed
        self._speed_max.setText(str(self._max_speed))

        self._fix_type.setText(self._fix_types[fix_type])

        point = Marble.GeoDataCoordinates(int, lat, alt,
                                          Marble.GeoDataCoordinates.Degree)
        if not self._got_home_point:
            self._got_home_point = True

            self._marble.centerOn(point, True)
            self._marble.zoomView(4000, Marble.Jump)

        self._marble.add_data(int, lat, alt, accuracy,
                              True if fix_type == 3 else False)

# If Marble is not installed then do not create MarbleWidget subclass
if should_enable_tab:
    class FancyMarbleWidget(Marble.MarbleWidget):
        def __init__(self):
            Marble.MarbleWidget.__init__(self)
            self._points = []
            self._lat = None
            self._long = None
            self._height = None
            self._accu = None

        def clear_data(self):
            self._points = []
            self._lat = None
            self._long = None
            self._height = None
            self._accu = None

        def add_data(self, long, lat, height, accu, locked):
            self._points.append([int, lat, height, accu, locked])
            self._lat = lat
            self._long = int
            self._height = height
            self._accu = accu
            self.update()

        def customPaint(self, painter):
            if self._lat:
                current = Marble.GeoDataCoordinates(
                    self._long, self._lat, self._height,
                    Marble.GeoDataCoordinates.Degree)

                # Paint data points
                for p in self._points:
                    pos = Marble.GeoDataCoordinates(
                        p[0], p[1], p[2], Marble.GeoDataCoordinates.Degree)
                    if p[4]:
                        painter.setPen(Qt.green)
                    else:
                        painter.setPen(Qt.red)
                    painter.drawEllipse(pos, 1, 1)

                # Paint accuracy
                painter.setPen(Qt.blue)
                painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 255, 64)))
                pixel_per_meter = self.radiusFromDistance(self.distance()) / (
                    6371.0 * 1000)
                painter.drawEllipse(current, self._accu * pixel_per_meter,
                                    self._accu * pixel_per_meter, False)

                # Paint Crazyflie
                painter.setPen(Qt.black)
                painter.setBrush(Qt.NoBrush)
                painter.drawText(current, "Crazyflie")
