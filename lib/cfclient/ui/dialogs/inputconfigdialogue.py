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

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Dialogue used to select and configure an inputdevice. This includes mapping buttuns and
axis to match controls for the Crazyflie.
"""

__author__ = 'Bitcraze AB'
__all__ = ['InputConfigDialogue']

import sys
import json
import logging

logger = logging.getLogger(__name__)

from cfclient.utils.config_manager import ConfigManager
from cflib.crtp.exceptions import CommunicationException
from pygame.locals import *

from PyQt4 import Qt, QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *

from cfclient.utils.input import JoystickReader

inputconfig_widget_class, connect_widget_base_class = uic.loadUiType(sys.path[0] + '/cfclient/ui/dialogs/inputconfigdialogue.ui')

class InputConfigDialogue(QtGui.QWidget, inputconfig_widget_class):

    def __init__(self, joystickReader, *args):
        super(InputConfigDialogue, self).__init__(*args)
        self.setupUi(self)
        self.joystickReader = joystickReader

        self.rawinputreader = RawJoystickReader(self.joystickReader)
        self.rawinputreader.start()

        self.rawinputreader.rawAxisUpdateSignal.connect(self.rawAxisUpdate)
        self.rawinputreader.rawButtonUpdateSignal.connect(self.rawButtonUpdate)

        self.cancelButton.clicked.connect(self.close)
        self.saveButton.clicked.connect(self.saveConfig)
        
        self.detectPitch.clicked.connect(lambda : self.doAxisDetect("pitch", "Pitch axis",
                                                 "Press the pitch axis to max forward pitch"))
        self.detectRoll.clicked.connect(lambda : self.doAxisDetect("roll", "Roll axis",
                                                 "Press the roll axis to max right roll"))
        self.detectYaw.clicked.connect(lambda : self.doAxisDetect("yaw", "Yaw axis",
                                                "Press the yaw axis to max rotation right"))
        self.detectThrust.clicked.connect(lambda : self.doAxisDetect("thrust", "Thrust axis",
                                                   "Press the thrust axis to max thrust"))
        self.detectPitchPos.clicked.connect(lambda : self.doButtonDetect("pitchPos", "Pitch Cal Positive",
                                                  "Press the button for Pitch postive calibration"))
        self.detectPitchNeg.clicked.connect(lambda : self.doButtonDetect("pitchNeg", "Pitch Cal Negative",
                                                     "Press the button for Pitch negative calibration"))
        self.detectRollPos.clicked.connect(lambda : self.doButtonDetect("rollPos", "Roll Cal Positive",
                                                    "Press the button for Roll positive calibration"))
        self.detectRollNeg.clicked.connect(lambda : self.doButtonDetect("rollNeg", "Roll Cal Negative",
                                                    "Press the button for Roll negative calibration"))
        self.detectKillswitch.clicked.connect(lambda : self.doButtonDetect("killswitch", "Killswtich",
                                                       "Press the button for the killswitch (will disable motors)"))
        self.detectExitapp.clicked.connect(lambda : self.doButtonDetect("exitapp", "Exit application",
                                                    "Press the button for the exiting the application"))

        self.configButton.clicked.connect(self.startConfigOfInputDevice)
        self.loadButton.clicked.connect(self.loadConfig)
        self.deleteButton.clicked.connect(self.deleteConfig)

        self.box = None
        self.detectButtons = [self.detectPitch, self.detectRoll, self.detectYaw, self.detectThrust, self.detectPitchPos, self.detectPitchNeg,
                         self.detectRollPos, self.detectRollNeg, self.detectKillswitch, self.detectExitapp]

        self._reset_mapping()
        self.btnDetect = ""
        self.axisDetect = ""

        for d in self.joystickReader.getAvailableDevices():
            self.inputDeviceSelector.addItem(d["name"], d["id"])

        if (len(self.joystickReader.getAvailableDevices()) > 0):
            self.configButton.setEnabled(True)

    def _reset_mapping(self):
        self.buttonmapping = {
            "pitchPos": {"id":-1, "indicator":self.pitchPos},
            "pitchNeg": {"id":-1, "indicator":self.pitchNeg},
            "rollPos": {"id":-1, "indicator":self.rollPos},
            "rollNeg": {"id":-1, "indicator":self.rollNeg},
            "killswitch": {"id":-1, "indicator":self.killswitch},
            "exitapp": {"id":-1, "indicator":self.exitapp}
            }

        self.axismapping = {
            "pitch": {"id":-1, "indicator":self.pitchAxisValue, "scale":-1.0},
            "roll": {"id":-1, "indicator":self.rollAxisValue, "scale":-1.0},
            "yaw": {"id":-1, "indicator":self.yawAxisValue, "scale":-1.0},
            "thrust": {"id":-1, "indicator":self.thrustAxisValue, "scale":-1.0}
            }

    def cancelConfigBox(self, button):
        self.axisDetect = ""
        self.btnDetect = ""

    def showConfigBox(self, caption, message):
        self.box = QMessageBox()
        self.box.setWindowTitle(caption)
        self.box.setText(message)
        self.box.setButtonText(1, "Cancel")
        self.box.setWindowFlags(Qt.Dialog|Qt.MSWindowsFixedSizeDialogHint)
        self.box.buttonClicked.connect(self.cancelConfigBox)
        self.box.show()

    def startConfigOfInputDevice(self):
        self.joystickReader.enableRawReading(self.inputDeviceSelector.currentIndex())
        self.rawinputreader.startReading()
        self.populateDropDown()
        self.profileCombo.setEnabled(True)
        for b in self.detectButtons:
            b.setEnabled(True)

    def rawAxisUpdate(self, data):
        if (len(self.axisDetect) > 0):
            for a in data:
                # TODO: Some axis on the PS3 controller are maxed out by default which causes problems...check change instead?
                # TODO: This assumes a range [-1.0,1.0] from input device driver, but is that safe?
                if (abs(data[a]) > 0.8 and abs(data[a]) < 1.0 and len(self.axisDetect) > 0):
                    self.axismapping[self.axisDetect]["id"] = a
                    if (data[a] >= 0):
                        self.axismapping[self.axisDetect]["scale"] = 1.0
                    else:
                        self.axismapping[self.axisDetect]["scale"] = -1.0
                    self.axisDetect = ""
                    self.checkAndEnableSave()
                    if (self.box != None):
                        self.box.close()
        for a in data:
            for m in self.axismapping:
                if (self.axismapping[m]["id"] == a):
                    self.axismapping[m]["indicator"].setValue(50+data[a]*50*self.axismapping[m]["scale"])

    def rawButtonUpdate(self, data):
        if (len(self.btnDetect) > 0):
            for b in data:
                if (data[b] > 0):
                    self.buttonmapping[self.btnDetect]["id"] = b
                    self.btnDetect = ""
                    self.checkAndEnableSave()
                    if (self.box != None):
                        self.box.close()
        for b in data:
            for m in self.buttonmapping:
                if (self.buttonmapping[m]["id"] == b):
                    if (data[b] == 0):
                        self.buttonmapping[m]["indicator"].setChecked(False)
                    else:
                        self.buttonmapping[m]["indicator"].setChecked(True)

    def checkAndEnableSave(self):
        canSave = True
        for m in self.axismapping:
            if (self.axismapping[m]["id"] == -1):
                canSave = False
        if (canSave == True):
            self.saveButton.setEnabled(True)

    def populateDropDown(self):
        configs = ConfigManager().get_list_of_configs()
        if len(configs):
            self.loadButton.setEnabled(True)
        for c in configs:
            self.profileCombo.addItem(c)
            logger.info("Found inputdevice [%s]", c)

    def doAxisDetect(self, varname, caption, message):
        self.axisDetect = varname
        self.showConfigBox(caption, message)

    def doButtonDetect(self, varname, caption, message):
        self.btnDetect = varname
        self.showConfigBox(caption, message)

    def showError(self, caption, message):
        QMessageBox.critical(self,caption, message)  

    def parseButtonConfig(self, key, btnId, scale):
        newKey = ""
        if ("pitch" in key and scale > 0):
            newKey = "pitchPos"
        if ("pitch"in key and scale < 0):
            newKey = "pitchNeg"
        if ("roll" in key and scale > 0):
            newKey = "rollPos"
        if ("roll" in key and scale < 0):
            newKey = "rollNeg"
        if ("estop" in key):
            newKey = "killswitch"
        if ("exit" in key):
            newKey = "exitapp"
        if (len(newKey) > 0):
            self.buttonmapping[newKey]['id'] = btnId
        else:
            logger.warning("Could not find new key for [%s]", key)

    def parseAxisConfig(self, key, axisId, scale):
        self.axismapping[key]['id'] = axisId
        self.axismapping[key]['scale'] = scale

    def loadConfig(self):
        conf = ConfigManager().get_config(self.profileCombo.currentText())
        self._reset_mapping()
        if (conf != None):
            for c in conf:
                if (conf[c]['type'] == "Input.BUTTON"):
                    self.parseButtonConfig(conf[c]['key'],
                                           conf[c]['id'], conf[c]['scale'])
                elif (conf[c]['type'] == "Input.AXIS"):
                    self.parseAxisConfig(conf[c]['key'],
                                         conf[c]['id'], conf[c]['scale'])
        else:
            logger.warning("Could not load configfile [%s]", self.profileCombo.currentText())
            self.showError("Could not load config", "Could not load config [%s]" % self.profileCombo.currentText())
        self.checkAndEnableSave()

    def deleteConfig(self):
        logger.warning("deleteConfig not implemented")

    def saveConfig(self):
        configName = str(self.profileCombo.currentText())

        saveConfig = {}
        inputConfig = {'inputdevice': {'axis':[]}}
        for a in self.axismapping:
            newC = {}
            newC['key'] = a
            newC['name'] = a
            newC['id'] = self.axismapping[a]['id']
            newC['scale'] = self.axismapping[a]['scale']
            newC['type'] = "Input.AXIS"
            inputConfig['inputdevice']['axis'].append(newC)

        for a in self.buttonmapping:
            newC = {}
            newC['id'] = self.buttonmapping[a]['id']
            newC['type'] = "Input.BUTTON"
            if (a.find("Neg") >= 0):
                newC['scale'] = -1.0
            else:
                newC['scale'] = 1.0

            if ("pitch" in a):
                newC['key'] = "pitchcal"
                newC['name'] = a

            if ("roll" in a):
                newC['key'] = "rollcal"
                newC['name'] = a

            if ("killswitch" in a):
                newC['key'] = "estop"
                newC['name'] = a

            if ("exit" in a):
                newC['key'] = "exit"
                newC['name'] = a

            inputConfig['inputdevice']['axis'].append(newC)

        inputConfig['inputdevice']['name'] = configName
        inputConfig['inputdevice']['updateperiod'] = 10
        saveConfig['inputconfig'] = inputConfig

        config_name = self.profileCombo.currentText()
        filename = ConfigManager().configs_dir + "/%s.json" % config_name
        logger.info("Saving config to [%s]", filename)
        json_data=open(filename, 'w')
        json_data.write(json.dumps(saveConfig, indent=2))
        json_data.close()

        ConfigManager().conf_needs_reload.call(config_name)
        self.close()

    def showEvent(self, event):
        self.joystickReader.stopInputSignal.emit()

    def closeEvent(self, event):
        self.rawinputreader.stopReading()

class RawJoystickReader(QThread):

    rawAxisUpdateSignal = pyqtSignal(object)
    rawButtonUpdateSignal = pyqtSignal(object)

    def __init__(self, joystickReader):
        QThread.__init__(self)

        self.joystickReader = joystickReader
        self.readTimer = QTimer()
        self.readTimer.setInterval(25);
        self.connect(self.readTimer, SIGNAL("timeout()"), self.readInput)

    def stopReading(self):
        self.readTimer.stop()

    def startReading(self):
        self.readTimer.start()

    @pyqtSlot()
    def readInput(self):
        [rawaxis,rawbuttons] = self.joystickReader.readRawValues()
        self.rawAxisUpdateSignal.emit(rawaxis)
        self.rawButtonUpdateSignal.emit(rawbuttons)

