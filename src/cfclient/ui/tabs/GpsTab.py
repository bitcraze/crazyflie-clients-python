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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
"""
This tab plots different logging data defined by configurations that has been
pre-configured.
"""
import logging

import cfclient
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QMessageBox
from cfclient.ui.tab import Tab
from cflib.crazyflie.log import LogConfig
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtNetwork
from PyQt5 import QtWebKit
from PyQt5 import uic

__author__ = 'Bitcraze AB'
__all__ = ['GpsTab']

logger = logging.getLogger(__name__)

gps_tab_class = uic.loadUiType(cfclient.module_path +
                               "/ui/tabs/gpsTab.ui")[0]


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

        view = self.view = QtWebKit.QWebView()

        cache = QtNetwork.QNetworkDiskCache()
        cache.setCacheDirectory(cfclient.config_path + "/cache")
        view.page().networkAccessManager().setCache(cache)
        view.page().networkAccessManager()

        view.page().mainFrame().addToJavaScriptWindowObject("MainWindow", self)
        view.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        view.load(QtCore.QUrl(cfclient.module_path + "/resources/map.html"))
        view.loadFinished.connect(self.onLoadFinished)
        view.linkClicked.connect(QtGui.QDesktopServices.openUrl)

        self.map_layout.addWidget(view)

        self._reset_max_btn.clicked.connect(self._reset_max)

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

        self._max_speed = 0.0
        self._lat = 0
        self._long = 0

    def onLoadFinished(self):
        with open(cfclient.module_path + "/resources/map.js", 'r') as f:
            frame = self.view.page().mainFrame()
            frame.evaluateJavaScript(f.read())

    @QtCore.pyqtSlot(float, float)
    def onMapMove(self, lat, lng):
        return

    def panMap(self, lng, lat):
        frame = self.view.page().mainFrame()
        frame.evaluateJavaScript('map.panTo(L.latLng({}, {}));'.format(lat,
                                                                       lng))

    def _place_cf(self, lng, lat, acc):
        frame = self.view.page().mainFrame()
        frame.evaluateJavaScript('cf.setLatLng([{}, {}]);'.format(lat, lng))

    def _connected(self, link_uri):
        lg = LogConfig("GPS", 1000)
        lg.add_variable("gps.lat")
        lg.add_variable("gps.lon")
        lg.add_variable("gps.hAcc")
        lg.add_variable("gps.hMSL")
        lg.add_variable("gps.nsat")
        self._cf.log.add_config(lg)
        if lg.valid:
            lg.data_received_cb.add_callback(self._log_data_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        else:
            logger.warning("Could not setup logging block for GPS!")
        self._max_speed = 0.0

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        return

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(self, "Plot error", "Error when starting log config"
                          " [%s]: %s" % (log_conf.name, msg))

    def _reset_max(self):
        """Callback from reset button"""
        self._max_speed = 0.0
        self._speed_max.setText(str(self._max_speed))
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

        if self._lat != lat or self._long != long:
            self._long.setText("{:.6f}".format(long))
            self._lat.setText("{:.6f}".format(lat))
            self._nbr_locked_sats.setText(str(data["gps.nsat"]))
            self._height.setText("{:.2f}".format(float(data["gps.hMSL"])))
            self._place_cf(long, lat, 1)
            self._lat = lat
            self._long = long
