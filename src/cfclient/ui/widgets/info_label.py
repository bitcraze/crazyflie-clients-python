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
from PyQt6.QtWidgets import QLabel, QWidget, QFrame, QVBoxLayout
from PyQt6.QtCore import QObject, QEvent, Qt, QPoint
from PyQt6.QtGui import QGuiApplication


class _InfoPopover(QFrame):
    POPOVER_WIDTH = 300

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame {"
            "  background-color: #fffef0;"
            "  border: 1px solid #aaaaaa;"
            "  border-radius: 6px;"
            "}"
            "QLabel {"
            "  background: transparent;"
            "  border: none;"
            "  color: #222222;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(self.POPOVER_WIDTH)
        layout.addWidget(self._label)

    def show_near(self, global_pos: QPoint, text: str):
        self._label.setText(text)
        self._label.adjustSize()
        self.adjustSize()

        x = global_pos.x() + 8
        y = global_pos.y() + 8

        screen = QGuiApplication.screenAt(global_pos)
        if screen:
            rect = screen.availableGeometry()
            if x + self.width() > rect.right():
                x = global_pos.x() - self.width() - 8
            if y + self.height() > rect.bottom():
                y = global_pos.y() - self.height() - 8

        self.move(x, y)
        self.show()


class InfoLabel(QLabel):
    """A label with an information icon. Click to open a popover with details."""

    class Position(Enum):
        TOP_LEFT = 1
        TOP_RIGHT = 2
        BOTTOM_LEFT = 3
        BOTTOM_RIGHT = 4

    ICON_WIDTH = 16
    ICON_HEIGHT = 16
    MARGIN = 0

    _shared_popover: _InfoPopover | None = None

    def __init__(self, text: str, parent: QWidget, position: Position = Position.TOP_RIGHT,
                 v_margin: int = MARGIN, h_margin: int = MARGIN):
        super().__init__(parent)

        self._v_margin = v_margin
        self._h_margin = h_margin
        self._text = text

        self._event_filter = _EventFilter(self, position)
        parent.installEventFilter(self._event_filter)

        info_pixmap = self.style().StandardPixmap.SP_MessageBoxInformation
        info_icon = self.style().standardIcon(info_pixmap).pixmap(self.ICON_WIDTH, self.ICON_HEIGHT)
        self.setPixmap(info_icon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setToolTip(self, text: str):
        """Store text for use in the popover (replaces tooltip)."""
        self._text = text

    def mousePressEvent(self, event):
        if InfoLabel._shared_popover is None:
            InfoLabel._shared_popover = _InfoPopover()
        InfoLabel._shared_popover.show_near(event.globalPosition().toPoint(), self._text)


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
