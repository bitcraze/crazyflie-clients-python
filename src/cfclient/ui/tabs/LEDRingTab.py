#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2025 Bitcraze AB
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

from PyQt6 import QtGui, uic
from PyQt6.QtCore import pyqtSignal
from PyQt6 import QtWidgets

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox

from cflib.crazyflie.mem import MemoryElement

__author__ = 'Bitcraze AB'
__all__ = ['LEDRingTab']

logger = logging.getLogger(__name__)

led_ring_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/ledRingTab.ui")[0]


class LEDRingTab(TabToolbox, led_ring_tab_class):
    """Tab for plotting logging data"""

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)

    def __init__(self, helper):
        super(LEDRingTab, self).__init__(helper, 'LED Ring')
        self.setupUi(self)

        # LED-ring effect dropdown and headlight checkbox
        self._ledring_nbr_effects = 0

        # Connect the headlight checkbox
        self._led_ring_headlight.clicked.connect(
            lambda enabled: self._helper.cf.param.set_value("ring.headlightEnable", int(enabled)))

        # Update headlight when param changes
        self._helper.cf.param.add_update_callback(
            group="ring", name="headlightEnable",
            cb=lambda name, checked: self._led_ring_headlight.setChecked(bool(int(checked))))

        # Update LED-ring effect when param changes
        self._helper.cf.param.add_update_callback(
            group="ring", name="effect",
            cb=self._ring_effect_updated)

        # Populate dropdown when all params are updated
        self._helper.cf.param.all_updated.add_callback(self._ring_populate_dropdown)

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

        self._helper.inputDeviceReader.alt1_updated.add_callback(self.alt1_updated)
        self._helper.inputDeviceReader.alt2_updated.add_callback(self.alt2_updated)

        self._led_ring_effect.setEnabled(False)
        self._led_ring_headlight.setEnabled(False)

    def _select(self, nbr):
        col = QtGui.QColor()

        if self._mem:
            led = self._mem.leds[nbr]
            col = QtGui.QColor.fromRgb(led.r, led.g, led.b)

        col = QtWidgets.QColorDialog.getColor(col)

        if col.isValid() and self._mem:
            r, g, b = col.red(), col.green(), col.blue()
            self._mem.leds[nbr].set(r=r, g=g, b=b)

            brightness = 0.299 * r + 0.587 * g + 0.114 * b
            text_color = "white" if brightness < 128 else "black"

            self.sender().setStyleSheet(
                f"background-color: rgb({r}, {g}, {b}); color: {text_color};"
            )

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
                btn.setStyleSheet("background-color: black; color: white")
                self._intensity_slider.setEnabled(True)
                self._intensity_spin.setEnabled(True)

        self._led_ring_effect.setEnabled(True)
        self._led_ring_headlight.setEnabled(True)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        for btn in self._btns:
            btn.setEnabled(False)
            btn.setStyleSheet("background-color: none")
            self._intensity_slider.setEnabled(False)
            self._intensity_spin.setEnabled(False)
            self._intensity_slider.setValue(100)

        self._led_ring_effect.setEnabled(False)
        self._led_ring_headlight.setEnabled(False)

    def _ring_populate_dropdown(self):
        try:
            nbr = int(self._helper.cf.param.values["ring"]["neffect"])
            current = int(self._helper.cf.param.values["ring"]["effect"])
        except KeyError:
            return

        self._ring_effect = current
        self._ledring_nbr_effects = nbr

        hardcoded_names = {
            0: "Off",
            1: "White spinner",
            2: "Color spinner",
            3: "Tilt effect",
            4: "Brightness effect",
            5: "Color spinner 2",
            6: "Double spinner",
            7: "Solid color effect",
            8: "Factory test",
            9: "Battery status",
            10: "Boat lights",
            11: "Alert",
            12: "Gravity",
            13: "LED tab",
            14: "Color fader",
            15: "Link quality",
            16: "Location server status",
            17: "Sequencer",
            18: "Lighthouse quality",
        }

        self._led_ring_effect.clear()
        for i in range(nbr + 1):
            name = "{}: ".format(i)
            name += hardcoded_names.get(i, "N/A")
            self._led_ring_effect.addItem(name, i)

        self._led_ring_effect.currentIndexChanged.connect(self._ring_effect_changed)
        self._led_ring_effect.setCurrentIndex(current)
        self._led_ring_effect.setEnabled(int(self._helper.cf.param.values["deck"]["bcLedRing"]) == 1)
        self._led_ring_headlight.setEnabled(int(self._helper.cf.param.values["deck"]["bcLedRing"]) == 1)

        try:
            self._helper.cf.param.set_value("ring.effect", "13")
            self._led_ring_effect.setCurrentIndex(13)
            self._ring_effect = 13
            logger.info("Initialized LED ring to 'LED tab' mode (effect 13).")
        except Exception as e:
            logger.warning(f"Could not set LED tab effect on connect: {e}")

    def _ring_effect_changed(self, index):
        self._ring_effect = index
        if index > -1:
            i = self._led_ring_effect.itemData(index)
            if i != int(self._helper.cf.param.values["ring"]["effect"]):
                self._helper.cf.param.set_value("ring.effect", str(i))

            if i == 13:
                self._intensity_slider.setEnabled(True)
                self._intensity_spin.setEnabled(True)
            else:
                self._intensity_slider.setEnabled(False)
                self._intensity_spin.setEnabled(False)

    def _ring_effect_updated(self, name, value):
        if self._helper.cf.param.is_updated:
            self._led_ring_effect.setCurrentIndex(int(value))

    def alt1_updated(self, state):
        if state:
            new_index = (self._ring_effect+1) % (self._ledring_nbr_effects+1)
            self._helper.cf.param.set_value("ring.effect", str(new_index))

    def alt2_updated(self, state):
        self._helper.cf.param.set_value("ring.headlightEnable", str(state))
