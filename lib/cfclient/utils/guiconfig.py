#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __                           
#  +------+      / __ )(_) /_______________ _____  ___ 
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013 Bitcraze AB
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
__all__ = ['GuiConfig']

import logging
from cfclient.utils.config import Config
from PyQt4.QtCore import QString

logger = logging.getLogger(__name__)

class GuiConfig(Config):
    """ Singleton class for accessing application configuration """

    def set(self, key, value):
        """ Set the value of a config parameter """
        strval = value
        if (isinstance(value, QString)):
            strval = str(value)
        Config.set(self, key, strval)

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

    def dump(self):
        print self._data
