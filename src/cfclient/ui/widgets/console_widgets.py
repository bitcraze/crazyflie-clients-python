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
The parts of the console tab that show the state of the consoles, from the ConsoleModel.
"""

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                             QTextEdit, QVBoxLayout)

from cfclient.ui.widgets.segmented_control import dot
from cfclient.utils.console_model import ALL, display_name, segment_label, split_path

__author__ = 'Bitcraze AB'
__all__ = ['AllBox', 'ErrorPanel', 'ConsoleLogView', 'CurrentPageStack']


ERROR_PATTERN = re.compile(r'\berror|assert|\bfail', re.IGNORECASE)
WARNING_PATTERN = re.compile(r'\bwarn', re.IGNORECASE)


def _is_dark():
    return QApplication.palette().base().color().lightness() < 128


def _severity_color(text, dark):
    """Red for errors and asserts, orange for warnings, else None"""
    if ERROR_PATTERN.search(text):
        return '#ff6b6b' if dark else '#c62828'
    if WARNING_PATTERN.search(text):
        return '#ffa94d' if dark else '#c76a00'
    return None


def _format(color=None):
    fmt = QTextCharFormat()
    if color is not None:
        fmt.setForeground(QColor(color))
    return fmt


def _muted():
    return QApplication.palette().placeholderText().color().name()


def _mono():
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


def path_html(path):
    if segment_label(path):
        return display_name(path)
    prefix, name = split_path(path)
    if not prefix:
        return name
    return '<span style="color: %s">%s</span>%s' % (_muted(), prefix, name)


def path_label(path):
    label = QLabel(path_html(path))
    label.setTextFormat(Qt.TextFormat.RichText)
    if not segment_label(path):
        label.setFont(_mono())
    return label


def small(text, mono=False):
    label = QLabel(text)
    label.setWordWrap(True)
    font = _mono() if mono else label.font()
    font.setPointSizeF(max(font.pointSizeF() - 1, 7))
    label.setFont(font)
    label.setStyleSheet('color: %s;' % _muted())
    return label


class CurrentPageStack(QStackedWidget):
    """A stack that is as big as its current page, and not its biggest page"""

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page else super().sizeHint()

    def minimumSizeHint(self):
        page = self.currentWidget()
        return page.minimumSizeHint() if page else super().minimumSizeHint()


class _Row(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path)
        else:
            super().mousePressEvent(event)


class _Box(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(10, 10, 10, 10)
        self.layout_.setSpacing(6)


class AllBox(_Box):
    select_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._title = QLabel()
        self.layout_.addWidget(self._title)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(2)
        self.layout_.addLayout(self._rows)
        self.layout_.addStretch(1)
        self._paths = None

    def show_consoles(self, model):
        paths = model.open_paths
        if paths != self._paths:
            self._paths = list(paths)
            while self._rows.count():
                self._rows.takeAt(0).widget().deleteLater()
            self._title.setText('Showing %d open consoles' % len(paths))
            for path in paths:
                row = _Row(path)
                row.setToolTip('Show only this console')
                row.clicked.connect(self.select_requested)
                column = QVBoxLayout(row)
                column.setContentsMargins(0, 3, 0, 3)
                column.setSpacing(0)
                layout = QHBoxLayout()
                layout.setSpacing(8)
                layout.addWidget(dot(model.states[path].color))
                layout.addWidget(path_label(path), 1)
                column.addLayout(layout)
                if segment_label(path):
                    # The technical name, for reports
                    detail = small(path, mono=True)
                    detail.setWordWrap(False)
                    detail.setContentsMargins(17, 0, 0, 0)
                    column.addWidget(detail)
                self._rows.addWidget(row)


class ErrorPanel(QFrame):
    retry_requested = pyqtSignal(str)
    dismissed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._path = None
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)
        self._headline = QLabel()
        self._headline.setTextFormat(Qt.TextFormat.RichText)
        self._headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body = QLabel()
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._details = small('', mono=True)
        self._details.setWordWrap(False)
        self._details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._headline)
        layout.addWidget(self._body)
        layout.addWidget(self._details)

        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._retry = QPushButton('Try again')
        self._retry.clicked.connect(lambda: self.retry_requested.emit(self._path))
        close = QPushButton('Close tab')
        close.clicked.connect(lambda: self.dismissed.emit(self._path))
        buttons.addWidget(self._retry)
        buttons.addWidget(close)
        layout.addSpacing(6)
        layout.addLayout(buttons)

    def set_enabled(self, enabled):
        self._retry.setEnabled(enabled)

    def show_error(self, path, errno, message):
        self._path = path
        self._headline.setText('<b>%s</b> could not be started' % path)
        if errno is not None:
            self._body.setText('The Crazyflie refused the request.')
            self._details.setText('Details: firmware errno %d' % errno)
        else:
            self._body.setText('The Crazyflie did not answer.')
            self._details.setText('Details: %s' % message)


class ConsoleLogView(QTextEdit):
    """The log of one console, or of all open consoles merged with a timestamp and the name on every line"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self._default_font = self.font()
        self._key = None
        self._last_seq = 0
        self._partial_start = None
        self._name_width = 0

    def reset(self):
        self._key = None

    def refresh(self, model):
        key = model.selected
        scrollbar = self.verticalScrollBar()
        at_end = scrollbar.value() >= scrollbar.maximum() - 2
        previous = scrollbar.value()

        if key != self._key or self._name_width != self._width_for(model, key):
            self._draw_all(model, key)
        else:
            self._remove_partials()
            self._append(model, key, model.lines_after(key, self._last_seq))
            self._append_partials(model, key)

        # Stay at the end if it was at the end
        scrollbar.setValue(scrollbar.maximum() if at_end else previous)

    @staticmethod
    def _width_for(model, key):
        if key != ALL:
            return 0
        return max((len(display_name(p)) for p in model.open_paths), default=0)

    def _draw_all(self, model, key):
        self.clear()
        self._key = key
        self._last_seq = 0
        self._name_width = self._width_for(model, key)
        self.setFont(_mono() if key == ALL else self._default_font)
        lines = model.view_lines(key)
        self._append(model, key, lines)
        self._append_partials(model, key)

    def _insert_line(self, cursor, model, key, line, dark):
        if key == ALL:
            cursor.insertText('%9s  ' % ('+%.3f' % line.t), _format(_muted()))
            cursor.insertText('%-*s  ' % (self._name_width, display_name(line.path)),
                              _format(model.states[line.path].color))
        if line.separator:
            cursor.insertText('--- %s ---' % line.text, _format(_muted()))
        else:
            cursor.insertText(line.text, _format(_severity_color(line.text, dark)))

    def _append(self, model, key, lines):
        if not lines:
            return
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        dark = _is_dark()
        cursor.beginEditBlock()
        for line in lines:
            self._insert_line(cursor, model, key, line, dark)
            cursor.insertBlock()
            self._last_seq = line.seq
        cursor.endEditBlock()

    def _append_partials(self, model, key):
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._partial_start = cursor.position()
        partials = model.view_partials(key)
        dark = _is_dark()
        for index, line in enumerate(partials):
            self._insert_line(cursor, model, key, line, dark)
            if index < len(partials) - 1:
                cursor.insertBlock()

    def _remove_partials(self):
        if self._partial_start is None:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(self._partial_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
