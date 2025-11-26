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
from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QPainter, QLinearGradient, QPen, QPainterPath
from PyQt6.QtWidgets import QPushButton, QMessageBox
from cflib.crazyflie.log import LogConfig

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox
from cfclient.utils.config import Config

__author__ = 'Bitcraze AB'
__all__ = ['ColorLEDTab']

logger = logging.getLogger(__name__)

color_led_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/colorLEDTab.ui")[0]  # type: ignore


class wrgb_t:
    def __init__(self, w: int, r: int, g: int, b: int):
        self.w = w
        self.r = r
        self.g = g
        self.b = b

    def pack(self) -> int:
        """Pack WRGB values into uint32 format: 0xWWRRGGBB"""
        return (self.w << 24) | (self.r << 16) | (self.g << 8) | self.b


class rgb_t:
    def __init__(self, r: int, g: int, b: int):
        self.r = r
        self.g = g
        self.b = b

    def __iter__(self):
        return iter([self.r, self.g, self.b])

    def extract_white(self) -> wrgb_t:
        """Extract white channel and return WRGB color"""
        white = min(self.r, self.g, self.b)
        return wrgb_t(white, self.r - white, self.g - white, self.b - white)


class ThermalMonitor:
    """Monitors thermal throttling status for Color LED decks"""

    def __init__(self, helper, params_config, log_data_signal, log_error_signal):
        """
        Initialize thermal monitor

        Args:
            helper: Crazyflie helper instance
            params_config: Dictionary mapping positions to their thermal log names
            log_data_signal: PyQt signal to emit when log data is received
            log_error_signal: PyQt signal to emit when log errors occur
        """
        self._helper = helper
        self._params_config = params_config
        self._log_data_signal = log_data_signal
        self._log_error_signal = log_error_signal
        self._active_positions = []

    def start_monitoring(self, positions):
        """
        Start thermal monitoring for specified deck positions

        Args:
            positions: List of position indices to monitor
        """
        self._active_positions = positions

        for position in positions:
            if position not in self._params_config:
                continue

            params = self._params_config[position]
            log_name = f"Thermal{['Bottom', 'Top'][position]}"
            lg = LogConfig(log_name, Config().get("ui_update_period"))

            try:
                lg.add_variable(params['thermal_log'], "uint8_t")
                self._helper.cf.log.add_config(lg)
                lg.data_received_cb.add_callback(self._log_data_signal.emit)
                lg.error_cb.add_callback(self._log_error_signal.emit)
                lg.start()
                logger.debug(f"Started thermal logging for position {position}: {params['thermal_log']}")
            except (KeyError, AttributeError) as e:
                logger.debug(f"Could not start thermal logging for position {position}: {e}")

    def check_throttling(self, data, positions_to_check):
        """
        Check if any of the specified positions are thermally throttling

        Args:
            data: Log data dictionary
            positions_to_check: List of position indices to check

        Returns:
            bool: True if any position is throttling
        """
        return any(
            self._params_config[pos]['thermal_log'] in data and
            data[self._params_config[pos]['thermal_log']]
            for pos in positions_to_check
            if pos in self._params_config
        )


