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
                             QScrollArea, QSizePolicy, QSlider, QSpinBox, QStyle, QVBoxLayout, QWidget)

from cfclient.ui.widgets.accordion import Accordion
from cfclient.ui.widgets.info_label import InfoLabel
from cfclient.ui.widgets.segmented_control import SegmentedControl

__author__ = 'Bitcraze AB'
__all__ = ['CameraSettingsPanel']

# Sensor crop window: the start must be even and at least 2, the end odd and within the pixel array
CROP_START_MIN = 2
CROP_X_END_MAX = 1285
CROP_Y_END_MAX = 725
DEFAULT_CROP = (4, 4, 1280, 720)
# The scaler can only scale down, and to no less than this
MIN_OUTPUT_SIZE = (56, 42)
OUTPUT_SCALES = (1, 2, 4)
DISABLED_OPACITY = 0.4
SCROLLBAR_GAP = 10

def _info(works, affects=(), notes=()):
    """The text of an info popover. Every setting is described the same way: how it works, what it
    affects (including the other settings) and what is good to know, such as when it is used."""
    parts = ['<b>How it works</b><br>%s' % works]
    if affects:
        parts.append('<b>What it affects</b><br>' + '<br>'.join('\u2022 ' + text for text in affects))
    if notes:
        parts.append('<b>Good to know</b><br>' + '<br>'.join('\u2022 ' + text for text in notes))
    return '<br><br>'.join(parts)


# What each setting does and what it affects. Based on the deck's settings reference, so keep them in
# line with it (S numbers in the comments).
# S03
INFO_CROP = _info(
    'Chooses which part of the sensor is used, like a digital zoom that keeps full detail. A smaller '
    'window shows a narrower view, and can cut out things like propellers or landing feet.',
    ['Field of view: a smaller window shows less.',
     'Scaled output resolution: the sizes on offer follow the crop window.',
     'WiFi: smaller frames are easier to send, but the speed of the camera itself does not change.'],
    ['The video restarts briefly when this changes.',
     'Positions and sizes are even numbers inside the sensor.'])
# S07
INFO_RESOLUTION = _info(
    'Shrinks the picture the deck sends, as a share of the crop window, with the same field of view.',
    ['Detail: a smaller picture has less detail.',
     'WiFi: smaller frames are easier to send, so over a weak connection more of them get through and '
     'the video is smoother.',
     'Frame rate: the camera still captures at the same speed, so you never get more frames than the '
     'camera\'s own frame rate.'],
    ['The picture can only be made smaller, never larger.',
     'The video restarts briefly when this changes.'])
# S12, S13
INFO_AUTO_EXPOSURE = _info(
    'Auto lets the camera choose exposure time and gain to keep the picture evenly bright as the light '
    'changes. Manual keeps the brightness fixed, for repeatable measurements or computer vision.',
    ['Brightness: in manual, the picture gets too dark or too bright when the light changes.',
     'Dim light: auto exposure can pick long exposures (motion blur, and a lower frame rate, also with '
     'Auto frame rate set to Fixed) or high gain (grain).'],
    ['Decides whether Exposure time, Gain and Anti-flicker are used.'])
# S14
INFO_EXPOSURE_TIME = _info(
    'How long the sensor collects light for each frame.',
    ['Brightness: shorter gives a darker picture, so it needs more gain and gets grainier. Longer gives '
     'a brighter, cleaner picture.',
     'Motion: longer exposures make moving things smear.',
     'Frame rate: once the exposure is longer than one frame (about 33 ms at 30 fps) the frame rate drops.'],
    ['Under mains-powered lights, use a multiple of the flicker period (10 ms at 50 Hz, 8.3 ms at 60 Hz) '
     'to avoid dark bands.',
     'Only used with manual exposure.'])
# S15
INFO_GAIN = _info(
    'Amplifies the signal after the light is collected, like turning up the volume. It adds no light.',
    ['Brightness: brightens a dark picture without extra motion blur.',
     'Noise: the noise is amplified too, so the picture gets grainy.'],
    ['Only used with manual exposure.'])
# S23
INFO_ANTI_FLICKER = _info(
    'Mains-powered lights, such as fluorescent tubes and many LEDs, pulse 100 times a second on 50 Hz '
    'mains and 120 times on 60 Hz, which shows as dark bands rolling through the picture. Anti-flicker '
    'keeps the exposure time at whole multiples of the pulse period (10 ms at 50 Hz, 8.3 ms at 60 Hz), '
    'which removes the bands.',
    ['Picture: no dark bands under mains-powered lights.',
     'Exposure: the steps are coarse, so auto exposure relies more on gain and the picture can get '
     'grainier, especially at high frame rates.'],
    ['Choose the mains frequency where you fly, for example 50 Hz in Europe and 60 Hz in North America.',
     'Not needed outdoors in daylight.',
     'Only used with auto exposure. With manual exposure, set the exposure time to a multiple yourself.'])
