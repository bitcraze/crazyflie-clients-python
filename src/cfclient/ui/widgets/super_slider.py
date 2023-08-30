# -*- coding: utf-8 -*-
#
# ,---------,       ____  _ __
# |  ,-^-,  |      / __ )(_) /_______________ _____  ___
# | (  O  ) |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# | / ,--'  |    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#    +------`   /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Copyright (C) 2022-2023 Bitcraze AB
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, in version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
Slider widget with advanced features
"""

from PyQt6 import QtWidgets, QtCore
from cflib.utils.callbacks import Caller


__author__ = 'Bitcraze AB'
__all__ = ['SuperSlider']


class SuperSlider(QtWidgets.QWidget):

    def __init__(self, min: float, max: float, value: float):
        super(SuperSlider, self).__init__()

        self.slider_scaling: int = 100

        self.min = min
        self.max = max
        self.value = value

        self.value_changed_cb = Caller()
        self._initUI()

    def set_value(self, value: float):
        self.input.blockSignals(True)
        self.slider.blockSignals(True)

        self.value = value
        self.input.setValue(self.value)
        self.slider.setValue(int(self.value * self.slider_scaling))

        self.input.blockSignals(False)
        self.slider.blockSignals(False)

    def _initUI(self):
        # Create controls
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, self)
        self.slider.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.slider.setRange(int(self.min * self.slider_scaling), int(self.max * self.slider_scaling))
        self.slider.setValue(int(self.value * self.slider_scaling))
        self.slider.setTickInterval(self.slider_scaling)
        self.slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)

        self.min_label = QtWidgets.QLabel(str(self.min), self)
        self.min_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self._small_font(self.min_label)

        self.input = QtWidgets.QDoubleSpinBox(self)
        self.input.setMinimum(self.min)
        self.input.setMaximum(self.max)
        self.input.setSingleStep(0.1)
        self.input.setValue(self.value)

        self.max_label = QtWidgets.QLabel(str(self.max), self)
        self.max_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._small_font(self.max_label)

        # Connect functionality
        self.slider.valueChanged.connect(self._slider_moved)
        self.input.valueChanged.connect(self._input_changed)

        # Layout
        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.slider, 0, 0, 1, 3)
        layout.addWidget(self.min_label, 1, 0)
        layout.addWidget(self.input, 1, 1)
        layout.addWidget(self.max_label, 1, 2)
        self.setLayout(layout)

    def _small_font(self, label):
        font = label.font()
        font.setPointSize(int(font.pointSize() * 0.8))
        label.setFont(font)

    def _slider_moved(self, value):
        self.input.blockSignals(True)
        self.value = value / self.slider_scaling
        self.input.setValue(self.value)
        self.input.blockSignals(False)
        self.value_changed_cb.call(self.value)

    def _input_changed(self, value):
        self.slider.blockSignals(True)
        self.value = value
        self.slider.setValue(int(self.value * self.slider_scaling))
        self.slider.blockSignals(False)
        self.value_changed_cb.call(self.value)
