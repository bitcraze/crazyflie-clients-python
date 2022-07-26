#!/usr/bin/env python

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import pyqtProperty
from PyQt5 import QtCore, QtWidgets
import time


class LighthouseBasestationGeometryWizard(QtWidgets.QWizard):
    def __init__(self, parent=None):
        super(LighthouseBasestationGeometryWizard, self).__init__(parent)
        self.addPage(Page1(self))
        self.addPage(Page2(self))
        self.setWindowTitle("PyQt5 Wizard Example - pythonspot.com")
        self.resize(640,480)

class Page1(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super(Page1, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 1. Put the Crazyflie where you want the origin of your coordinate system.')
        start_measurement_button = QtWidgets.QPushButton("Start measurement")
        start_measurement_button.clicked.connect(self.btn_clicked)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)
        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        for it in range(5):
            print(it)
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

class Page2(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super(Page2, self).__init__(parent)
        self.label1 = QtWidgets.QLabel()
        self.label2 = QtWidgets.QLabel()
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.label1)
        layout.addWidget(self.label2)
        self.setLayout(layout)

    def initializePage(self):
        self.label1.setText("Example text")
        self.label2.setText("Example text")

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    wizard = LighthouseBasestationGeometryWizard()
    wizard.show()
    sys.exit(app.exec_())

