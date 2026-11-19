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
a light background and an outline. Button text can span several lines. Background colors come from
the palette so it follows the theme.

By default the buttons are equally wide. Segments can also be rich (a colored dot, a muted prefix,
a monospace path and an unread badge), replaced at runtime, and the control can be moved with the
arrow keys. See set_segments().
"""

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy)

__author__ = 'Bitcraze AB'
__all__ = ['SegmentedControl', 'Segment', 'dot']

_STYLE = """
QFrame[segmentedControl=true] {
    background-color: %(track)s; border-radius: 8px; border: 1px solid transparent;
}
QFrame[segmentedControl=true] QPushButton {
    background-color: transparent; border: none; border-radius: 6px; padding: 5px 12px;
}
QFrame[segmentedControl=true] QPushButton:checked {
    background-color: %(selected)s; border: 1px solid %(border)s;
}
"""


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

        self._unread = 0
        self._badge = QLabel()
        self._badge.hide()
        layout.addWidget(self._badge)

        for child in (self._dot, self._label, self._badge):
            if child is not None:
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.refresh_style()

    def refresh_style(self):
        palette = QApplication.palette()
        muted = palette.placeholderText().color().name()
        text = self.segment.text
        if self.segment.dimmed:
            text = '<span style="color: %s">%s%s</span>' % (muted, self.segment.prefix, text)
        elif self.segment.prefix:
            text = '<span style="color: %s">%s</span>%s' % (muted, self.segment.prefix, text)
        self._label.setText(text)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont) if self.segment.monospace \
            else self._label.font()
        self._label.setFont(font)
        self._badge.setStyleSheet(
            'background-color: %s; color: %s; border-radius: 7px; padding: 0px 5px; font-size: 11px; '
            'border: none;' % (palette.highlight().color().name(), palette.highlightedText().color().name()))

    def set_badge(self, count):
        self._unread = count
        self._badge.setText(str(count))
        self.refresh_badge()

    def refresh_badge(self, selected=None):
        # The selected segment has been read
        if selected is None:
            selected = self.isChecked()
        self._badge.setVisible(self._unread > 0 and not selected)

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()


class SegmentedControl(QFrame):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, options=(), current=0, parent=None, equal_width=True):
        super().__init__(parent)
        # Not the object name, as a .ui file renames the widget
        self.setProperty('segmentedControl', True)
        self._style = ''
        self._equal_width = equal_width

        self._options = []
        self._buttons = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._clicked)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(2)

        self._apply_style()
        if options:
            self.set_segments(options, current)

    def set_equal_width(self, equal_width):
        self._equal_width = equal_width

    def set_segments(self, segments, current=0, emit=True):
        """Replace the segments, each a string or a Segment"""
        for button in self._buttons:
            self._group.removeButton(button)
            self._layout.removeWidget(button)
            button.deleteLater()
        self._buttons = []
        self._options = []

        for index, segment in enumerate(segments):
            if isinstance(segment, Segment):
                button = _SegmentButton(segment)
                self._options.append(segment.prefix + segment.text)
            else:
                button = QPushButton(segment)
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self._options.append(segment)
            policy = QSizePolicy.Policy.Expanding if self._equal_width else QSizePolicy.Policy.Preferred
            button.setSizePolicy(policy, QSizePolicy.Policy.Preferred)
            self._group.addButton(button, index)
            self._layout.addWidget(button, 1 if self._equal_width else 0)
            self._buttons.append(button)

        if self._buttons:
            self.set_current_index(min(current, len(self._buttons) - 1), emit)

    def set_badge(self, index, count):
        button = self._buttons[index]
        if isinstance(button, _SegmentButton):
            button.set_badge(count)

    def _clicked(self, index):
        self.setFocus()
        self._select(index)

    def _refresh_badges(self, index):
        for i, button in enumerate(self._buttons):
            if isinstance(button, _SegmentButton):
                button.refresh_badge(i == index)

    def _select(self, index):
        self._refresh_badges(index)
        self.currentIndexChanged.emit(index)

    def current_index(self):
        return self._group.checkedId()

    def current_text(self):
        return self._options[self.current_index()]

    def set_current_index(self, index, emit=True):
        self._group.button(index).setChecked(True)
        if emit:
            self._select(index)
        else:
            self._refresh_badges(index)

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

    def _apply_style(self):
        # The track has to stand out from the window behind it, which a plain
        # palette role does not guarantee, so derive it from the window color.
        # Uses the application palette, as the widget's own palette changes when
        # the style sheet is set, which would loop.
        palette = QApplication.palette()
        window = palette.window().color()
        track = window.lighter(150) if window.lightness() < 128 else window.darker(110)
        style = _STYLE % {
            'track': track.name(),
            'selected': palette.base().color().name(),
            'border': palette.mid().color().name(),
        }
        if style != self._style:
            self._style = style
            self.setStyleSheet(style)
            for button in self._buttons:
                if isinstance(button, _SegmentButton):
                    button.refresh_style()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self._apply_style()
