#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2023 Bitcraze AB
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
Attitude indicator widget.
"""

import sys
import math

from PyQt6 import QtGui
from PyQt6 import QtWidgets
from PyQt6.QtCore import QPoint
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt

__author__ = 'Bitcraze AB'
__all__ = ['AttitudeIndicator']


class AttitudeIndicator(QtWidgets.QWidget):
    """Widget for showing attitude"""

    def __init__(self):
        super(AttitudeIndicator, self).__init__()

        self.roll = 0
        self.pitch = 0
        self.hover = False
        self.hoverHeight = 0.0
        self.hoverTargetHeight = 0.0

        self.setMinimumSize(30, 30)
        # self.setMaximumSize(240,240)

    def setRoll(self, roll, repaint=True):
        self.roll = roll
        if repaint:
            self.repaint()

    def setPitch(self, pitch, repaint=True):
        self.pitch = pitch
        if repaint:
            self.repaint()

    def setHover(self, target, repaint=True):
        self.hoverTargetHeight = target
        self.hover = target > 0
        if repaint:
            self.repaint()

    def setBaro(self, height, repaint=True):
        self.hoverHeight = height
        if repaint:
            self.repaint()

    def setRollPitch(self, roll, pitch, repaint=True):
        self.roll = roll
        self.pitch = pitch
        if repaint:
            self.repaint()

    def paintEvent(self, e):
        qp = QtGui.QPainter()
        qp.begin(self)
        self.drawWidget(qp)
        qp.end()

    def drawWidget(self, qp):
        size = self.size()
        w = size.width()
        h = size.height()
        qp.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        diameter = max(24, min(w, h) - 18)
        radius = diameter / 2
        cx = w / 2
        cy = h / 2
        rect = QRectF(cx - radius, cy - radius, diameter, diameter)

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QtGui.QColor('#eef1f5'))
        qp.drawEllipse(QRectF(rect).adjusted(-8, -8, 8, 8))
        qp.setPen(QtGui.QPen(QtGui.QColor('#c8cdd3'), 1))
        qp.setBrush(Qt.BrushStyle.NoBrush)
        qp.drawEllipse(QRectF(rect).adjusted(-4, -4, 4, 4))

        clip_path = QtGui.QPainterPath()
        clip_path.addEllipse(rect)

        qp.save()
        qp.setClipPath(clip_path)
        qp.translate(cx, cy)
        qp.rotate(self.roll)
        qp.translate(0, self.pitch * radius / 45)

        sky = QtGui.QLinearGradient(QPointF(0, -radius), QPointF(0, 0))
        sky.setColorAt(0, QtGui.QColor('#4a90d9'))
        sky.setColorAt(1, QtGui.QColor('#a8cef0'))
        ground = QtGui.QLinearGradient(QPointF(0, 0), QPointF(0, radius))
        ground.setColorAt(0, QtGui.QColor('#8b6d3f'))
        ground.setColorAt(1, QtGui.QColor('#5c4427'))

        span = radius * 2.6
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(sky)
        qp.drawRect(QRectF(-span, -span, span * 2, span))
        qp.setBrush(ground)
        qp.drawRect(QRectF(-span, 0, span * 2, span))

        qp.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 210), 1.4))
        qp.drawLine(int(-span), 0, int(span), 0)

        ladder_font = QtGui.QFont()
        ladder_font.setPointSize(int(max(7, radius / 17)))
        qp.setFont(ladder_font)
        for pitch_mark in range(-40, 45, 5):
            if pitch_mark == 0:
                continue
            y = -pitch_mark * radius / 45
            length = radius * (0.42 if pitch_mark % 10 == 0 else 0.22)
            qp.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 185), 1))
            qp.drawLine(int(-length / 2), int(y), int(length / 2), int(y))
            if pitch_mark % 10 == 0:
                label = str(abs(pitch_mark))
                qp.drawText(int(length / 2 + 8), int(y + 4), label)
                qp.drawText(int(-length / 2 - 22), int(y + 4), label)
        qp.restore()

        qp.setPen(QtGui.QPen(QtGui.QColor('#c8cdd3'), 1.6))
        qp.setBrush(Qt.BrushStyle.NoBrush)
        qp.drawEllipse(rect)

        qp.setPen(QtGui.QPen(QtGui.QColor('#6b7280'), 1))
        tick_font = QtGui.QFont()
        tick_font.setPointSize(int(max(7, radius / 15)))
        tick_font.setWeight(QtGui.QFont.Weight.DemiBold)
        qp.setFont(tick_font)
        for angle, label in [(-90, 'W'), (-45, ''), (0, 'N'), (45, ''), (90, 'E'),
                             (180, 'S')]:
            rad = math.radians(angle)
            sx = cx + radius * 0.94 * math.sin(rad)
            sy = cy - radius * 0.94 * math.cos(rad)
            ex = cx + radius * 1.02 * math.sin(rad)
            ey = cy - radius * 1.02 * math.cos(rad)
            qp.drawLine(int(sx), int(sy), int(ex), int(ey))
            if label:
                tx = cx + radius * 0.84 * math.sin(rad)
                ty = cy - radius * 0.84 * math.cos(rad)
                qp.drawText(int(tx - 5), int(ty + 4), label)

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QtGui.QColor('#1c2024'))
        marker = QtGui.QPolygon([
            QPoint(int(cx), int(cy - radius - 2)),
            QPoint(int(cx - 5), int(cy - radius - 12)),
            QPoint(int(cx + 5), int(cy - radius - 12)),
        ])
        qp.drawPolygon(marker)

        qp.setPen(QtGui.QPen(QtGui.QColor('#f59e0b'), 2.4, Qt.PenStyle.SolidLine,
                             Qt.PenCapStyle.RoundCap))
        wing = radius * 0.36
        gap = radius * 0.08
        qp.drawLine(int(cx - wing), int(cy), int(cx - gap), int(cy))
        qp.drawLine(int(cx + gap), int(cy), int(cx + wing), int(cy))
        qp.setBrush(QtGui.QColor('#f59e0b'))
        qp.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))



if __name__ == "__main__":
    class Example(QtWidgets.QWidget):

        def __init__(self):
            super(Example, self).__init__()

            self.initUI()

        def updatePitch(self, pitch):
            self.wid.setPitch(pitch - 90)

        def updateRoll(self, roll):
            self.wid.setRoll((roll / 10.0) - 180.0)

        def updateTarget(self, target):
            self.wid.setHover(500 + target / 10.)

        def updateBaro(self, height):
            self.wid.setBaro(500 + height / 10.)

        def initUI(self):
            vbox = QtWidgets.QVBoxLayout()

            sld = QtWidgets.QSlider(Qt.Orientation.Horizontal, self)
            sld.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            sld.setRange(0, 3600)
            sld.setValue(1800)
            vbox.addWidget(sld)

            self.wid = AttitudeIndicator()

            sld.valueChanged[int].connect(self.updateRoll)
            vbox.addWidget(self.wid)

            hbox = QtWidgets.QHBoxLayout()
            hbox.addLayout(vbox)

            sldPitch = QtWidgets.QSlider(Qt.Orientation.Vertical, self)
            sldPitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            sldPitch.setRange(0, 180)
            sldPitch.setValue(90)
            sldPitch.valueChanged[int].connect(self.updatePitch)
            hbox.addWidget(sldPitch)

            sldHeight = QtWidgets.QSlider(Qt.Orientation.Vertical, self)
            sldHeight.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            sldHeight.setRange(-200, 200)
            sldHeight.setValue(0)
            sldHeight.valueChanged[int].connect(self.updateBaro)

            sldT = QtWidgets.QSlider(Qt.Orientation.Vertical, self)
            sldT.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            sldT.setRange(-200, 200)
            sldT.setValue(0)
            sldT.valueChanged[int].connect(self.updateTarget)

            hbox.addWidget(sldT)
            hbox.addWidget(sldHeight)

            self.setLayout(hbox)

            self.setGeometry(50, 50, 510, 510)
            self.setWindowTitle('Attitude Indicator')
            self.show()

        def changeValue(self, value):
            self.c.updateBW.emit(value)
            self.wid.repaint()

    def main():
        app = QtWidgets.QApplication(sys.argv)
        Example()
        sys.exit(app.exec())

    if __name__ == '__main__':
        main()
