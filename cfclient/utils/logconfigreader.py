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
The input module that will read joysticks/input devices and send control set-points to
the Crazyflie. It will also accept settings from the UI.

This module can use different drivers for reading the input device data. Currently it can
just use the PyGame driver but in the future there will be a Linux and Windows driver that can
bypass PyGame.
"""

__author__ = 'Bitcraze AB'
__all__ = ['LogVariable', 'LogConfigReader', 'LogConfig']

import sys
import json, glob, os
import logging

logger = logging.getLogger(__name__)

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import pyqtSlot, pyqtSignal
from pprint import pprint

from cflib.crazyflie.log import Log, LogTocElement

import traceback

class LogConfig():
    def __init__(self, configname, period = 0, filename = ""):
        self.period = period
        self.variables = []
        self.configName = configname
        self.configFileName = filename
        self.datarangeMin = 0
        self.datarangeMax = 0

    def addVariable(self, var):
        self.variables.append(var)

    def setPeriod(self, period):
        self.period = period

    def setDataRange(self, minVal, maxVal):
        self.datarangeMin = minVal
        self.datarangeMax = maxVal

    def getVariables(self):
        return self.variables

    def getName(self):
        return self.configName

    def getDataRangeMin(self):
        return self.datarangeMin

    def getDataRangeMax(self):
        return self.datarangeMax

    def getPeriod(self):
        return self.period

    def __str__(self):
        return "LogConfig: name=%s, period=%d, variables=%d" % (self.configName, self.period, len(self.variables))

class LogVariable():
    """A logging variable"""

    TOC_TYPE = 0
    MEM_TYPE = 1

    def __init__(self, name = "", fetchAs = "uint8_t", varType = 0, storedAs = "", address = 0):
        self.name = name
        self.fetchAs = LogTocElement.getIdFromCString(fetchAs)
        if (len(storedAs) == 0):
            self.storedAs = self.fetchAs
        else:
            self.storedAs = LogTocElement.getIdFromCString(storedAs)
        self.address = address
        self.varType = varType
        self.fetchAndStoreageString = fetchAs
        self.storedAsString = storedAs
        self.fetchAsString = fetchAs

    def setName(self, name):
        """Set the name"""
        self.name = name

    def setTypes(self, storeAs, fetchAs):
        """Set the type the variable is stored as in the Crazyflie and the type it should be fetched as."""
        self.fetchAs = fetchAs
        self.storeAs = storeAs

    def isTocVariable(self):
        """Return true if the variable should be in the TOC, false if raw memory variable"""
        return self.varType == LogVariable.TOC_TYPE

    def setAddress(self, addr):
        """Set the address in case of raw memory logging."""
        self.address = addr

    def getName(self):
        """Return the variable name"""
        return self.name

    def getStoredAs(self):
        """Return the type the variable is stored as in the Crazyflie"""
        return self.storedAs

    def getFetchAs(self):
        """Return the type the variable should be fetched as."""
        return self.fetchAs

    def getAddress(self):
        """Return the address in case of memory logging."""
        return self.address

    def getVarType(self):
        """Get the variable type"""
        return self.varType

    def getStoredFetchAs(self):
        """Return what the variable is stored as and fetched as"""
        return (self.fetchAs | (self.storedAs << 4))

    def setFetchAndStorageString(self, s):
        """Set the fetch and store string"""
        self.fetchAndStoreageString = s

    def getFetchAndStorageString(self):
        """Return the fetch and store string"""
        return self.fetchAndStoreageString

    def __str__(self):
        return "LogVariable: name=%s, store=%s, fetch=%s" % (self.name, LogTocElement.getCStringFromId(self.storedAs),
                                                             LogTocElement.getCStringFromId(self.fetchAs))

class LogConfigReader():
    """Reads logging configurations from file"""

    def __init__(self):
        self.dsList = []

    def readConfigFiles(self):
        """Read and parse log configurations"""
        configsfound = [ os.path.basename(f) for f in glob.glob("configs/log/[A-Za-z_-]*.json")]

        for conf in configsfound:            
            try:
                logger.info("Parsing [%s]", conf)
                json_data = open (os.getcwd()+"/configs/log/%s"%conf)                
                self.data = json.load(json_data)
                infoNode = self.data["logconfig"]["logblock"]

                logConf = LogConfig(infoNode["name"], int(infoNode["period"]), conf)
                logConf.setDataRange(int(infoNode["min"]), int(infoNode["max"]))
                for v in self.data["logconfig"]["logblock"]["variables"]:
                    if (v["type"]=="TOC"):
                        logConf.addVariable(LogVariable(str(v["name"]), v["fetch_as"], LogVariable.TOC_TYPE))
                    else:
                        logConf.addVariable(LogVariable("Mem", v["fetch_as"], LogVariable.MEM_TYPE, v["stored_as"],
                                                        int(v["address"],16)))
                self.dsList.append(logConf)
                json_data.close()
            except Exception as e:
                logger.warning("Exception while parsing logconfig file: %s", e)

    def getLogConfigs(self):
        """Return the log configurations"""
        return self.dsList

    def saveLogConfigFile(self, logconfig, filename):
        """Save a log configuration to file"""
        logger.info("Saving config for [%s] to file [%s]", logconfig.getName(), filename)
        
        # Build tree for JSON
        tree = {}
        saveConfig = {}
        logconf = {'logblock': {'variables':[]}}
        logconf['logblock']['name'] = logconfig.getName()
        logconf['logblock']['period'] = logconfig.getPeriod()
		# Temporary until plot is fixed
        logconf['logblock']['min'] = -180
        logconf['logblock']['max'] = 180

        for v in logconfig.getVariables():
            newC = {}
            newC['name'] = v.getName()
            newC['stored_as'] = v.getFetchAndStorageString()
            newC['fetch_as'] = v.getFetchAndStorageString()
            newC['type'] = "TOC"
            logconf['logblock']['variables'].append(newC)

        saveConfig['logconfig'] = logconf

        json_data=open(filename, 'w')
        json_data.write(json.dumps(saveConfig))
        json_data.close()

