# -*- coding: utf-8 -*-
#
#    ||          ____  _ __
# +------+      / __ )(_) /_______________ _____  ___
# | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#  ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Crazyflie client software
#
# Copyright (C) 2011-2012 Bitcraze AB
#

import math
import sys
from PyQt4 import QtGui, QtCore

from cfclient.ui.widgets.plotwidget import PlotWidget
from cfclient.ui.widgets.rtplotwidget import PlotDataSet


class PlotTest(QtGui.QWidget):

    def __init__(self):
        super(PlotTest, self).__init__()

        self.timer = QtCore.QTimer()
        self.timer.setInterval(10)
        self.connect(self.timer, QtCore.SIGNAL("timeout()"), self.adddata)
        self.initUI()

    def initUI(self):
        #QtGui.QToolTip.setFont(QtGui.QFont('SansSerif', 10))

        self.fp = PlotWidget(title="A nice test plot")
        self.cosDataSet = PlotDataSet("Graph showing cos",
                                      QtCore.Qt.black,
                                      [180, -180])
        self.sinDataSet = PlotDataSet("One showing sin",
                                      QtCore.Qt.blue,
                                      [180, -180])
        self.negcosDataSet = PlotDataSet("Another one showing -cos",
                                         QtCore.Qt.green,
                                         [180, -180])
        self.negsinDataSet = PlotDataSet("And the last one showing -sin",
                                         QtCore.Qt.magenta,
                                         [180, -180])

        self.fp.addDataset(self.cosDataSet)
        self.fp.addDataset(self.sinDataSet)
        self.fp.addDataset(self.negcosDataSet)
        self.fp.addDataset(self.negsinDataSet)
        self.setGeometry(100, 100, 800, 500)
        self.setWindowTitle('FastPlotTest')
        layout = QtGui.QGridLayout(self)
        layout.addWidget(self.fp)
        self.setLayout(layout)
        self.show()
        self.timer.start()
        self.mod = 0.0

    def adddata(self):
        self.mod = self.mod + 0.01
        if (self.mod > math.pi):
            self.mod = -math.pi
        self.cosDataSet.addData(360 * math.cos(self.mod))
        self.sinDataSet.addData(180 * math.sin(self.mod))
        self.negcosDataSet.addData(-180 * math.cos(self.mod))
        self.negsinDataSet.addData(-180 * math.sin(self.mod))


def main():

    app = QtGui.QApplication(sys.argv)
    ex = PlotTest()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
