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
A simple accordion: a vertical stack of sections that each have a clickable
header (arrow, title and a short summary) and a collapsible content area.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QToolButton,
                             QVBoxLayout, QWidget)

__author__ = 'Bitcraze AB'
__all__ = ['Accordion', 'AccordionSection']


class AccordionSection(QWidget):
    """One collapsible section. Put widgets in content_layout."""

    def __init__(self, title, summary='', expanded=False, parent=None):
        super().__init__(parent)

        self._toggle = QToolButton()
        self._toggle.setCheckable(True)
        self._toggle.setText(title)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setStyleSheet("QToolButton { border: none; }")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.toggled.connect(self._set_expanded)

        self._summary = QLabel(summary)
        self._summary.setEnabled(False)

        header = QHBoxLayout()
        header.addWidget(self._toggle)
        header.addStretch()
        header.addWidget(self._summary)

        self._content = QFrame()
        self.content_layout = QVBoxLayout(self._content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self._content)

        self._toggle.setChecked(expanded)
        self._set_expanded(expanded)

    def set_summary(self, text):
        self._summary.setText(text)

    def is_expanded(self):
        return self._toggle.isChecked()

    def set_expanded(self, expanded):
        self._toggle.setChecked(expanded)

    def _set_expanded(self, expanded):
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._content.setVisible(expanded)


class Accordion(QWidget):
    """A vertical stack of AccordionSections separated by thin lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addStretch()

    def add_section(self, title, summary='', expanded=False):
        section = AccordionSection(title, summary, expanded)
        if self._layout.count() > 1:
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            self._layout.insertWidget(self._layout.count() - 1, line)
        self._layout.insertWidget(self._layout.count() - 1, section)
        return section
