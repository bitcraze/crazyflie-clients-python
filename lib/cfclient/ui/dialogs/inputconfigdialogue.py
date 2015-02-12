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

from PyQt4 import Qt, QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *

from cfclient.utils.input import JoystickReader

(inputconfig_widget_class,
connect_widget_base_class) = (uic.loadUiType(sys.path[0] +
                             '/cfclient/ui/dialogs/inputconfigdialogue.ui'))


class InputConfigDialogue(QtGui.QWidget, inputconfig_widget_class):

    def __init__(self, joystickReader, *args):
        super(InputConfigDialogue, self).__init__(*args)
        self.setupUi(self)
        self.joystickReader = joystickReader

        self.rawinputreader = RawJoystickReader(self.joystickReader)
        self.rawinputreader.start()

        self.rawinputreader.rawAxisUpdateSignal.connect(self.rawAxisUpdate)
        self.rawinputreader.rawButtonUpdateSignal.connect(self.rawButtonUpdate)
        self.rawinputreader.mapped_values_signal.connect(self._update_mapped_values)

        self.cancelButton.clicked.connect(self.close)
        self.saveButton.clicked.connect(self.saveConfig)
        
        self.detectPitch.clicked.connect(lambda : self.doAxisDetect("pitch", "Pitch axis",
                                                 "Center the pitch axis then do max %s pitch", ["forward", "backward"]))
        self.detectRoll.clicked.connect(lambda : self.doAxisDetect("roll", "Roll axis",
                                                 "Center the roll axis and then do max %s roll", ["right", "left"]))
        self.detectYaw.clicked.connect(lambda : self.doAxisDetect("yaw", "Yaw axis",
                                                "Center the yaw axis and then do max %s yaw", ["right", "left"]))
        self.detectThrust.clicked.connect(lambda : self.doAxisDetect("thrust", "Thrust axis",
                                                   "Center the thrust axis do max thrust (also used to adjust target altitude in altitude hold mode)"))
        self.detectPitchPos.clicked.connect(lambda : self.doButtonDetect("pitchPos", "Pitch Cal Positive",
                                                  "Press the button for Pitch postive calibration"))
        self.detectPitchNeg.clicked.connect(lambda : self.doButtonDetect("pitchNeg", "Pitch Cal Negative",
                                                     "Press the button for Pitch negative calibration"))
        self.detectRollPos.clicked.connect(lambda : self.doButtonDetect("rollPos", "Roll Cal Positive",
                                                    "Press the button for Roll positive calibration"))
        self.detectRollNeg.clicked.connect(lambda : self.doButtonDetect("rollNeg", "Roll Cal Negative",
                                                    "Press the button for Roll negative calibration"))
        self.detectKillswitch.clicked.connect(lambda : self.doButtonDetect("killswitch", "Killswitch",
                                                       "Press the button for the killswitch (will disable motors)"))
        self.detectAlt1.clicked.connect(lambda : self.doButtonDetect("alt1", "Alternative function 1",
                                                       "The alternative function 1 that will do a callback"))
        self.detectAlt2.clicked.connect(lambda : self.doButtonDetect("alt2", "Alternative function 2",
                                                       "The alternative function 2 that will do a callback"))
        self.detectExitapp.clicked.connect(lambda : self.doButtonDetect("exitapp", "Exit application",
                                                    "Press the button for the exiting the application"))
        self.detectAltHold.clicked.connect(lambda : self.doButtonDetect("althold", "Altitude hold",
                                                    "Press the button for altitude hold mode activation (releasing returns to manual mode)"))        

        self.configButton.clicked.connect(self.startConfigOfInputDevice)
        self.loadButton.clicked.connect(self.loadConfig)
        self.deleteButton.clicked.connect(self.deleteConfig)

        self.box = None
        self.combinedButton = None
        self.detectButtons = [self.detectPitch, self.detectRoll,
                              self.detectYaw, self.detectThrust,
                              self.detectPitchPos, self.detectPitchNeg,
                              self.detectRollPos, self.detectRollNeg,
                              self.detectKillswitch, self.detectExitapp,
                              self.detectAltHold, self.detectAlt1, self.detectAlt2]

        self._reset_mapping()
        self.btnDetect = ""
        self.axisDetect = ""
        self.combinedDetection = 0
        self._prev_combined_id = None

        self._maxed_axis = []
        self._mined_axis = []

        for d in self.joystickReader.getAvailableDevices():
            self.inputDeviceSelector.addItem(d.name, d.id)

        if (len(self.joystickReader.getAvailableDevices()) > 0):
            self.configButton.setEnabled(True)

        self._value_to_indicator_map = {
            "pitch": self.pitchAxisValue,
            "roll": self.rollAxisValue,
            "yaw": self.yawAxisValue,
            "thrust": self.thrustAxisValue
        }

        self._map = {}
        self._saved_open_device = None

    def _reset_mapping(self):
        self.buttonmapping = {
            "pitchPos": {"id":-1, "indicator": self.pitchPos},
            "pitchNeg": {"id":-1, "indicator": self.pitchNeg},
            "rollPos": {"id":-1, "indicator": self.rollPos},
            "rollNeg": {"id":-1, "indicator": self.rollNeg},
            "killswitch": {"id":-1, "indicator": self.killswitch},
            "alt1": {"id":-1, "indicator": self.alt1},
            "alt2": {"id":-1, "indicator": self.alt2},
            "exitapp": {"id":-1, "indicator": self.exitapp},
            "althold": {"id":-1, "indicator": self.althold},
            }

        self.axismapping = {
            "pitch": {"id":-1,
                      "indicator": self.pitchAxisValue,
                      "scale":-1.0},
            "roll": {"id":-1,
                     "indicator": self.rollAxisValue,
                     "scale":-1.0},
            "yaw": {"id":-1,
                    "indicator": self.yawAxisValue,
                    "scale":-1.0},
            "thrust": {"id":-1,
                       "indicator": self.thrustAxisValue,
                       "scale":-1.0}
            }

    def cancelConfigBox(self, button):
        self.axisDetect = ""
        self.btnDetect = ""

    def showConfigBox(self, caption, message, directions=[]):
        self._maxed_axis = []
        self._mined_axis = []
        self.box = QMessageBox()
        self.box.directions = directions
        self.combinedButton = QtGui.QPushButton('Combined Axis Detection')
        self.cancelButton = QtGui.QPushButton('Cancel')
        self.box.addButton(self.cancelButton, QMessageBox.DestructiveRole)
        self.box.setWindowTitle(caption)
        self.box.setWindowFlags(Qt.Dialog|Qt.MSWindowsFixedSizeDialogHint)
        if len(directions) > 1:
            self.box.originalMessage = message
            message = self.box.originalMessage % directions[0]
            self.combinedButton.setCheckable(True)
            self.combinedButton.blockSignals(True)
            self.box.addButton(self.combinedButton, QMessageBox.ActionRole)
        self.box.setText(message)
        self.box.show()

    def startConfigOfInputDevice(self):
        self.joystickReader.enableRawReading(str(self.inputDeviceSelector.currentText()))
        self.rawinputreader.startReading()
        self.populateDropDown()
        self.profileCombo.setEnabled(True)
        for b in self.detectButtons:
            b.setEnabled(True)

    def rawAxisUpdate(self, data):
        if (len(self.axisDetect) > 0):
            if self.combinedButton and self.combinedButton.isChecked() and self.combinedDetection == 0:
                self.combinedButton.setDisabled(True)
                self.combinedDetection = 1
            for a in data:
                # Axis must go low and high before it's accepted as selected
                # otherwise maxed out axis (like gyro/acc) in some controllers
                # will always be selected. Not enforcing negative values makes it
                # possible to detect split axis (like bumpers on PS3 controller)
                if a not in self._maxed_axis and abs(data[a]) > 0.8:
                    self._maxed_axis.append(a)
                if a not in self._mined_axis and abs(data[a]) < 0.1:
                    self._mined_axis.append(a)
                if a in self._maxed_axis and a in self._mined_axis and len(self.axisDetect) > 0:
                    if self.combinedDetection == 0:
                        if data[a] >= 0:
                            self._map_axis(self.axisDetect, a, 1.0)
                        else:
                            self._map_axis(self.axisDetect, a, -1.0)
                        self.axisDetect = ""
                        self.checkAndEnableSave()
                        if self.box != None:
                            self.cancelButton.click()
                    elif self.combinedDetection == 2: #finished detection
                        if self._prev_combined_id != a: # not the same axis again ...
                            self._map_axis(self.axisDetect, a, -1.0)
                            self.axisDetect = ""
                            self.checkAndEnableSave()
                            if (self.box != None):
                                self.cancelButton.click()
                            self.combinedDetection = 0
                    elif self.combinedDetection == 1:
                        self._map_axis(self.axisDetect, a, 1.0)
                        self._prev_combined_id = a
                        self.combinedDetection = 2
                        message = self.box.originalMessage % self.box.directions[1]
                        self.box.setText(message)

    def _update_mapped_values(self, values):
        for v in values:
            #logger.info("{} in {}".format(v, self.buttonmapping))
            if v in self.buttonmapping:
                if values[v]:
                    self.buttonmapping[v]["indicator"].setChecked(True)
                else:
                    self.buttonmapping[v]["indicator"].setChecked(False)
            if v in self.axismapping:
                # The sliders used are set to 0-100 and the values from the input
                # layer is -1 to 1. So scale the value and place 0 in the middle
                self.axismapping[v]["indicator"].setValue(values[v]*100)
                #if v == "roll":
                #    logger.info("{}".format(values[v]))

    def _map_axis(self, function, key_id, scale):
        self._map["Input.AXIS-{}".format(key_id)] = {}
        self._map["Input.AXIS-{}".format(key_id)]["id"] = key_id
        self._map["Input.AXIS-{}".format(key_id)]["key"] = function
        self._map["Input.AXIS-{}".format(key_id)]["scale"] = scale
        self._map["Input.AXIS-{}".format(key_id)]["offset"] = 0.0
        self._map["Input.AXIS-{}".format(key_id)]["type"] = "Input.AXIS"
        self.joystickReader.set_raw_input_map(self._map)

    def _map_button(self, function, key_id):
        self._map["Input.BUTTON-{}".format(key_id)] = {}
        self._map["Input.BUTTON-{}".format(key_id)]["id"] = key_id
        self._map["Input.BUTTON-{}".format(key_id)]["key"] = function
        self._map["Input.BUTTON-{}".format(key_id)]["scale"] = 1.0
        self._map["Input.BUTTON-{}".format(key_id)]["type"] = "Input.BUTTON"
        self.joystickReader.set_raw_input_map(self._map)

    def rawButtonUpdate(self, data):
        if len(self.btnDetect) > 0:
            for b in data:
                if data[b] > 0:
                    self._map_button(self.btnDetect, b)
                    self.btnDetect = ""
                    self.checkAndEnableSave()
                    if self.box != None:
                        self.box.close()

    def checkAndEnableSave(self):
        needed_funcs = ["thrust", "yaw", "roll", "pitch"]

        for m in self._map:
            if self._map[m]["key"] in needed_funcs:
                needed_funcs.remove(self._map[m]["key"])

        if len(needed_funcs) == 0:
            self.saveButton.setEnabled(True)

    def populateDropDown(self):
        configs = ConfigManager().get_list_of_configs()
        if len(configs):
            self.loadButton.setEnabled(True)
        for c in configs:
            self.profileCombo.addItem(c)
            logger.info("Found inputdevice [%s]", c)

    def doAxisDetect(self, varname, caption, message, directions=[]):
        self.axisDetect = varname
        self.showConfigBox(caption, message, directions)

    def doButtonDetect(self, varname, caption, message):
        self.btnDetect = varname
        self.showConfigBox(caption, message)

    def showError(self, caption, message):
        QMessageBox.critical(self, caption, message)

    #def parseButtonConfig(self, key, btnId, scale):
    #    newKey = ""
    #    if ("pitch" in key and scale > 0):
    #        newKey = "pitchPos"
    #    if ("pitch"in key and scale < 0):
    #        newKey = "pitchNeg"
    #    if ("roll" in key and scale > 0):
    #        newKey = "rollPos"
    #    if ("roll" in key and scale < 0):
    #        newKey = "rollNeg"
    #    if ("estop" in key):
    #        newKey = "killswitch"
    #    if ("alt1" in key):
    #        newKey = "alt1"
    #    if ("alt2" in key):
    #        newKey = "alt2"
    #    if ("exit" in key):
    #        newKey = "exitapp"
    #    if ("althold" in key):
    #        newKey = "althold"
    #    if (len(newKey) > 0):
    #        self.buttonmapping[newKey]['id'] = btnId
    #    else:
    #        logger.warning("Could not find new key for [%s]", key)

    #def parseAxisConfig(self, key, axisId, scale):
    #    if self.axismapping[key]['id'] != -1: #second axis
    #        if scale > 0:
    #            self.axismapping[key]['ids'] = [self.axismapping[key]['id'], axisId]
    #        else:
    #            self.axismapping[key]['ids'] = [axisId, self.axismapping[key]['id']]
    #        del self.axismapping[key]['id']
    #    else:
    #        self.axismapping[key]['id'] = axisId
    #    self.axismapping[key]['scale'] = scale

    def loadConfig(self):
        loaded_map = ConfigManager().get_config(self.profileCombo.currentText())
        if loaded_map:
            self.joystickReader.set_raw_input_map(loaded_map)
            self._map = loaded_map
        else:
            logger.warning("Could not load configfile [%s]",
                           self.profileCombo.currentText())
            self.showError("Could not load config",
                           "Could not load config [%s]" %
                           self.profileCombo.currentText())
        self.checkAndEnableSave()

        #self._reset_mapping()
        #if (conf != None):
        #    for c in conf:
        #        if (conf[c]['type'] == "Input.BUTTON"):
        #            self.parseButtonConfig(conf[c]['key'],
        #                                   conf[c]['id'], conf[c]['scale'])
        #        elif (conf[c]['type'] == "Input.AXIS"):
        #            self.parseAxisConfig(conf[c]['key'],
        #                                 conf[c]['id'], conf[c]['scale'])
        #else:
        #    logger.warning("Could not load configfile [%s]",
        #                   self.profileCombo.currentText())
        #    self.showError("Could not load config",
        #                   "Could not load config [%s]" %
        #                   self.profileCombo.currentText())
        #self.checkAndEnableSave()

    def deleteConfig(self):
        logger.warning("deleteConfig not implemented")

    def saveConfig(self):
        configName = str(self.profileCombo.currentText())

        # Build up the structure of the config file
        conf = {}

        mapping = {'inputconfig': {'inputdevice': {'axis': []}}}

        # Create intermediate structure for the configuration file
        funcs = {}
        for m in self._map:
            key = self._map[m]["key"]
            if not key in funcs:
                funcs[key] = []
            funcs[key].append(self._map[m])

        logger.info(funcs)

        # Create a mapping for each axis, take care to handle
        # split axis configurations
        for a in funcs:
            func = funcs[a]
            axis = {}
            # Check for split axis
            if len(func) > 1:
                axis["ids"] = [func[0]["id"], func[1]["id"]]
                axis["scale"] = func[1]["scale"]
            else:
                axis["id"] = func[0]["id"]
                axis["scale"] = func[0]["scale"]
            axis["key"] = func[0]["key"]
            axis["name"] = func[0]["key"] # Name isn't used...
            axis["type"] =func[0]["type"]
            mapping["inputconfig"]["inputdevice"]["axis"].append(axis)


        saveConfig = {}
        inputConfig = {'inputdevice': {'axis': []}}
        for a in self.axismapping:
            newC = {}
            if "id" in self.axismapping[a]:
                newC['id'] = self.axismapping[a]['id']
            elif "ids" in self.axismapping[a]:
                newC['ids'] = self.axismapping[a]['ids']
            else:
                raise Exception("Problem during save")
            newC['key'] = a
            newC['name'] = a

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

            if ("alt1" in a):
                newC['key'] = "alt1"
                newC['name'] = a

            if ("alt2" in a):
                newC['key'] = "alt2"
                newC['name'] = a

            if ("exit" in a):
                newC['key'] = "exit"
                newC['name'] = a
                
            if ("althold" in a):
                newC['key'] = "althold"
                newC['name'] = a               
                

            inputConfig['inputdevice']['axis'].append(newC)

        mapping["inputconfig"]['inputdevice']['name'] = configName
        mapping["inputconfig"]['inputdevice']['updateperiod'] = 10

        config_name = self.profileCombo.currentText()
        filename = ConfigManager().configs_dir + "/%s.json" % config_name
        logger.info("Saving config to [%s]", filename)
        json_data = open(filename, 'w')
        json_data.write(json.dumps(mapping, indent=2))
        json_data.close()

        ConfigManager().conf_needs_reload.call(config_name)
        self.close()

    def showEvent(self, event):
        self._saved_open_device = self.joystickReader.get_device_name()
        self.joystickReader.stop_input()

    def closeEvent(self, event):
        self.joystickReader.disableRawReading()
        self.rawinputreader.stopReading()
        self.joystickReader.start_input(self._saved_open_device)

class RawJoystickReader(QThread):

    rawAxisUpdateSignal = pyqtSignal(object)
    rawButtonUpdateSignal = pyqtSignal(object)
    mapped_values_signal = pyqtSignal(object)

    def __init__(self, joystickReader):
        QThread.__init__(self)

        self.joystickReader = joystickReader
        self.readTimer = QTimer()
        self.readTimer.setInterval(25)

        self.connect(self.readTimer, SIGNAL("timeout()"), self.read_input)

    def stopReading(self):
        self.readTimer.stop()

    def startReading(self):
        self.readTimer.start()

    @pyqtSlot()
    def read_input(self):
        [rawaxis, rawbuttons, mapped_values] = self.joystickReader.readRawValues()
        self.rawAxisUpdateSignal.emit(rawaxis)
        self.rawButtonUpdateSignal.emit(rawbuttons)
        self.mapped_values_signal.emit(mapped_values)
