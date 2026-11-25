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
A row of mutually exclusive buttons in a rounded container, where the selected one is raised with
a light background and an outline. Background colors come from the palette so it follows the theme.

Each segment can have a colored dot, a muted prefix and a monospace path. The
segments can be replaced at runtime and the control can be moved with the arrow keys.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase
from PyQt6.QtWidgets import QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton

__author__ = 'Bitcraze AB'
__all__ = ['SegmentedControl', 'Segment', 'dot', 'muted_color']

_STYLE = """
QFrame[segmentedControl=true] {
    background-color: %(track)s; border-radius: 8px; border: 1px solid %(outline)s;
}
QFrame[segmentedControl=true] QPushButton {
    background-color: transparent; border: none; border-radius: 6px; padding: 5px 12px;
}
QFrame[segmentedControl=true] QPushButton:checked {
    background-color: %(selected)s; border: 1px solid %(outline)s;
}
"""


def muted_color():
    """The placeholder text color as a solid color, as it is the text color with some transparency"""
    palette = QApplication.palette()
    color = palette.placeholderText().color()
    background = palette.window().color()
    alpha = color.alphaF()
    blended = [color.getRgbF()[i] * alpha + background.getRgbF()[i] * (1 - alpha) for i in range(3)]
    return QColor.fromRgbF(*blended).name()


def dot(color, size=9):
    label = QLabel()
    label.setFixedSize(size, size)
    label.setStyleSheet('background-color: %s; border-radius: %dpx; border: none;' % (color, size // 2))
    return label


class Segment:

    def __init__(self, text, prefix='', color=None, monospace=False, dimmed=False):
        self.text = text
        self.prefix = prefix        # Shown before the text in a muted color
        self.color = color          # Color of a dot before the text, no dot if None
        self.monospace = monospace
        self.dimmed = dimmed        # Everything but the dot in the muted color


class _SegmentButton(QPushButton):

    def __init__(self, segment):
        super().__init__()
        self.segment = segment
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # The control has the focus and handles the arrow keys
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        self._dot = None
        if segment.color:
            self._dot = dot(segment.color)
            layout.addWidget(self._dot)

        self._label = QLabel()
        self._label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._label)

        for child in (self._dot, self._label):
            if child is not None:
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.refresh_style()

    def refresh_style(self):
        muted = muted_color()
        text = self.segment.text
        if self.segment.dimmed:
            text = '<span style="color: %s">%s%s</span>' % (muted, self.segment.prefix, text)
        elif self.segment.prefix:
            text = '<span style="color: %s">%s</span>%s' % (muted, self.segment.prefix, text)
        self._label.setText(text)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont) if self.segment.monospace \
            else self._label.font()
        self._label.setFont(font)

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()


class SegmentedControl(QFrame):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Not the object name, as a .ui file renames the widget
        self.setProperty('segmentedControl', True)
        self._style = ''

        self._buttons = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._clicked)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(2)

        # A widget with a style sheet is not told about a new theme, the application is
        QApplication.instance().paletteChanged.connect(self._apply_style)
        self._apply_style()

    def set_segments(self, segments, current=0, emit=True):
        """Replace the segments, a list of Segment"""
        for button in self._buttons:
            self._group.removeButton(button)
            self._layout.removeWidget(button)
            button.deleteLater()

        self._buttons = [_SegmentButton(segment) for segment in segments]
        for index, button in enumerate(self._buttons):
            self._group.addButton(button, index)
            self._layout.addWidget(button)

        if self._buttons:
            self.set_current_index(min(current, len(self._buttons) - 1), emit)

    def _clicked(self, index):
        self.setFocus()
        self.currentIndexChanged.emit(index)

    def current_index(self):
        return self._group.checkedId()

    def set_current_index(self, index, emit=True):
        self._group.button(index).setChecked(True)
        if emit:
            self.currentIndexChanged.emit(index)

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(event.key())
        if step is None or not self._buttons:
            super().keyPressEvent(event)
            return
        index = self.current_index()
        while 0 <= index + step < len(self._buttons):
            index += step
            if not self._buttons[index].isHidden():
                self.set_current_index(index)
                break
        event.accept()

    def _apply_style(self, *_):
        # The track has to stand out from the window behind it, which a plain
        # palette role does not guarantee, so derive it from the window color.
        # Uses the application palette, as the widget's own palette changes when
        # the style sheet is set, which would loop.
        palette = QApplication.palette()
        window = palette.window().color()
        # The selected segment is raised: white in a light theme, the button color in a dark one,
        # where the base color is darker than the track
        if window.lightness() < 128:
            track = window.darker(120)
            selected = palette.button().color()
        else:
            track = window.darker(110)
            selected = palette.base().color()
        style = _STYLE % {
            'track': track.name(),
            'selected': selected.name(),
            # A faint outline for the track and the selected segment, from the text color
            'outline': 'rgba(%d, %d, %d, 40)' % palette.windowText().color().getRgb()[:3],
        }
        if style != self._style:
            self._style = style
            self.setStyleSheet(style)
            for button in self._buttons:
                button.refresh_style()
