#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
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
This class provides a spin box with hexadecimal numbers and arbitrarily length
(i.e. not limited by 32 bit).
"""

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QAbstractSpinBox

__author__ = 'Bitcraze AB'
__all__ = ['HexSpinBox']


class HexSpinBox(QAbstractSpinBox):

    def __init__(self, *args):
        QAbstractSpinBox.__init__(self, *args)
        regexp = QtCore.QRegExp('^0x[0-9A-Fa-f]{1,10}$')
        self.validator = QtGui.QRegExpValidator(regexp)
        self._value = 0

    def validate(self, text, pos):
        return self.validator.validate(text, pos)

    def textFromValue(self, value):
        return "0x%X" % value

    def valueFromText(self, text):
        return int(str(text), 0)

    def setValue(self, value):
        self._value = value
        self.lineEdit().setText(self.textFromValue(value))

    def value(self):
        self._value = self.valueFromText(self.lineEdit().text())
        return self._value

    def stepBy(self, steps):
        self.setValue(self._value + steps)

    def stepEnabled(self):
        return (QAbstractSpinBox.StepUpEnabled |
                QAbstractSpinBox.StepDownEnabled)