class ColorLEDDeckController:
    """Manages Color LED deck detection and parameter writes"""

    def __init__(self, helper, params_config):
        """
        Initialize deck controller

        Args:
            helper: Crazyflie helper instance
            params_config: Dictionary mapping positions to their parameter names
        """
        self._helper = helper
        self._params_config = params_config
        self._deck_present = {}  # Maps position -> bool

    def detect_decks(self):
        """Detect which Color LED decks are present"""
        for position, params in self._params_config.items():
            try:
                deck_param = self._helper.cf.param.get_value(params['deck_param'])
                # Convert to int to handle string values like "0" or "1"
                self._deck_present[position] = bool(int(deck_param))
                logger.debug(f"Color LED deck at position {position} ({'Bottom' if position == 0 else 'Top'}) "
                             f"detected: {self._deck_present[position]} (param: {params['deck_param']}={deck_param})")
            except (KeyError, ValueError, TypeError) as e:
                self._deck_present[position] = False
                logger.debug(f"Color LED deck parameter not found for position {position}: {e}")

    def is_deck_present(self, position):
        """Check if deck at given position is present"""
        return self._deck_present.get(position, False)

    def get_present_decks(self):
        """Get list of positions where decks are present"""
        return [pos for pos, present in self._deck_present.items() if present]

    def write_color(self, position, color_uint32):
        """
        Write color to a specific deck position

        Args:
            position: Deck position (0=bottom, 1=top)
            color_uint32: Packed WRGB color value
        """
        if position not in self._params_config:
            logger.warning(f"Unknown position {position}")
            return

        if not self.is_deck_present(position):
            logger.debug(f"Color LED deck at position {position} not present, skipping color write")
            return

        param_name = self._params_config[position]['color']
        self._helper.cf.param.set_value(param_name, str(color_uint32))

    def clear_deck_state(self):
        """Clear deck presence state (called on disconnect)"""
        self._deck_present.clear()


