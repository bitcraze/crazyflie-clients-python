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

from __future__ import annotations

import logging

from PySide6 import QtGui
from PySide6.QtUiTools import loadUiType
from PySide6 import QtWidgets

import cfclient
from cfclient.gui import create_task
from cfclient.ui.pluginhelper import PluginHelper
from cfclient.ui.tab_toolbox import TabToolbox

from cflib2 import Crazyflie
from cflib2.memory import LedRingColor

__author__ = "Bitcraze AB"
__all__ = ["LEDRingTab"]

logger = logging.getLogger(__name__)

led_ring_tab_class = loadUiType(cfclient.module_path + "/ui/tabs/ledRingTab.ui")[0]

HARDCODED_EFFECT_NAMES = {
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


class LEDRingTab(TabToolbox, led_ring_tab_class):
    """Tab for controlling the Crazyflie LED ring deck"""

    def __init__(self, helper: PluginHelper) -> None:
        super(LEDRingTab, self).__init__(helper, "LED Ring")
        self.setupUi(self)

        self._cf = None
        self._leds = [LedRingColor() for _ in range(12)]

        self._btns = [
            self._u1,
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
            self._u12,
        ]

        for i, btn in enumerate(self._btns):
            btn.clicked.connect(lambda _, idx=i: self._select(idx))

        self._intensity_slider.valueChanged.connect(self._intensity_change)
        self._intensity_slider.valueChanged.connect(self._intensity_spin.setValue)
        self._intensity_spin.valueChanged.connect(self._intensity_slider.setValue)

        self._led_ring_headlight.clicked.connect(self._headlight_clicked)
        self._led_ring_effect.currentIndexChanged.connect(self._ring_effect_changed)

        self._set_ui_connected(False)

    def connected(self, cf: Crazyflie) -> None:
        self._cf = cf
        # Reset LED state to black
        self._leds = [LedRingColor() for _ in range(12)]
        for btn in self._btns:
            btn.setStyleSheet("background-color: black; color: white")
        create_task(self._on_connected())

    def disconnected(self) -> None:
        self._cf = None
        self._set_ui_connected(False)
        self._intensity_slider.setValue(100)
        # Clear dropdown
        self._led_ring_effect.blockSignals(True)
        self._led_ring_effect.clear()
        self._led_ring_effect.blockSignals(False)

    async def _on_connected(self) -> None:
        param = self._cf.param()

        # Check if LED ring deck is present
        try:
            deck_present = int(await param.get("deck.bcLedRing")) == 1
        except Exception:
            deck_present = False

        # Fetch ring params
        try:
            neffect = int(await param.get("ring.neffect"))
            current_effect = int(await param.get("ring.effect"))
            headlight = int(await param.get("ring.headlightEnable"))
        except Exception as e:
            logger.warning("Could not read ring params: %s", e)
            self._set_ui_connected(True)
            return

        # Populate effect dropdown
        self._led_ring_effect.blockSignals(True)
        self._led_ring_effect.clear()
        for i in range(neffect + 1):
            name = f"{i}: {HARDCODED_EFFECT_NAMES.get(i, 'N/A')}"
            self._led_ring_effect.addItem(name, i)
        self._led_ring_effect.blockSignals(False)

        self._set_ui_connected(True)
        self._led_ring_effect.setEnabled(deck_present)
        self._led_ring_headlight.setEnabled(deck_present)

        # Set initial UI state from current param values
        self._led_ring_headlight.blockSignals(True)
        self._led_ring_headlight.setChecked(bool(headlight))
        self._led_ring_headlight.blockSignals(False)

        # Switch to "LED tab" effect (13) and write the current LED state to
        # the deck. On connect this sets the ring to black
        try:
            await param.set("ring.effect", 13)
            await self._cf.memory().write_led_ring(self._leds)
            self._led_ring_effect.blockSignals(True)
            self._led_ring_effect.setCurrentIndex(13)
            self._led_ring_effect.blockSignals(False)
        except Exception as e:
            logger.warning("Could not set LED tab effect: %s", e)
            self._led_ring_effect.blockSignals(True)
            self._led_ring_effect.setCurrentIndex(current_effect)
            self._led_ring_effect.blockSignals(False)

    def _set_ui_connected(self, connected: bool) -> None:
        for btn in self._btns:
            btn.setEnabled(connected)
            if not connected:
                btn.setStyleSheet("background-color: none")
        self._intensity_slider.setEnabled(connected)
        self._intensity_spin.setEnabled(connected)
        self._led_ring_effect.setEnabled(connected)
        self._led_ring_headlight.setEnabled(connected)

    def _select(self, nbr: int) -> None:
        led = self._leds[nbr]
        current_color = QtGui.QColor.fromRgb(led.r, led.g, led.b)
        col = QtWidgets.QColorDialog.getColor(current_color)

        if col.isValid():
            r, g, b = col.red(), col.green(), col.blue()
            self._leds[nbr].set(r=r, g=g, b=b)

            brightness = 0.299 * r + 0.587 * g + 0.114 * b
            text_color = "white" if brightness < 128 else "black"
            self._btns[nbr].setStyleSheet(
                f"background-color: rgb({r}, {g}, {b}); color: {text_color};"
            )

            self._write_led_output()

    def _intensity_change(self, _: int) -> None:
        self._write_led_output()

    def _write_led_output(self) -> None:
        if self._cf is None:
            return
        intensity = self._intensity_slider.value()
        for led in self._leds:
            led.intensity = intensity
        create_task(self._async_write_leds())

    async def _async_write_leds(self) -> None:
        if self._cf is None:
            return
        await self._cf.memory().write_led_ring(self._leds)

    def _headlight_clicked(self, enabled: bool) -> None:
        if self._cf is None:
            return
        create_task(self._async_set_headlight(int(enabled)))

    async def _async_set_headlight(self, value: int) -> None:
        if self._cf is None:
            return
        await self._cf.param().set("ring.headlightEnable", value)

    def _ring_effect_changed(self, index: int) -> None:
        if index < 0 or self._cf is None:
            return
        effect_id = self._led_ring_effect.itemData(index)
        if effect_id is None:
            return
        create_task(self._async_set_effect(effect_id))
        # Enable intensity controls only in LED tab mode (effect 13)
        is_led_tab = effect_id == 13
        self._intensity_slider.setEnabled(is_led_tab)
        self._intensity_spin.setEnabled(is_led_tab)

    async def _async_set_effect(self, effect_id: int) -> None:
        if self._cf is None:
            return
        await self._cf.param().set("ring.effect", effect_id)
        # When switching back to "LED tab" effect, write the current tab state
        # so the colors match what the buttons show
        if effect_id == 13:
            await self._cf.memory().write_led_ring(self._leds)
