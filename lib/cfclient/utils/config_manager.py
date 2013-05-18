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
#  Copyright (C) 2013 Allyn Bauer
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
Manager for loading/accesing input device mappings.
"""

__author__ = 'Bitcraze AB/Allyn Bauer'
__all__ = ['ConfigManager']

import sys
import json
import logging
import glob
import os
import copy

from .singleton import Singleton
from cflib.utils.callbacks import Caller

logger = logging.getLogger(__name__)

@Singleton
class ConfigManager():
    """ Singleton class for managing input processing """
    conf_needs_reload = Caller()
    configs_dir = sys.path[1] + "/input"

    def __init__(self):
        """Initialize and create empty config list"""
        self._list_of_configs = []

    def get_config(self, config_name):
        """Get the configuration for an input device."""
        try:
            idx = self._list_of_configs.index(config_name)
            return self._input_config[idx]
        except:
            return None

    def get_list_of_configs(self):
        """Reload the configurations from file"""
        try:
            configs = [os.path.basename(f) for f in glob.glob(self.configs_dir + "/[A-Za-z]*.json")]
            self._input_config = []
            self._list_of_configs = []
            for conf in configs:            
                logger.info("Parsing [%s]", conf)
                json_data = open(self.configs_dir + "/%s" % conf)                
                data = json.load(json_data)
                newInputDevice = {}
                for a in data["inputconfig"]["inputdevice"]["axis"]:
                    axis = {}
                    axis["scale"] = a["scale"]
                    axis["type"] = a["type"]
                    axis["key"] = a["key"]
                    axis["name"] = a["name"]
                    try:
                      ids = a["ids"]
                    except:
                      ids = [a["id"]]
                    for id in ids:
                      locaxis = copy.deepcopy(axis)
                      if "ids" in a:
                        if id == a["ids"][0]:
                          locaxis["scale"] = locaxis["scale"] * -1
                      locaxis["id"] = id
                      index = "%s-%d" % (a["type"], id) # 'type'-'id' defines unique index for axis    
                      newInputDevice[index] = locaxis
                self._input_config.append(newInputDevice)
                json_data.close()
                self._list_of_configs.append(conf[:-5])
        except Exception as e:
            logger.warning("Exception while parsing inputconfig file: %s ", e)
        return self._list_of_configs
