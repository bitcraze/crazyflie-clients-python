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
Attitude indicator widget.
"""

import sys

from PyQt5 import QtGui
from PyQt5 import QtWidgets, QtCore

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

        qp.translate(w / 2, h / 2)
        qp.rotate(self.roll)
        qp.translate(0, (self.pitch * h) / 50)
        qp.translate(-w / 2, -h / 2)
        qp.setRenderHint(qp.Antialiasing)

        font = QtGui.QFont('Serif', 7, QtGui.QFont.Light)
        qp.setFont(font)

        # Draw the blue
        qp.setPen(QtGui.QColor(0, 61, 144))
        qp.setBrush(QtGui.QColor(0, 61, 144))
        qp.drawRect(-w, h / 2, 3 * w, -3 * h)

        # Draw the marron
        qp.setPen(QtGui.QColor(59, 41, 39))
        qp.setBrush(QtGui.QColor(59, 41, 39))
        qp.drawRect(-w, h / 2, 3 * w, 3 * h)

        pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5,
                         QtCore.Qt.SolidLine)
        qp.setPen(pen)
        qp.drawLine(-w, h / 2, 3 * w, h / 2)

        # Drawing pitch lines
        for ofset in [-180, 0, 180]:
            for i in range(-900, 900, 25):
                pos = (((i / 10.0) + 25 + ofset) * h / 50.0)
                if i % 100 == 0:
                    length = 0.35 * w
                    if i != 0:
                        if ofset == 0:
                            qp.drawText((w / 2) + (length / 2) + (w * 0.06),
                                        pos, "{}".format(-i / 10))
                            qp.drawText((w / 2) - (length / 2) - (w * 0.08),
                                        pos, "{}".format(-i / 10))
                        else:
                            qp.drawText((w / 2) + (length / 2) + (w * 0.06),
                                        pos, "{}".format(i / 10))
                            qp.drawText((w / 2) - (length / 2) - (w * 0.08),
                                        pos, "{}".format(i / 10))
                elif i % 50 == 0:
                    length = 0.2 * w
                else:
                    length = 0.1 * w

                qp.drawLine((w / 2) - (length / 2), pos,
                            (w / 2) + (length / 2), pos)

        qp.setWorldMatrixEnabled(False)

        pen = QtGui.QPen(QtGui.QColor(0, 0, 0), 2,
                         QtCore.Qt.SolidLine)
        qp.setBrush(QtGui.QColor(0, 0, 0))
        qp.setPen(pen)
        qp.drawLine(0, h / 2, w, h / 2)

        # Draw Hover vs Target

        qp.setWorldMatrixEnabled(False)

        pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 2,
                         QtCore.Qt.SolidLine)
        qp.setBrush(QtGui.QColor(255, 255, 255))
        qp.setPen(pen)
        fh = max(7, h / 50)
        font = QtGui.QFont('Sans', fh, QtGui.QFont.Light)
        qp.setFont(font)
        qp.resetTransform()

        qp.translate(0, h / 2)
        if not self.hover:
            # height
            qp.drawText(w - fh * 10, fh / 2, str(round(self.hoverHeight, 2)))

        if self.hover:
            # target height (center)
            qp.drawText(
                w - fh * 10, fh / 2, str(round(self.hoverTargetHeight, 2)))
            diff = round(self.hoverHeight - self.hoverTargetHeight, 2)
            pos_y = -h / 6 * diff

            # cap to +- 2.8m
            if diff < -2.8:
                pos_y = -h / 6 * -2.8
            elif diff > 2.8:
                pos_y = -h / 6 * 2.8
            else:
                pos_y = -h / 6 * diff

            # difference from target (moves up and down +- 2.8m)
            qp.drawText(w - fh * 3.8, pos_y + fh / 2, str(diff))
            # vertical line
            qp.drawLine(w - fh * 4.5, 0, w - fh * 4.5, pos_y)
            # left horizontal line
            qp.drawLine(w - fh * 4.7, 0, w - fh * 4.5, 0)
            # right horizontal line
            qp.drawLine(w - fh * 4.2, pos_y, w - fh * 4.5, pos_y)


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

            sld = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
            sld.setFocusPolicy(QtCore.Qt.NoFocus)
            sld.setRange(0, 3600)
            sld.setValue(1800)
            vbox.addWidget(sld)

            self.wid = AttitudeIndicator()

            sld.valueChanged[int].connect(self.updateRoll)
            vbox.addWidget(self.wid)

            hbox = QtWidgets.QHBoxLayout()
            hbox.addLayout(vbox)

            sldPitch = QtWidgets.QSlider(QtCore.Qt.Vertical, self)
            sldPitch.setFocusPolicy(QtCore.Qt.NoFocus)
            sldPitch.setRange(0, 180)
            sldPitch.setValue(90)
            sldPitch.valueChanged[int].connect(self.updatePitch)
            hbox.addWidget(sldPitch)

            sldHeight = QtWidgets.QSlider(QtCore.Qt.Vertical, self)
            sldHeight.setFocusPolicy(QtCore.Qt.NoFocus)
            sldHeight.setRange(-200, 200)
            sldHeight.setValue(0)
            sldHeight.valueChanged[int].connect(self.updateBaro)

            sldT = QtWidgets.QSlider(QtCore.Qt.Vertical, self)
            sldT.setFocusPolicy(QtCore.Qt.NoFocus)
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
        sys.exit(app.exec_())

    if __name__ == '__main__':
        main()
