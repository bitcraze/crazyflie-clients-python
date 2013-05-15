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
Gives access for reading and writing application configuration parameters
"""

__author__ = 'Bitcraze AB'
__all__ = ['Config']

import sys
import json
import logging
from .singleton import Singleton

from PyQt4.QtCore import QString

logger = logging.getLogger(__name__)

@Singleton
class Config():
    """ Singleton class for accessing application configuration """
    def __init__(self):
        """ Initializes the singleton and reads the config files """
        self._dist_config = sys.path[0] + "/cfclient/configs/config.json"
        self._config = sys.path[1] + "/config.json"

        [self._readonly, self._data] = self._read_distfile()

        user_config = self._read_config()
        if (user_config):
            self._data.update(user_config)

    def _read_distfile(self):
        """ Read the distribution config file containing the defaults """
        f = open(self._dist_config, 'r')
        data = json.load(f)
        f.close()
        logger.info("Dist config read from %s" % self._dist_config)

        return [data["read-only"], data["writable"]]

    def set(self, key, value):
        """ Set the value of a config parameter """
        try:
            if (isinstance(value, QString)):
                self._data[key] = str(value)
            else:
                 self._data[key] = value
        except KeyError:
            raise KeyError("Could not set the parameter [%s]" % key)

    def get(self, key):
        """ Get the value of a config parameter """
        value = None
        if (key in self._data):
            value = self._data[key]
        elif (key in self._readonly):
            value = self._readonly[key]
        else:
            raise KeyError("Could not get the paramter [%s]" % key)
        
        if (isinstance(value, unicode)):
            value = str(value)

        return value

    def save_file(self):
        """ Save the user config to file """
        json_data=open(self._config, 'w')
        json_data.write(json.dumps(self._data, indent=2))
        json_data.close()
        logger.info("Config file saved to [%s]" % self._config)

    def _read_config(self):
        """ Read the user config from file """
        try:
            json_data = open(self._config)
            data = json.load(json_data)
            json_data.close()
            logger.info("Config file read from [%s]" % self._config)
        except Exception:
            return None
        
        return data
