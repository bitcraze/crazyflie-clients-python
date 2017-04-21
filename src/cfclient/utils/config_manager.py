#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013-2017 Bitcraze AB
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

import json
import logging
import glob
import os
import copy

from .singleton import Singleton
from cflib.utils.callbacks import Caller

import cfclient

__author__ = 'Bitcraze AB/Allyn Bauer'
__all__ = ['ConfigManager']

logger = logging.getLogger(__name__)


class ConfigManager(metaclass=Singleton):
    """ Singleton class for managing input processing """
    conf_needs_reload = Caller()
    configs_dir = cfclient.config_path + "/input"

    def __init__(self):
        """Initialize and create empty config list"""
        self._list_of_configs = []

    def get_config(self, config_name):
        """Get the button and axis mappings for an input device."""
        try:
            idx = self._list_of_configs.index(config_name)
            return self._input_config[idx]
        except:
            return None

    def get_settings(self, config_name):
        """Get the settings for an input device."""
        try:
            idx = self._list_of_configs.index(config_name)
            return self._input_settings[idx]
        except:
            return None

    def get_list_of_configs(self):
        """Reload the configurations from file"""
        try:
            configs = [os.path.basename(f) for f in
                       glob.glob(self.configs_dir + "/[A-Za-z]*.json")]
            self._input_config = []
            self._input_settings = []
            self._list_of_configs = []
            for conf in configs:
                logger.debug("Parsing [%s]", conf)
                json_data = open(self.configs_dir + "/%s" % conf)
                data = json.load(json_data)
                new_input_device = {}
                new_input_settings = {"updateperiod": 10,
                                      "springythrottle": True}
                for s in data["inputconfig"]["inputdevice"]:
                    if s == "axis":
                        for a in data["inputconfig"]["inputdevice"]["axis"]:
                            axis = {}
                            axis["scale"] = a["scale"]
                            axis["offset"] = a[
                                "offset"] if "offset" in a else 0.0
                            axis["type"] = a["type"]
                            axis["key"] = a["key"]
                            axis["name"] = a["name"]

                            self._translate_for_backwards_compatibility(axis)

                            try:
                                ids = a["ids"]
                            except:
                                ids = [a["id"]]
                            for id in ids:
                                locaxis = copy.deepcopy(axis)
                                if "ids" in a:
                                    if id == a["ids"][0]:
                                        locaxis["scale"] = locaxis[
                                            "scale"] * -1
                                locaxis["id"] = id
                                # 'type'-'id' defines unique index for axis
                                index = "%s-%d" % (a["type"], id)
                                new_input_device[index] = locaxis
                    else:
                        new_input_settings[s] = data[
                            "inputconfig"]["inputdevice"][s]
                self._input_config.append(new_input_device)
                self._input_settings.append(new_input_settings)
                json_data.close()
                self._list_of_configs.append(conf[:-5])
        except Exception as e:
            logger.warning("Exception while parsing inputconfig file: %s ", e)
        return self._list_of_configs

    def save_config(self, input_map, config_name):
        """Save a configuration to file"""
        mapping = {'inputconfig': {'inputdevice': {'axis': []}}}

        # Create intermediate structure for the configuration file
        funcs = {}
        for m in input_map:
            key = input_map[m]["key"]
            if key not in funcs:
                funcs[key] = []
            funcs[key].append(input_map[m])

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
            axis["name"] = func[0]["key"]  # Name isn't used...
            axis["type"] = func[0]["type"]
            mapping["inputconfig"]["inputdevice"]["axis"].append(axis)

        mapping["inputconfig"]['inputdevice']['name'] = config_name
        mapping["inputconfig"]['inputdevice']['updateperiod'] = 10

        filename = ConfigManager().configs_dir + "/%s.json" % config_name
        logger.info("Saving config to [%s]", filename)
        json_data = open(filename, 'w')
        json_data.write(json.dumps(mapping, indent=2))
        json_data.close()

        self.conf_needs_reload.call(config_name)

    def _translate_for_backwards_compatibility(self, axis):
        """Handle changes in the config file format"""

        # The parameter that used to be called 'althold' has been renamed to
        # 'assistedControl'
        althold = 'althold'
        assistedControl = 'assistedControl'

        if axis['key'] == althold:
            axis['key'] = assistedControl

        if axis['name'] == althold:
            axis['name'] = assistedControl
