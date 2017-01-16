#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2017 Bitcraze AB
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.

"""
Shows data for the Loco Positioning system
"""

import logging

from PyQt4 import uic
from PyQt4.QtCore import pyqtSignal
from PyQt4.QtGui import QMessageBox

import cfclient
from cfclient.ui.tab import Tab

from cfclient.utils.config import Config
from cflib.crazyflie.log import LogConfig

__author__ = 'Bitcraze AB'
__all__ = ['LocoPositioningTab']

logger = logging.getLogger(__name__)

locopositioning_tab_class = uic.loadUiType(
    cfclient.module_path + "/ui/tabs/locopositioning_tab.ui")[0]


class LocoPositioningTab(Tab, locopositioning_tab_class):
    """Tab for plotting Loco Positioning data"""

    # TODO krri make instance variables
    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_error_signal = pyqtSignal(object, str)
    _anchor_range_signal = pyqtSignal(int, object, object)

    def __init__(self, tabWidget, helper, *args):
        super(LocoPositioningTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Loco Positioning"
        self.menuName = "Loco Positioning Tab"
        self.tabWidget = tabWidget

        self._helper = helper

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._anchor_range_signal.connect(self._anchor_range_received)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.debug("Crazyflie connected to {}".format(link_uri))

        lg = LogConfig("LoPo", Config().get("ui_update_period"))
        lg.add_variable("ranging.distance1", "float")
        lg.add_variable("ranging.distance2", "float")
        lg.add_variable("ranging.distance3", "float")
        lg.add_variable("ranging.distance4", "float")
        lg.add_variable("ranging.distance5", "float")
        lg.add_variable("ranging.distance6", "float")
        # lg.add_variable("ranging.distance7", "float")
        # lg.add_variable("ranging.distance8", "float")

        try:
            self._helper.cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self._anchor_range_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""

        logger.debug("Crazyflie disconnected from {}".format(link_uri))

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""

        QMessageBox.about(self, "LocoPositioningTab error",
                          "Error when using log config"
                          " [{0}]: {1}".format(log_conf.name, msg))

    def _anchor_range_received(self, timestamp, data, logconf):
        self.anchor1_distance.setValue(data['ranging.distance1'] * 10)
        self.anchor2_distance.setValue(data['ranging.distance2'] * 10)
        self.anchor3_distance.setValue(data['ranging.distance3'] * 10)
        self.anchor4_distance.setValue(data['ranging.distance4'] * 10)
        self.anchor5_distance.setValue(data['ranging.distance5'] * 10)
        self.anchor6_distance.setValue(data['ranging.distance6'] * 10)
        # self.anchor7_distance.setValue(data['ranging.distance7'] * 10)
        # self.anchor8_distance.setValue(data['ranging.distance8'] * 10)
