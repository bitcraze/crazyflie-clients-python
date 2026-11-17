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
A label that cuts its text with "..." when there is not enough room, instead of
pushing the widgets next to it out of place. The full text is shown as a tooltip
while it is cut.
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPainter, QPalette
from PyQt6.QtWidgets import QLabel, QSizePolicy

__author__ = 'Bitcraze AB'
__all__ = ['ElidedLabel']

MIN_WIDTH = 30


class ElidedLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def setText(self, text):
        self._full_text = text
        super().setText(text)
        self._update_tooltip()

    def minimumSizeHint(self):
        return QSize(MIN_WIDTH, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_tooltip()

    def _is_elided(self):
        return self.fontMetrics().horizontalAdvance(self._full_text) > self.contentsRect().width()

    def _update_tooltip(self):
        self.setToolTip(self._full_text if self._is_elided() else '')

    def paintEvent(self, event):
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, rect.width())
        painter = QPainter(self)
        group = QPalette.ColorGroup.Normal if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(self.palette().color(group, QPalette.ColorRole.WindowText))
        painter.drawText(rect, int(self.alignment()), text)