# S61
INFO_FRAME_RATE = _info(
    'Lets the deck slow down the frame rate in low light, to allow longer exposures. Fixed keeps the '
    'frame rate steady.',
    ['Brightness: a brighter, cleaner picture in dim light.',
     'Motion: longer exposures mean more motion blur.',
     'Frame rate: it varies in the dark.'],
    ['Even with Fixed, auto exposure can still lower the frame rate in a dim scene if it picks a long '
     'exposure.'])
# S40, S110
INFO_COLOR_MODE = _info(
    'Grayscale sends a black and white picture instead of a color one.',
    ['WiFi: it should need less data than color, which helps on a weak connection.',
     'Color saturation: not used in grayscale.',
     'White balance: still changes the brightness, so it still matters.'],
    ['Suits computer vision that only uses brightness.',
     'The video restarts briefly when this changes.'])
# S26
INFO_WHITE_BALANCE = _info(
    'Corrects the color of the light, such as warm indoor bulbs or bluish shade, so that white looks '
    'white. Auto adapts when you move between different lights. Manual keeps the colors fixed.',
    ['Colors: auto can shift them when one color fills the view, for example a green floor. Manual gives '
     'a tint over the whole picture if the light changes.',
     'Brightness: it also changes the brightness, so it matters in grayscale too.'],
    ['Manual suits fixed lighting and color tracking.',
     'Decides whether the red and blue gains are used.',
     'Applied before color saturation.'])
# S27
INFO_GAIN_RED = _info(
    'Boosts or reduces red relative to green.',
    ['Colors: raise it to warm up a bluish picture.'],
    ['Only used with manual white balance.'])
INFO_GAIN_BLUE = _info(
    'Boosts or reduces blue relative to green.',
    ['Colors: raise it to cool down a yellowish picture.'],
    ['Only used with manual white balance.'])
# S30
INFO_SATURATION = _info(
    'Sets how vivid the colors are: 0% is gray, 100% is the normal strength and higher is more intense.',
    ['Colors: changes their strength, not the brightness.'],
    ['Applied after white balance.',
     'Not used in grayscale.'])
# S33
INFO_SHARPNESS = _info(
    'Makes edges look crisper by boosting the contrast along them.',
    ['Detail: higher values help marker and tag detection. Lower values give a softer picture, which '
     'suits noisy, low-light scenes.',
     'Noise: higher values amplify it and draw bright or dark halos along edges.',
     'WiFi: sharper pictures compress worse, so the frames get larger, which matters on a weak connection.'])
# S36
INFO_LENS_SHADING = _info(
    'Brightens the corners of the picture to cancel the darkening that the lens causes (vignetting).',
    ['Brightness: it becomes even across the frame.',
     'Noise: it becomes more visible in the corners.'],
    ['The correction has to be calibrated for each lens: a wrong calibration gives over-bright corners '
     'or colored edges.'])


def _wrap(layout):
    """Put a layout in a widget, so that the whole row can be enabled/disabled"""
    layout.setContentsMargins(0, 0, 0, 0)
    widget = QWidget()
    widget.setLayout(layout)
    return widget


def _set_row_enabled(widget, enabled):
    """Enable or disable a row, fading it when disabled as Qt's own disabled look is subtle.
    The info icons stay usable, as the explanation of a setting is most needed when it is not available."""
    effect = widget.graphicsEffect()
    if effect is None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(1.0 if enabled else DISABLED_OPACITY)
    for child in widget.findChildren(QWidget):
        if not isinstance(child, InfoLabel):
            child.setEnabled(enabled)


def _label(text, info=None):
    """A row's label, followed by an info icon that explains the setting when there is a description"""
    row = QHBoxLayout()
    row.setSpacing(4)
    label = QLabel(text)
    # Keep the icon next to the text, also in rows where the label has the whole width
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
    row.addWidget(label)
    if info:
        row.addWidget(InfoLabel(info, None, InfoLabel.Position.INLINE))
    return row


def _inline_row(text, control, info=None):
    """A label on the left and its control on the right"""
    row = QHBoxLayout()
    row.addLayout(_label(text, info))
    row.addStretch()
    row.addWidget(control)
    return _wrap(row)