class ColorLEDTab(TabToolbox, color_led_tab_class):
    """Tab with inline color picker with hue slider, SV area, and hex input."""

    _colorChanged = pyqtSignal(QColor)
    _connectedSignal = pyqtSignal(str)
    _disconnectedSignal = pyqtSignal(str)
    _log_data_signal = pyqtSignal(int, object, object)
    _log_error_signal = pyqtSignal(object, str)

    # Parameter and log names by position
    PARAMS_BY_POSITION = {
        0: {  # Bottom
            'color': 'colorLedBot.wrgb8888',
            'thermal_log': 'colorLedBot.throttlePct',
            'brightness': 'colorLedBot.brightCorr',
            'deck_param': 'deck.bcColorLedBot'
        },
        1: {  # Top
            'color': 'colorLedTop.wrgb8888',
            'thermal_log': 'colorLedTop.throttlePct',
            'brightness': 'colorLedTop.brightCorr',
            'deck_param': 'deck.bcColorLedTop'
        }
    }

    def __init__(self, helper):
        super(ColorLEDTab, self).__init__(helper, 'Color LED')
        self.setupUi(self)

        self.groupBox_color.setEnabled(False)
        self.hue_bar.setEnabled(False)

        self._populate_position_dropdown()

        self._hue = 0
        self._saturation = 0
        self._value = 0

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

        self._isConnected = False
        self._updating_from_fetch = False  # Flag to prevent writes during color fetch
        self._throttling_state = {}  # Track last known throttling state per position

        # Initialize thermal monitor and deck controller
        self._thermal_monitor = ThermalMonitor(
            self._helper,
            self.PARAMS_BY_POSITION,
            self._log_data_signal,
            self._log_error_signal
        )
        self._deck_controller = ColorLEDDeckController(
            self._helper,
            self.PARAMS_BY_POSITION
        )

        self._connectedSignal.connect(self._connected)
        self._disconnectedSignal.connect(self._disconnected)
        self._colorChanged.connect(self._write_color_parameter)
        self._log_data_signal.connect(self._log_data_received)
        self._log_error_signal.connect(self._logging_error)

        self._helper.cf.connected.add_callback(self._connectedSignal.emit)
        self._helper.cf.disconnected.add_callback(self._disconnectedSignal.emit)

        # Handle position dropdown changes
        self.positionDropdown.currentIndexChanged.connect(self._on_position_changed)

    def _logging_error(self, log_conf, msg):
        QMessageBox.about(self, "Log error",
                          "Error when starting log config [%s]: %s" % (
                              log_conf.name, msg))

    def _log_data_received(self, _timestamp, data, _logconf):
        if not self.isVisible():
            return

        position = self.positionDropdown.currentData()

        # Determine which positions to check for throttling
        positions_to_check = [0, 1] if position == 2 else [position]

        # Update throttling state for positions that have data in this update
        has_thermal_data = False
        for pos in positions_to_check:
            if pos in self.PARAMS_BY_POSITION:
                thermal_log = self.PARAMS_BY_POSITION[pos]['thermal_log']
                if thermal_log in data:
                    has_thermal_data = True
                    # Update state for this position
                    self._throttling_state[pos] = bool(data[thermal_log])

        if has_thermal_data:
            # Check if any selected position is currently throttling based on known state
            is_throttling = any(
                self._throttling_state.get(pos, False)
                for pos in positions_to_check
            )

            self.information_text.setText(
                "Throttling: Lowering intensity to lower temperature." if is_throttling else ""
            )

    def _connected(self, _):
        self._isConnected = True

        # Detect which color LED decks are attached
        self._deck_controller.detect_decks()

        # Update dropdown based on detected decks
        self._update_position_dropdown()

        # Enable UI controls only if at least one deck is present
        present_decks = self._deck_controller.get_present_decks()
        has_decks = len(present_decks) > 0
        self.groupBox_color.setEnabled(has_decks)
        self.hue_bar.setEnabled(has_decks)

        # Set up thermal logging for available decks
        if has_decks:
            self._thermal_monitor.start_monitoring(present_decks)

    def _disconnected(self, _):
        self._isConnected = False
        self._deck_controller.clear_deck_state()
        self._throttling_state.clear()  # Clear throttling state

        # Disable UI controls
        self.groupBox_color.setEnabled(False)
        self.hue_bar.setEnabled(False)

        # Disable all position dropdown items
        self.positionDropdown.model().item(0).setEnabled(False)
        self.positionDropdown.model().item(1).setEnabled(False)
        self.positionDropdown.model().item(2).setEnabled(False)

        self.information_text.setText("")  # clear thermal throttling warning

    def _write_color_parameter(self, color: QColor):
        if not self._isConnected:
            return

        # Don't write when we're updating UI from a fetch operation
        if self._updating_from_fetch:
            return

        r, g, b, _ = color.getRgb()
        rgb = rgb_t(r or 0, g or 0, b or 0)
        wrgb = rgb.extract_white()
        color_uint32 = wrgb.pack()

        position = self.positionDropdown.currentData()

        # Determine which positions to write to
        positions_to_write = [0, 1] if position == 2 else [position]

        for pos in positions_to_write:
            self._deck_controller.write_color(pos, color_uint32)

    def _on_position_changed(self, _):
        """Handle position dropdown changes by fetching current color from Crazyflie"""
        if not self._isConnected:
            return

        position = self.positionDropdown.currentData()

        if position == 2:  # Both
            # Fetch both colors and compare
            color_bottom = self._fetch_color_from_position(0)
            color_top = self._fetch_color_from_position(1)

            if color_bottom is not None and color_top is not None:
                if color_bottom == color_top:
                    # Both are the same, show that color
                    self._update_ui_from_rgb(color_bottom)
                else:
                    # Different colors, show black
                    self._update_ui_from_rgb((0, 0, 0))
            else:
                # Could not fetch one or both colors, show black
                self._update_ui_from_rgb((0, 0, 0))
        else:  # Bottom (0) or Top (1)
            color = self._fetch_color_from_position(position)
            if color is not None:
                self._update_ui_from_rgb(color)
            else:
                # Could not fetch color, show black
                self._update_ui_from_rgb((0, 0, 0))

    def _fetch_color_from_position(self, position):
        """
        Fetch current color from Crazyflie for given position

        Args:
            position: 0 for bottom, 1 for top

        Returns:
            tuple (r, g, b) or None if fetch failed
        """
        if position not in self.PARAMS_BY_POSITION:
            return None

        if not self._deck_controller.is_deck_present(position):
            return None

        try:
            param_name = self.PARAMS_BY_POSITION[position]['color']
            color_uint32 = int(self._helper.cf.param.get_value(param_name))

            # Unpack WRGB: 0xWWRRGGBB
            w = (color_uint32 >> 24) & 0xFF
            r = (color_uint32 >> 16) & 0xFF
            g = (color_uint32 >> 8) & 0xFF
            b = color_uint32 & 0xFF

            # Convert WRGB back to RGB by adding white channel back
            r_full = r + w
            g_full = g + w
            b_full = b + w

            return (r_full, g_full, b_full)
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Could not fetch color from position {position}: {e}")
            return None

    def _update_ui_from_rgb(self, rgb):
        """
        Update UI controls from RGB values without writing back to Crazyflie

        Args:
            rgb: tuple (r, g, b)
        """
        self._updating_from_fetch = True
        try:
            r, g, b = rgb
            color = QColor(r, g, b)
            h, s, v, _ = color.getHsvF()

            self._hue = h or 0
            self._saturation = s or 0
            self._value = v or 0

            self.hue_bar.setValue(int(self._hue * 1000))
            self._update_sv_area(self.sv_area, self._hue)
            self._update_preview()
        finally:
            self._updating_from_fetch = False

    def _populate_position_dropdown(self):
        """Initialize the position dropdown with items (called once during __init__)"""
        self.positionDropdown.addItem("Bottom", 0)
        self.positionDropdown.addItem("Top", 1)
        self.positionDropdown.addItem("Both", 2)

        # Initially all disabled until we connect and detect decks
        self.positionDropdown.model().item(0).setEnabled(False)
        self.positionDropdown.model().item(1).setEnabled(False)
        self.positionDropdown.model().item(2).setEnabled(False)

    def _update_position_dropdown(self):
        """Update position dropdown based on detected decks"""
        is_bottom_attached = self._deck_controller.is_deck_present(0)
        is_top_attached = self._deck_controller.is_deck_present(1)

        if is_bottom_attached and is_top_attached:
            self.positionDropdown.model().item(0).setEnabled(True)
            self.positionDropdown.model().item(1).setEnabled(True)
            self.positionDropdown.model().item(2).setEnabled(True)
            # Default to "Both" if both attached
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
            # No decks attached
            self.positionDropdown.model().item(0).setEnabled(False)
            self.positionDropdown.model().item(1).setEnabled(False)
            self.positionDropdown.model().item(2).setEnabled(False)

    def showEvent(self, a0):
        """ Show event for proper initial SV area sizing """
        super().showEvent(a0)
        self._update_sv_area(self.sv_area, self._hue)
        # Update preview without writing to Crazyflie
        self._updating_from_fetch = True
        try:
            self._update_preview()
        finally:
            self._updating_from_fetch = False

    def mousePressEvent(self, a0):
        self._handle_mouse_event(a0)

    def mouseMoveEvent(self, a0):
        self._handle_mouse_event(a0)

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
        color = QColor.fromHsvF(self._hue or 0, self._saturation or 0, self._value or 0)
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
            self._hue, self._saturation, self._value = h or 0, s or 0, v or 0
            self.hue_bar.setValue(int(self._hue * 1000))
            self._update_sv_area(self.sv_area, self._hue)
            self._update_preview()
            self.hex_input.setStyleSheet("")
            self.hex_error_label.setText("")
            self.information_text.setText("")
        else:
            self.hex_input.setStyleSheet("border: 2px solid red; border-radius: 4px;")
            self.hex_error_label.setText("Invalid hex code.")
            self.information_text.setText("")
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
        style = button.styleSheet()  # type: ignore
        if "background-color:" not in style:
            return
        hex_color = style.split("background-color:")[-1].split(";")[0].strip()
        color = QColor(hex_color)
        if color.isValid():
            h, s, v, _ = color.getHsvF()
            self._hue, self._saturation, self._value = h or 0, s or 0, v or 0
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
        logger.debug(f"Added new custom color {color_hex}")

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
            logger.debug("Removed custom color button.")

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
