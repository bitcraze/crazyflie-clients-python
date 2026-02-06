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

from enum import Enum
from PyQt6.QtWidgets import QLabel, QWidget, QToolTip
from PyQt6.QtCore import QObject, QEvent


class InfoLabel(QLabel):
    """A label with an information icon and a tooltip."""

    class Position(Enum):
        TOP_LEFT = 1
        TOP_RIGHT = 2
        BOTTOM_LEFT = 3
        BOTTOM_RIGHT = 4

    ICON_WIDTH = 16
    ICON_HEIGHT = 16
    MARGIN = 0

    def __init__(self, tooltip: str, parent: QWidget, position: Position = Position.TOP_RIGHT,
                 v_margin: int = MARGIN, h_margin: int = MARGIN):
        super().__init__(parent)

        self._v_margin = v_margin
        self._h_margin = h_margin

        self._event_filter = _EventFilter(self, position)
        parent.installEventFilter(self._event_filter)

        self.setToolTip(tooltip)

        info_pixmap = self.style().StandardPixmap.SP_MessageBoxInformation
        info_icon = self.style().standardIcon(info_pixmap).pixmap(self.ICON_WIDTH, self.ICON_HEIGHT)
        self.setPixmap(info_icon)

    def mousePressEvent(self, event):
        """Override mouse press event to show tooltip on click."""
        QToolTip.showText(event.globalPosition().toPoint(), self.toolTip(), self)


class _EventFilter(QObject):
    def __init__(self, info_label: 'InfoLabel', position: InfoLabel.Position):
        super().__init__()
        self._info_label = info_label
        self._position = position

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            self._update_position()
        return super().eventFilter(obj, event)

    def _update_position(self):
        parent = self._info_label.parent()
        if parent is None:
            return
        x, y = 0, 0
        if self._position == InfoLabel.Position.TOP_LEFT:
            x, y = self._info_label._h_margin, self._info_label._v_margin
        elif self._position == InfoLabel.Position.TOP_RIGHT:
            x = parent.width() - self._info_label.ICON_WIDTH - self._info_label._h_margin
            y = self._info_label._v_margin
        elif self._position == InfoLabel.Position.BOTTOM_LEFT:
            x = self._info_label._h_margin
            y = parent.height() - self._info_label.ICON_HEIGHT - self._info_label._v_margin
        elif self._position == InfoLabel.Position.BOTTOM_RIGHT:
            x = parent.width() - self._info_label.ICON_WIDTH - self._info_label._h_margin
            y = parent.height() - self._info_label.ICON_HEIGHT - self._info_label._v_margin
        self._info_label.move(x, y)
