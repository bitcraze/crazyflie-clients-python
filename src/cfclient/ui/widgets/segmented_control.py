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
A row of mutually exclusive buttons in a rounded container, where the selected
one is highlighted. Background colors come from the palette so it follows the theme.
"""

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QButtonGroup, QFrame, QHBoxLayout, QPushButton

__author__ = 'Bitcraze AB'
__all__ = ['SegmentedControl']

# Fixed instead of the palette highlight, which can be any color in the user's theme
COLOR_ACCENT = '#2473DD'

_STYLE = """
QFrame#segmentedControl {
    background-color: %(track)s; border-radius: 8px;
}
QFrame#segmentedControl QPushButton {
    background-color: transparent; border: none; border-radius: 6px; padding: 5px 12px;
}
QFrame#segmentedControl QPushButton:checked {
    background-color: %(selected)s; color: %(accent)s;
}
"""


class SegmentedControl(QFrame):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, options, current=0, parent=None):
        super().__init__(parent)
        self.setObjectName('segmentedControl')
        self._style = ''

        self._options = list(options)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        for index, text in enumerate(self._options):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(button, index)
            layout.addWidget(button)

        self._group.idClicked.connect(self.currentIndexChanged)
        self._apply_style()
        self.set_current_index(current)

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
            'accent': COLOR_ACCENT,
        }
        if style != self._style:
            self._style = style
            self.setStyleSheet(style)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self._apply_style()

    def current_index(self):
        return self._group.checkedId()

    def current_text(self):
        return self._options[self.current_index()]

    def set_current_index(self, index):
        self._group.button(index).setChecked(True)
        self.currentIndexChanged.emit(index)
