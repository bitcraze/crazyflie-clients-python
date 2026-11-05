#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2026 Bitcraze AB
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
The settings of the WiFi camera deck, grouped in an accordion. Every change is
reported through settingChanged(name, value), which is where the camera lib
should be hooked up.

All ranges and options below are placeholders until the lib defines them.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                             QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

from cfclient.ui.widgets.accordion import Accordion
from cfclient.ui.widgets.segmented_control import SegmentedControl

__author__ = 'Bitcraze AB'
__all__ = ['CameraSettingsPanel']

OUTPUT_RESOLUTIONS = [(160, 120), (320, 240), (640, 480), (720, 720)]
DEFAULT_RESOLUTION = (720, 720)
CROP_LIMIT = 9999
DISABLED_OPACITY = 0.4


def _wrap(layout):
    """Put a layout in a widget, so that the whole row can be enabled/disabled"""
    layout.setContentsMargins(0, 0, 0, 0)
    widget = QWidget()
    widget.setLayout(layout)
    return widget


def _set_row_enabled(widget, enabled):
    """Enable or disable a row, fading it when disabled as Qt's own disabled look is subtle"""
    effect = widget.graphicsEffect()
    if effect is None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(1.0 if enabled else DISABLED_OPACITY)
    widget.setEnabled(enabled)


def _inline_row(text, control):
    """A label on the left and its control on the right"""
    row = QHBoxLayout()
    row.addWidget(QLabel(text))
    row.addStretch()
    row.addWidget(control)
    return _wrap(row)


def _stacked_row(text, control):
    """A label with its control below"""
    column = QVBoxLayout()
    column.addWidget(QLabel(text))
    column.addWidget(control)
    return _wrap(column)


