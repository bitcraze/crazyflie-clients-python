#!/usr/bin/env python

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import pyqtProperty
from PyQt5 import QtCore, QtWidgets
import time
REFERENCE_DIST = 1.0
ITERATION_MAX_NR = 2
DEFAULT_RECORD_TIME = 20

class LighthouseBasestationGeometryWizard(QtWidgets.QWizard):
    def __init__(self, parent=None):
        super(LighthouseBasestationGeometryWizard, self).__init__(parent)
        self.addPage(Page1(self))
        self.addPage(Page2(self))
        self.addPage(Page3(self))
        self.addPage(Page4(self))
        self.addPage(Page5(self))
        self.addPage(Page6(self))
        self.setWindowTitle("Lighthouse Basestation Geometry Wizard")
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
        for it in range(ITERATION_MAX_NR):
            print(it)
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

class Page2(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super(Page2, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText(f'Step 2. Put the Crazyflie on the positive X-axis,  exactly {REFERENCE_DIST} meters from the origin.\n ' +
              'This position defines the direction of the X-axis, but it is also used for scaling of the system.')
        start_measurement_button = QtWidgets.QPushButton("Start measurement")
        start_measurement_button.clicked.connect(self.btn_clicked)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)
        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        for it in range(ITERATION_MAX_NR):
            print(it)
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

class Page3(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super(Page3, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 3. Put the Crazyflie somehere in the XY-plane, but not on the X-axis. \n')
        start_measurement_button = QtWidgets.QPushButton("Start measurement")
        start_measurement_button.clicked.connect(self.btn_clicked)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)
        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        for it in range(ITERATION_MAX_NR):
            print(it)
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done


class Page4(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super(Page4, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 4. We will now record data from the space you plan to fly in and optimize the base station \n ' +
              'geometry based on this data. Move the Crazyflie around, try to cover all of the space, make sure \n ' +
              'all the base stations are received and do not move too fast.')
        start_measurement_button = QtWidgets.QPushButton("Start measurement")
        start_measurement_button.clicked.connect(self.btn_clicked)
        self.fill_record_times = QtWidgets.QLineEdit(str(DEFAULT_RECORD_TIME))


        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(self.fill_record_times)
        layout.addWidget(start_measurement_button)

        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        print(self.fill_record_times.text())
        for it in range(ITERATION_MAX_NR):
            print(int(it))
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done


class Page5(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super(Page5, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 5. We will now estimate Geometry! Press the button.')
        start_measurement_button = QtWidgets.QPushButton("Estimate geometry")
        start_measurement_button.clicked.connect(self.btn_clicked)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)

        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        print('Estimating geometry...')
        for it in range(ITERATION_MAX_NR):
            print(int(it))
            time.sleep(1)
        self.is_done = True
        print('  Geometry estimated!')
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

class Page6(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super(Page6, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 6. Double check the basestations geometry. If it looks good, press the button')
        start_measurement_button = QtWidgets.QPushButton("Upload geometry to Crazyflie")
        start_measurement_button.clicked.connect(self.btn_clicked)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)

        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        print('Geometry uploading...')
        for it in range(ITERATION_MAX_NR):
            print(int(it))
            time.sleep(1)
        self.is_done = True
        print('  Geometry uploaded!')
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done



if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    wizard = LighthouseBasestationGeometryWizard()
    wizard.show()
    sys.exit(app.exec_())

