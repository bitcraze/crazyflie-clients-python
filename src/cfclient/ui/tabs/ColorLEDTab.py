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
Basic tab to be able to set (and test) color in Color LED.
"""

import logging
from PyQt6 import uic, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QPainter, QLinearGradient, QPen, QPainterPath
from PyQt6.QtWidgets import QPushButton, QMessageBox

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox

__author__ = 'Bitcraze AB'
__all__ = ['ColorLEDTab']

logger = logging.getLogger(__name__)

color_led_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/colorLEDTab.ui")[0]


class ColorLEDTab(TabToolbox, color_led_tab_class):
    """Tab with inline color picker with hue slider, SV area, and hex input."""

    _colorChanged = pyqtSignal(QColor)

    def __init__(self, helper):
        super(ColorLEDTab, self).__init__(helper, 'Color LED')
        self.setupUi(self)

        is_connected = True
        self.groupBox_color.setEnabled(is_connected)
        self.hue_bar.setEnabled(is_connected)

        self._populate_position_dropdown()

        self._hue = 0
        self._saturation = 1
        self._value = 1


        self.hue_bar.setMinimum(0)
        self.hue_bar.setMaximum(1000)
        self.hue_bar.setValue(int(self._hue * 1000))
        self.hue_bar.valueChanged.connect(self._on_hue_slider_changed)
        self.hue_bar.setMouseTracking(True)

        self.hex_input.editingFinished.connect(self._on_hex_changed)

        self.custom_color_buttons = []
        self._connect_color_buttons()

        self.add_color_button.clicked.connect(self._add_custom_color_button)

        self.sv_area.setMouseTracking(True)
        self.sv_area.setStyleSheet("""
            QLabel {
                border-radius: 8px;
                border: 1px solid #444;
                background-color: #222;
            }
        """)

    def _populate_position_dropdown(self):

        self.positionDropdown.addItem("Bottom", 0)
        self.positionDropdown.addItem("Top", 1)
        self.positionDropdown.addItem("Both", 2)

        # is_bottom_attached = int(self._helper.cf.param.values["deck"]["bottomColorLed"])
        # is_top_attached = int(self._helper.cf.param.values["deck"]["topColorLed"])
        is_bottom_attached = False
        is_top_attached = True

        if is_bottom_attached and is_top_attached:
            self.positionDropdown.model().item(0).setEnabled(True)
            self.positionDropdown.model().item(1).setEnabled(True)
            self.positionDropdown.model().item(2).setEnabled(True)
            self.positionDropdown.setCurrentIndex(2)
        elif is_bottom_attached:
            self.positionDropdown.model().item(0).setEnabled(True)
            self.positionDropdown.model().item(1).setEnabled(False)
            self.positionDropdown.model().item(2).setEnabled(False)
            self.positionDropdown.setCurrentIndex(0)
        elif is_top_attached:
            self.positionDropdown.model().item(0).setEnabled(False)
            self.positionDropdown.model().item(1).setEnabled(True)
            self.positionDropdown.model().item(2).setEnabled(False)
            self.positionDropdown.setCurrentIndex(1)
        else:
            self.positionDropdown.model().item(0).setEnabled(False)
            self.positionDropdown.model().item(1).setEnabled(False)
            self.positionDropdown.model().item(2).setEnabled(False)

    def showEvent(self, event):
        """ Show event for proper initial SV area sizing """
        super().showEvent(event)
        self._update_sv_area(self.sv_area, self._hue)
        self._update_preview()

    def mousePressEvent(self, event):
        self._handle_mouse_event(event)

    def mouseMoveEvent(self, event):
        self._handle_mouse_event(event)

    def _handle_mouse_event(self, event):
        if not self.groupBox_color.isEnabled():
            return
        sv_pos = self.sv_area.mapFrom(self, event.pos())
        if self.sv_area.rect().contains(sv_pos):
            self._update_sv_from_pos(sv_pos)

    def _update_sv_from_pos(self, pos):
        x = pos.x()
        y = pos.y()
        w = self.sv_area.width()
        h = self.sv_area.height()

        self._saturation = max(0, min(1, x / w))
        self._value = 1 - max(0, min(1, y / h))
        self._update_preview()
        self._update_sv_area(self.sv_area, self._hue)

    def _update_sv_area(self, sv_area, hue):
        width = sv_area.width()
        height = sv_area.height()
        if width <= 0 or height <= 0:
            return

        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        """ Rounded corners """
        path = QPainterPath()
        corner_radius = 8
        path.addRoundedRect(0, 0, width, height, corner_radius, corner_radius)
        painter.setClipPath(path)

        """ Base hue layer """
        base_color = QColor.fromHsvF(hue, 1, 1)
        painter.fillRect(pixmap.rect(), base_color)

        """ Saturation overlay (white → transparent) """
        sat_gradient = QLinearGradient(0, 0, width, 0)
        sat_gradient.setColorAt(0, Qt.GlobalColor.white)
        sat_gradient.setColorAt(1, Qt.GlobalColor.transparent)
        painter.fillRect(pixmap.rect(), sat_gradient)

        """ Value overlay (transparent → black) """
        val_gradient = QLinearGradient(0, 0, 0, height)
        val_gradient.setColorAt(0, Qt.GlobalColor.transparent)
        val_gradient.setColorAt(1, Qt.GlobalColor.black)
        painter.fillRect(pixmap.rect(), val_gradient)

        """ Outline """
        outline_pen = QPen(Qt.GlobalColor.darkGray)
        outline_pen.setWidth(1)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        """ Circle selector """
        sel_x = int(self._saturation * width)
        sel_y = int((1 - self._value) * height)
        selector_radius = 6
        pen = QPen(Qt.GlobalColor.white)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(sel_x - selector_radius, sel_y - selector_radius, selector_radius * 2, selector_radius * 2)

        painter.end()
        sv_area.setPixmap(pixmap)

    def _on_hue_slider_changed(self, value):
        if not self.groupBox_color.isEnabled():
            return
        self._hue = value / 1000
        self._update_sv_area(self.sv_area, self._hue)
        self._update_preview()

    def _update_preview(self):
        color = QColor.fromHsvF(self._hue, self._saturation, self._value)
        self.color_preview.setStyleSheet(f"""
        QFrame#color_preview {{
            border: 1px solid #444;
            border-radius: 4px;
        }}

        QFrame#color_preview:enabled {{
            background-color: {color.name()};
        }}

        QFrame#color_preview:disabled {{
            background-color: #777777;  /* greyed out when disconnected */
        }}
        """)
        self.hex_input.setText(color.name().upper())
        self._colorChanged.emit(color)

    def _on_hex_changed(self):
        if not self.groupBox_color.isEnabled():
            return
        hex_value = self.hex_input.text().strip()
        color = QColor(hex_value)
        if color.isValid():
            h, s, v, _ = color.getHsvF()
            self._hue, self._saturation, self._value = h, s, v
            self.hue_bar.setValue(int(self._hue * 1000))
            self._update_sv_area(self.sv_area, self._hue)
            self._update_preview()
            self.hex_input.setStyleSheet("")
            self.hex_error_label.setText("")
            self.information_text.setText("")
        else:
            self.hex_input.setStyleSheet("border: 2px solid red; border-radius: 4px;")
            self.hex_error_label.setText("Invalid hex code.")
            self.information_text.setText("Throttling: Lowering intensity to lower temperature.")
            logger.warning(f"Invalid HEX color: {hex_value}")

    def _connect_color_buttons(self):
        color_buttons = [
            self.color_button1,
            self.color_button2,
            self.color_button3,
            self.color_button4,
            self.color_button5,
            self.color_button6,
            self.color_button7,
            self.color_button8,
            self.color_button9,
            self.color_button10,
        ]
        for btn in color_buttons:
            btn.clicked.connect(self._on_color_button_clicked)

    def _on_color_button_clicked(self):
        if not self.groupBox_color.isEnabled():
            return
        button = self.sender()
        style = button.styleSheet()
        if "background-color:" not in style:
            return
        hex_color = style.split("background-color:")[-1].split(";")[0].strip()
        color = QColor(hex_color)
        if color.isValid():
            h, s, v, _ = color.getHsvF()
            self._hue, self._saturation, self._value = h, s, v
            self.hue_bar.setValue(int(self._hue * 1000))
            self._update_sv_area(self.sv_area, self._hue)
            self._update_preview()

    def _add_custom_color_button(self):
        color_hex = self.hex_input.text().strip()
        if not color_hex.startswith("#"):
            color_hex = "#" + color_hex

        color = QColor(color_hex)
        if not color.isValid():
            logger.warning(f"Invalid custom color: {color_hex}")
            return

        new_btn = QPushButton()
        new_btn.setStyleSheet(f"background-color: {color_hex};")
        new_btn.setFixedSize(50, 30)
        new_btn.clicked.connect(self._on_color_button_clicked)
        new_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        new_btn.customContextMenuRequested.connect(lambda pos, btn=new_btn: self._remove_custom_color_button(btn))

        self.custom_color_buttons.append(new_btn)

        self._repack_custom_buttons()
        logger.info(f"Added new custom color {color_hex}")

    def _remove_custom_color_button(self, button):
        reply = QMessageBox.question(
            self,
            "Remove Custom Color",
            "Do you want to remove this custom color?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if button in self.custom_color_buttons:
                self.custom_color_buttons.remove(button)
            button.setParent(None)
            button.deleteLater()
            logger.info("Removed custom color button.")

            self._repack_custom_buttons()

    def _repack_custom_buttons(self):
        grid = self.gridLayout_5
        plus_button = self.add_color_button

        total_cols = 8
        row, col = 0, 0

        preset_buttons = [
            self.color_button1,
            self.color_button2,
            self.color_button3,
            self.color_button4,
            self.color_button5,
            self.color_button6,
            self.color_button7,
            self.color_button8,
            self.color_button9,
            self.color_button10,
        ]

        for btn in self.custom_color_buttons + [plus_button]:
            grid.removeWidget(btn)

        for btn in preset_buttons:
            grid.addWidget(btn, row, col)
            col += 1
            if col >= total_cols:
                col = 0
                row += 1

        for btn in self.custom_color_buttons:
            grid.addWidget(btn, row, col)
            col += 1
            if col >= total_cols:
                col = 0
                row += 1

        grid.addWidget(plus_button, row, col)
