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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
The input module that will read joysticks/input devices and send control set-
points to the Crazyflie. It will also accept settings from the UI.

This module can use different drivers for reading the input device data.
Currently it can just use the PyGame driver but in the future there will be a
Linux and Windows driver that can bypass PyGame.
"""

__author__ = 'Bitcraze AB'
__all__ = ['LogVariable', 'LogConfigReader', 'LogConfigRemoveThis']

import glob
import json
import logging
import os
import shutil
import sys

logger = logging.getLogger(__name__)

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import pyqtSlot, pyqtSignal

from cflib.crazyflie.log import LogVariable, LogConfig


class LogConfigReader():
    """Reads logging configurations from file"""

    def __init__(self, crazyflie):
        self.dsList = []
        # Check if user config exists, otherwise copy files
        if (not os.path.exists(sys.path[1] + "/log")):
            logger.info("No user config found, copying dist files")
            os.makedirs(sys.path[1] + "/log")
            for f in glob.glob(sys.path[0] +
                               "/cfclient/configs/log/[A-Za-z]*.json"):
                shutil.copy2(f, sys.path[1] + "/log")
        self._cf = crazyflie
        self._cf.connected.add_callback(self._connected)

    def _read_config_files(self):
        """Read and parse log configurations"""
        configsfound = [os.path.basename(f) for f in
                        glob.glob(sys.path[1] + "/log/[A-Za-z_-]*.json")]
        new_dsList = []
        for conf in configsfound:
            try:
                logger.info("Parsing [%s]", conf)
                json_data = open(sys.path[1] + "/log/%s" % conf)
                self.data = json.load(json_data)
                infoNode = self.data["logconfig"]["logblock"]

                logConf = LogConfig(infoNode["name"],
                                    int(infoNode["period"]))
                for v in self.data["logconfig"]["logblock"]["variables"]:
                    if v["type"] == "TOC":
                        logConf.add_variable(str(v["name"]), v["fetch_as"])
                    else:
                        logConf.add_variable("Mem", v["fetch_as"],
                                             v["stored_as"],
                                             int(v["address"], 16))
                new_dsList.append(logConf)
                json_data.close()
            except Exception as e:
                logger.warning("Exception while parsing logconfig file: %s", e)
        self.dsList = new_dsList

    def _connected(self, link_uri):
        """Callback that is called once Crazyflie is connected"""

        self._read_config_files()
        # Just add all the configurations. Via callbacks other parts of the
        # application will pick up these configurations and use them
        for d in self.dsList:
            self._cf.log.add_config(d)
            if not d.valid:
                logger.warning("Could not add log configuration [%s]",
                               d.name)

    def getLogConfigs(self):
        """Return the log configurations"""
        return self.dsList

    def saveLogConfigFile(self, logconfig):
        """Save a log configuration to file"""
        filename = sys.path[1] + "/log/" + logconfig.name + ".json"
        logger.info("Saving config for [%s]", filename)

        # Build tree for JSON
        saveConfig = {}
        logconf = {'logblock': {'variables': []}}
        logconf['logblock']['name'] = logconfig.name
        logconf['logblock']['period'] = logconfig.period_in_ms
        # Temporary until plot is fixed

        for v in logconfig.variables:
            newC = {}
            newC['name'] = v.name
            newC['stored_as'] = v.stored_as_string
            newC['fetch_as'] = v.fetch_as_string
            newC['type'] = "TOC"
            logconf['logblock']['variables'].append(newC)

        saveConfig['logconfig'] = logconf

        json_data = open(filename, 'w')
        json_data.write(json.dumps(saveConfig, indent=2))
        json_data.close()