def _stacked_row(text, control, info=None):
    """A label with its control below"""
    column = QVBoxLayout()
    column.addLayout(_label(text, info))
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
        self._scroll_bar = scroll.verticalScrollBar()
        self._scroll_bar.rangeChanged.connect(self._update_scroll_padding)
        self._update_scroll_padding()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _update_scroll_padding(self, *_):
        """Keep the contents clear of the scroll bar. Some styles draw it on top of the contents
        instead of next to them, so then it needs room for the bar as well."""
        padding = 0
        if self._scroll_bar.maximum() > 0:
            padding = SCROLLBAR_GAP
            if self.style().styleHint(QStyle.StyleHint.SH_ScrollBar_Transient, None, self._scroll_bar):
                padding += self._scroll_bar.sizeHint().width()
        self._accordion.layout().setContentsMargins(0, 0, padding, 0)

    def _segmented(self, name, options, values=None):
        control = SegmentedControl(options)
        values = values if values is not None else options
        control.currentIndexChanged.connect(lambda i: self.settingChanged.emit(name, values[i]))
        return control

    def _slider(self, name, text, low, high, value, to_text, scale=1, info=None):
        """A label with the current value on the right and a slider below.
        The slider works in integers, the emitted value is divided by scale."""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)

        value_label = QLabel(to_text(value))
        head = QHBoxLayout()
        head.addLayout(_label(text, info))
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
        section = self._accordion.add_section('Framing', '')

        # Two per row, four in a row is too wide for the panel with some themes and fonts
        spin_boxes = []
        crop = QGridLayout()
        for index, (label, value) in enumerate(zip(('X', 'Y', 'W', 'H'), DEFAULT_CROP)):
            box = QSpinBox()
            box.setSingleStep(2)
            box.setRange(0, CROP_X_END_MAX)
            box.setValue(value)
            box.setMinimumWidth(0)
            spin_boxes.append(box)
            row, column = divmod(index, 2)
            crop.addWidget(QLabel(label), row, column * 2)
            crop.addWidget(box, row, column * 2 + 1)
            crop.setColumnStretch(column * 2 + 1, 1)
        x, y, w, h = spin_boxes
        section.content_layout.addWidget(_stacked_row('Sensor crop window', _wrap(crop), INFO_CROP))

        resolution = QComboBox()
        section.content_layout.addWidget(_stacked_row('Scaled output resolution', resolution, INFO_RESOLUTION))
        # The scaler scales width and height separately, so keeping the aspect ratio of the crop
        # window is up to us: every option is the crop window divided by a whole number.

        def update_limits():
            """Start positions are even, sizes are even, and the window stays inside the sensor"""
            for box in spin_boxes:
                box.blockSignals(True)
                box.setValue(box.value() // 2 * 2)
            x.setRange(CROP_START_MIN, CROP_X_END_MAX - MIN_OUTPUT_SIZE[0])
            y.setRange(CROP_START_MIN, CROP_Y_END_MAX - MIN_OUTPUT_SIZE[1])
            w.setRange(MIN_OUTPUT_SIZE[0], CROP_X_END_MAX + 1 - x.value())
            h.setRange(MIN_OUTPUT_SIZE[1], CROP_Y_END_MAX + 1 - y.value())
            for box in spin_boxes:
                box.blockSignals(False)

        def output_sizes():
            sizes = []
            for scale in OUTPUT_SCALES:
                size = (w.value() // scale // 2 * 2, h.value() // scale // 2 * 2)
                if size[0] >= MIN_OUTPUT_SIZE[0] and size[1] >= MIN_OUTPUT_SIZE[1]:
                    sizes.append((scale, size))
            return sizes

        def update_resolutions():
            previous = resolution.currentIndex()
            resolution.blockSignals(True)
            resolution.clear()
            for scale, (width, height) in output_sizes():
                resolution.addItem('%d x %d  (%d%%)' % (width, height, 100 // scale), (width, height))
            resolution.setCurrentIndex(max(0, min(previous, resolution.count() - 1)))
            resolution.blockSignals(False)

        def announce_resolution():
            size = resolution.currentData()
            if size is None:
                return
            section.set_summary('%d x %d' % size)
            self.settingChanged.emit('output_resolution', size)

        def crop_changed(_):
            update_limits()
            update_resolutions()
            self.settingChanged.emit('crop_window', tuple(b.value() for b in spin_boxes))
            announce_resolution()

        update_limits()
        update_resolutions()
        section.set_summary('%d x %d' % resolution.currentData())
        for box in spin_boxes:
            box.valueChanged.connect(crop_changed)
        resolution.currentIndexChanged.connect(lambda _: announce_resolution())

    def _add_exposure(self):
        section = self._accordion.add_section('Exposure', 'Auto')
        layout = section.content_layout

        auto = self._segmented('auto_exposure', ['Auto', 'Manual'], [True, False])
        layout.addWidget(_inline_row('Auto exposure', auto, INFO_AUTO_EXPOSURE))

        exposure_time, _ = self._slider('exposure_time', 'Exposure time', 1, 100, 10, lambda v: '%d ms' % v,
                                        info=INFO_EXPOSURE_TIME)
        gain, _ = self._slider('gain', 'Gain', 100, 1600, 200, lambda v: '%.2f×' % (v / 100), scale=100,
                            info=INFO_GAIN)
        layout.addWidget(exposure_time)
        layout.addWidget(gain)

        anti_flicker = self._segmented('anti_flicker', ['Off', '50 Hz', '60 Hz'], ['off', '50hz', '60hz'])
        anti_flicker_row = _inline_row('Anti-flicker', anti_flicker, INFO_ANTI_FLICKER)
        layout.addWidget(anti_flicker_row)

        frame_rate = self._segmented('auto_frame_rate', ['Fixed', 'Down to ½', 'Down to ¼'],
                                     ['fixed', 'half', 'quarter'])
        layout.addWidget(_stacked_row('Auto frame rate', frame_rate, INFO_FRAME_RATE))

        def update():
            is_auto = auto.current_index() == 0
            _set_row_enabled(exposure_time, not is_auto)
            _set_row_enabled(gain, not is_auto)
            for widget in (exposure_time, gain):
                widget.setToolTip('Exposure time and gain are set automatically' if is_auto else '')
            # Anti-flicker only limits the exposure times that auto exposure picks
            _set_row_enabled(anti_flicker_row, is_auto)
            anti_flicker_row.setToolTip('Only used with auto exposure' if not is_auto else '')
            section.set_summary('%s · %s' % (auto.current_text(), anti_flicker.current_text()) if is_auto
                                else auto.current_text())

        auto.currentIndexChanged.connect(lambda _: update())
        anti_flicker.currentIndexChanged.connect(lambda _: update())
        update()

    def _add_colour(self):
        section = self._accordion.add_section('Color', 'Auto WB')
        layout = section.content_layout

        color_mode = self._segmented('color_mode', ['Color', 'Grayscale'], ['color', 'grayscale'])
        layout.addWidget(_inline_row('Color mode', color_mode, INFO_COLOR_MODE))

        auto = self._segmented('auto_white_balance', ['Auto', 'Manual'], [True, False])
        layout.addWidget(_inline_row('Auto white balance', auto, INFO_WHITE_BALANCE))

        gains = []
        gain_widgets = []
        # Only red and blue, white balance adjusts them relative to green
        for colour, info in (('Red', INFO_GAIN_RED), ('Blue', INFO_GAIN_BLUE)):
            widget, slider = self._slider('wb_gain_%s' % colour.lower(), '%s gain' % colour, 50, 400, 100,
                                          lambda v: '%.2f×' % (v / 100), scale=100, info=info)
            gains.append(slider)
            gain_widgets.append(widget)
            layout.addWidget(widget)
        for slider in gains:
            slider.valueChanged.connect(
                lambda _: self.settingChanged.emit('white_balance_gains', tuple(s.value() / 100 for s in gains)))


        saturation, _ = self._slider('saturation', 'Color saturation', 0, 200, 100, lambda v: '%d%%' % v, scale=100,
                                   info=INFO_SATURATION)
        layout.addWidget(saturation)

        def update():
            is_auto = auto.current_index() == 0
            for widget in gain_widgets:
                _set_row_enabled(widget, not is_auto)
                widget.setToolTip('White balance gains are set automatically' if is_auto else '')
            section.set_summary('Auto WB' if is_auto else 'Manual WB')

        def update_color_mode():
            # Saturation only scales the color information, which grayscale leaves out
            is_color = color_mode.current_index() == 0
            _set_row_enabled(saturation, is_color)
            saturation.setToolTip('' if is_color else 'Not used in grayscale')

        auto.currentIndexChanged.connect(lambda _: update())
        color_mode.currentIndexChanged.connect(lambda _: update_color_mode())
        update_color_mode()
        update()

    def _add_image_quality(self):
        section = self._accordion.add_section('Image Quality', 'Sharpness 0')
        layout = section.content_layout

        sharpness, slider = self._slider('sharpness', 'Sharpness', -2, 2, 0, lambda v: '%+d' % v if v else '0',
                                      info=INFO_SHARPNESS)
        layout.addWidget(sharpness)

        lens_shading = self._segmented('lens_shading_correction', ['Off', 'On'], [False, True])
        layout.addWidget(_inline_row('Lens shading correction', lens_shading, INFO_LENS_SHADING))

        def update(*_):
            section.set_summary('Sharpness %d · Lens shading %s' % (slider.value(), lens_shading.current_text()))

        slider.valueChanged.connect(update)
        lens_shading.currentIndexChanged.connect(update)
        update()
