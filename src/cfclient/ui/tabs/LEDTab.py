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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.

"""
Basic tab to be able to set (and test) colors in the LED-ring.
"""

import logging

from PyQt5 import QtGui, uic
from PyQt5.QtCore import pyqtSignal

import cfclient
from cfclient.ui.tab import Tab

from cflib.crazyflie.mem import MemoryElement

__author__ = 'Bitcraze AB'
__all__ = ['LEDTab']

logger = logging.getLogger(__name__)

led_tab_class = uic.loadUiType(cfclient.module_path +
                               "/ui/tabs/ledTab.ui")[0]


class LEDTab(Tab, led_tab_class):
    """Tab for plotting logging data"""

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(LEDTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "LED"
        self.menuName = "LED tab"
        self.tabWidget = tabWidget

        self._helper = helper

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._btns = [self._u1,
                      self._u2,
                      self._u3,
                      self._u4,
                      self._u5,
                      self._u6,
                      self._u7,
                      self._u8,
                      self._u9,
                      self._u10,
                      self._u11,
                      self._u12]

        self._intensity = self._intensity_slider.value()

        self._u1.clicked.connect(lambda: self._select(0))
        self._u2.clicked.connect(lambda: self._select(1))
        self._u3.clicked.connect(lambda: self._select(2))
        self._u4.clicked.connect(lambda: self._select(3))
        self._u5.clicked.connect(lambda: self._select(4))
        self._u6.clicked.connect(lambda: self._select(5))
        self._u7.clicked.connect(lambda: self._select(6))
        self._u8.clicked.connect(lambda: self._select(7))
        self._u9.clicked.connect(lambda: self._select(8))
        self._u10.clicked.connect(lambda: self._select(9))
        self._u11.clicked.connect(lambda: self._select(10))
        self._u12.clicked.connect(lambda: self._select(11))

        self._mem = None

        self._intensity_slider.valueChanged.connect(self._intensity_change)
        self._intensity_slider.valueChanged.connect(
            self._intensity_spin.setValue)
        self._intensity_spin.valueChanged.connect(
            self._intensity_slider.setValue)

    def _select(self, nbr):
        col = QtGui.QColor()  # default to invalid

        if self._mem:
            led = self._mem.leds[nbr]
            col = QtGui.QColor.fromRgb(led.r, led.g, led.b)

        col = QtGui.QColorDialog.getColor(col)

        if col.isValid() and self._mem:
            logger.info(col.red())
            self._mem.leds[nbr].set(r=col.red(), g=col.green(), b=col.blue())
            self.sender().setStyleSheet("background-color: rgb({},{},{})"
                                        .format(col.red(), col.green(),
                                                col.blue()))
            self._write_led_output()

    def _intensity_change(self, value):
        self._intensity = value
        self._write_led_output()

    def _write_led_output(self):
        if self._mem:
            for led in self._mem.leds:
                led.intensity = self._intensity
            self._mem.write_data(self._led_write_done)
        else:
            logger.info("No LED-ring memory found!")

    def _led_write_done(self, mem, addr):
        logger.info("LED write done callback")

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        mems = self._helper.cf.mem.get_mems(MemoryElement.TYPE_DRIVER_LED)
        if len(mems) > 0:
            self._mem = mems[0]
            logger.info(self._mem)

        if self._mem:
            for btn in self._btns:
                btn.setEnabled(True)
                btn.setStyleSheet("background-color: black")
                self._intensity_slider.setEnabled(True)
                self._intensity_spin.setEnabled(True)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        for btn in self._btns:
            btn.setEnabled(False)
            btn.setStyleSheet("background-color: none")
            self._intensity_slider.setEnabled(False)
            self._intensity_spin.setEnabled(False)
            self._intensity_slider.setValue(100)