class CameraSettingsPanel(QWidget):
    settingChanged = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._accordion = Accordion()
        self._add_framing()
        self._add_exposure()
        self._add_colour()
        self._add_image_quality()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._accordion)
        # Let the group box show through, otherwise the area gets its own slightly different color
        self._accordion.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _segmented(self, name, options, values=None):
        control = SegmentedControl(options)
        values = values if values is not None else options
        control.currentIndexChanged.connect(lambda i: self.settingChanged.emit(name, values[i]))
        return control

    def _slider(self, name, text, low, high, value, to_text, scale=1):
        """A label with the current value on the right and a slider below.
        The slider works in integers, the emitted value is divided by scale."""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)

        value_label = QLabel(to_text(value))
        head = QHBoxLayout()
        head.addWidget(QLabel(text))
        head.addStretch()
        head.addWidget(value_label)

        column = QVBoxLayout()
        column.addLayout(head)
        column.addWidget(slider)

        def changed(v):
            value_label.setText(to_text(v))
            self.settingChanged.emit(name, v if scale == 1 else v / scale)

        slider.valueChanged.connect(changed)
        return _wrap(column), slider

    def _add_framing(self):
        section = self._accordion.add_section('Framing', '%d x %d' % DEFAULT_RESOLUTION)

        # Two per row, four in a row is too wide for the panel with some themes and fonts
        spin_boxes = []
        crop = QGridLayout()
        for index, (label, value) in enumerate(zip(('X', 'Y', 'W', 'H'), (0, 0) + DEFAULT_RESOLUTION)):
            box = QSpinBox()
            box.setRange(0, CROP_LIMIT)
            box.setValue(value)
            box.setMinimumWidth(0)
            spin_boxes.append(box)
            row, column = divmod(index, 2)
            crop.addWidget(QLabel(label), row, column * 2)
            crop.addWidget(box, row, column * 2 + 1)
            crop.setColumnStretch(column * 2 + 1, 1)
        for box in spin_boxes:
            box.valueChanged.connect(
                lambda _: self.settingChanged.emit('crop_window', tuple(b.value() for b in spin_boxes)))
        section.content_layout.addWidget(_stacked_row('Sensor crop window', _wrap(crop)))

        resolution = QComboBox()
        for width, height in OUTPUT_RESOLUTIONS:
            resolution.addItem('%d x %d' % (width, height), (width, height))
        resolution.setCurrentIndex(OUTPUT_RESOLUTIONS.index(DEFAULT_RESOLUTION))

        def resolution_changed(index):
            section.set_summary(resolution.itemText(index))
            self.settingChanged.emit('output_resolution', resolution.itemData(index))

        resolution.currentIndexChanged.connect(resolution_changed)
        section.content_layout.addWidget(_stacked_row('Scaled output resolution', resolution))

    def _add_exposure(self):
        section = self._accordion.add_section('Exposure', 'Auto')
        layout = section.content_layout

        auto = self._segmented('auto_exposure', ['Auto', 'Manual'], [True, False])
        layout.addWidget(_inline_row('Auto exposure', auto))

        exposure_time, _ = self._slider('exposure_time', 'Exposure time', 1, 100, 10, lambda v: '%d ms' % v)
        gain, _ = self._slider('gain', 'Gain', 100, 1600, 200, lambda v: '%.2f×' % (v / 100), scale=100)
        layout.addWidget(exposure_time)
        layout.addWidget(gain)

        anti_flicker = self._segmented('anti_flicker', ['Off', '50 Hz', '60 Hz'], ['off', '50hz', '60hz'])
        layout.addWidget(_inline_row('Anti-flicker', anti_flicker))

        frame_rate = self._segmented('auto_frame_rate', ['Fixed', 'Down to ½', 'Down to ¼'],
                                     ['fixed', 'half', 'quarter'])
        stacked = _stacked_row('Auto frame rate', frame_rate)
        stacked.setToolTip('Lets the frame rate drop in low light, to allow longer exposures')
        layout.addWidget(stacked)

        def update():
            is_auto = auto.current_index() == 0
            _set_row_enabled(exposure_time, not is_auto)
            _set_row_enabled(gain, not is_auto)
            for widget in (exposure_time, gain):
                widget.setToolTip('Exposure time and gain are set automatically' if is_auto else '')
            section.set_summary('%s · %s' % (auto.current_text(), anti_flicker.current_text()))

        auto.currentIndexChanged.connect(lambda _: update())
        anti_flicker.currentIndexChanged.connect(lambda _: update())
        update()

    def _add_colour(self):
        section = self._accordion.add_section('Color', 'Auto WB')
        layout = section.content_layout

        auto = self._segmented('auto_white_balance', ['Auto', 'Manual'], [True, False])
        layout.addWidget(_inline_row('Auto white balance', auto))

        gains = []
        gain_widgets = []
        for colour in ('Red', 'Green', 'Blue'):
            widget, slider = self._slider('wb_gain_%s' % colour.lower(), '%s gain' % colour, 50, 400, 100,
                                          lambda v: '%.2f×' % (v / 100), scale=100)
            gains.append(slider)
            gain_widgets.append(widget)
            layout.addWidget(widget)
        for slider in gains:
            slider.valueChanged.connect(
                lambda _: self.settingChanged.emit('white_balance_gains', tuple(s.value() / 100 for s in gains)))

        effect = self._segmented('special_effect', ['None', 'Grayscale', 'Sepia', 'Negative'],
                                 ['none', 'grayscale', 'sepia', 'negative'])
        layout.addWidget(_stacked_row('Special effect', effect))

        saturation, _ = self._slider('saturation', 'Color saturation', 0, 200, 100, lambda v: '%d%%' % v, scale=100)
        layout.addWidget(saturation)

        def update():
            is_auto = auto.current_index() == 0
            for widget in gain_widgets:
                _set_row_enabled(widget, not is_auto)
                widget.setToolTip('White balance gains are set automatically' if is_auto else '')
            section.set_summary('Auto WB' if is_auto else 'Manual WB')

        auto.currentIndexChanged.connect(lambda _: update())
        update()

    def _add_image_quality(self):
        section = self._accordion.add_section('Image Quality', 'Sharpness 0')
        layout = section.content_layout

        sharpness, slider = self._slider('sharpness', 'Sharpness', -2, 2, 0, lambda v: '%+d' % v if v else '0')
        layout.addWidget(sharpness)

        lens_shading = self._segmented('lens_shading_correction', ['Off', 'On'], [False, True])
        layout.addWidget(_inline_row('Lens shading correction', lens_shading))

        def update(*_):
            section.set_summary('Sharpness %d · Lens shading %s' % (slider.value(), lens_shading.current_text()))

        slider.valueChanged.connect(update)
        lens_shading.currentIndexChanged.connect(update)
        update()
