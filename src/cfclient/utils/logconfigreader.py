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
Currently it can just use the PySdl2 driver but in the future there will be a
Linux and Windows driver that can bypass PySdl2.
"""

import glob
import json
import logging
import os
import re
import shutil

import cfclient
from cflib.crazyflie.log import LogVariable, LogConfig

from PyQt5 import QtGui

__author__ = 'Bitcraze AB'
__all__ = ['LogVariable', 'LogConfigReader']

logger = logging.getLogger(__name__)

DEFAULT_CONF_NAME = 'log_config'
DEFAULT_CATEGORY_NAME = 'category'


class LogConfigReader():
    """Reads logging configurations from file"""

    def __init__(self, crazyflie):

        self._log_configs = {}
        self.dsList = []
        # Check if user config exists, otherwise copy files
        if (not os.path.exists(cfclient.config_path + "/log")):
            logger.info("No user config found, copying dist files")
            os.makedirs(cfclient.config_path + "/log")
            for f in glob.glob(
                    cfclient.module_path + "/configs/log/[A-Za-z]*.json"):
                shutil.copy2(f, cfclient.config_path + "/log")
        self._cf = crazyflie
        self._cf.connected.add_callback(self._connected)

    def get_icons(self):
        client_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                      os.pardir))
        icon_path = os.path.join(client_path, 'ui', 'icons')
        save_icon = QtGui.QIcon(os.path.join(icon_path, 'create.png'))
        delete_icon = QtGui.QIcon(os.path.join(icon_path, 'delete.png'))
        return save_icon, delete_icon

    def create_empty_log_conf(self, category):
        """ Creates an empty log-configuration with a default name """
        log_path = self._get_log_path(category)
        conf_name = self._get_default_conf_name(log_path)
        file_path = os.path.join(log_path, conf_name) + '.json'

        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                f.write(json.dumps(
                    {
                        'logconfig': {
                            'logblock': {
                                'variables': [],
                                'name': conf_name,
                                'period': 100
                            }
                        }
                    }, indent=2))

        self._log_configs[category].append(LogConfig(conf_name, 100))
        return conf_name

    def create_category(self):
        """ Creates a new category (dir in filesystem), with a unique name """
        log_path = os.path.join(cfclient.config_path, 'log')
        category = self._get_default_category(log_path)
        dir_path = os.path.join(log_path, category)

        # This should never be false, but just to be safe.
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
            self._log_configs[category] = []

        return category

    def delete_category(self, category):
        """ Removes the directory on file-system and recursively removes
            all the logging configurations.
        """
        log_path = self._get_log_path(category)
        if os.path.exists(log_path):
            shutil.rmtree(log_path)
            self._log_configs.pop(category)

    def delete_config(self, conf_name, category):
        """ Deletes a configuration from file system. """
        log_path = self._get_log_path(category)
        conf_path = os.path.join(log_path, conf_name) + '.json'

        if not os.path.exists(conf_path):
            # Check if we can find the file with lowercase first letter.
            conf_path = os.path.join(log_path,
                                     conf_name[0].lower() + conf_name[1:]
                                     + '.json')
            if not os.path.exists(conf_path):
                # Cant' find the config-file
                logger.warning('Failed to find log-config %s' % conf_path)
                return

        os.remove(conf_path)
        for conf in self._log_configs[category]:
            if conf.name == conf_name:
                self._log_configs[category].remove(conf)

    def change_name_config(self, old_name, new_name, category):
        """ Changes name to the configuration and updates the
            file in the file system.
        """
        configs = self._log_configs[category]

        for conf in configs:
            if conf.name == old_name:
                conf.name = new_name

        log_path = self._get_log_path(category)
        old_path = os.path.join(log_path, old_name) + '.json'
        new_path = os.path.join(log_path, new_name) + '.json'

        # File should exist but just to be extra safe
        if os.path.exists(old_path):
            with open(old_path, 'r+') as f:
                data = json.load(f)
                data['logconfig']['logblock']['name'] = new_name
                f.seek(0)
                f.truncate()
                f.write(json.dumps(data, indent=2))

            os.rename(old_path, new_path)

    def change_name_category(self, old_name, new_name):
        """ Renames the directory on file system and the config dict """
        if old_name in self._log_configs:
            self._log_configs[new_name] = self._log_configs.pop(old_name)
            os.rename(self._get_log_path(old_name),
                      self._get_log_path(new_name))

    def _get_log_path(self, category):
        """ Helper method """
        category_dir = '' if category == 'Default' else '/' + category
        return os.path.join(cfclient.config_path,
                            'log' + category_dir)

    def _get_default_category(self, log_path):
        """ Creates a name for the category, ending with a unique number. """
        dirs = [dir_ for dir_ in os.listdir(log_path) if os.path.isdir(
            os.path.join(log_path, dir_)
        )]
        config_nbrs = re.findall(r'(?<=%s)\d*' % DEFAULT_CATEGORY_NAME,
                                 ' '.join(dirs))
        config_nbrs = list(filter(len, config_nbrs))

        if config_nbrs:
            return DEFAULT_CATEGORY_NAME + str(
                            max([int(nbr) for nbr in config_nbrs]) + 1)
        else:
            return DEFAULT_CATEGORY_NAME + '1'

    def _read_config_categories(self):
        """Read and parse log configurations"""

        self._log_configs = {'Default': []}
        log_path = os.path.join(cfclient.config_path, 'log')

        for cathegory in os.listdir(log_path):

            cathegory_path = os.path.join(log_path, cathegory)

            try:
                if (os.path.isdir(cathegory_path)):
                    # create a new cathegory
                    self._log_configs[cathegory] = []
                    for conf in os.listdir(cathegory_path):
                        if conf.endswith('.json'):
                            conf_path = os.path.join(cathegory_path, conf)
                            log_conf = self._get_conf(conf_path)

                        # add the log configuration to the cathegory
                        self._log_configs[cathegory].append(log_conf)

                else:
                    # if it's not a directory, the log config is placed
                    # in the 'Default' cathegory
                    if cathegory_path.endswith('.json'):
                        log_conf = self._get_conf(cathegory_path)
                        self._log_configs['Default'].append(log_conf)

            except Exception as e:
                logger.warning("Failed to open log config %s", e)

    def _get_default_conf_name(self, log_path):
        config_nbrs = re.findall(r'(?<=%s)\d*(?!=\.json)' % DEFAULT_CONF_NAME,
                                 ' '.join(os.listdir(log_path)))
        config_nbrs = list(filter(len, config_nbrs))

        if config_nbrs:
            return DEFAULT_CONF_NAME + str(
                        max([int(nbr) for nbr in config_nbrs]) + 1)
        else:
            return DEFAULT_CONF_NAME + '1'

    def _get_conf(self, conf_path):
        with open(conf_path) as f:
            data = json.load(f)
            infoNode = data["logconfig"]["logblock"]

            logConf = LogConfig(infoNode["name"],
                                int(infoNode["period"]))
            for v in data["logconfig"]["logblock"]["variables"]:
                if v["type"] == "TOC":
                    logConf.add_variable(str(v["name"]), v["fetch_as"])
                else:
                    logConf.add_variable("Mem", v["fetch_as"],
                                         v["stored_as"],
                                         int(v["address"], 16))
            return logConf

    def _get_configpaths_recursively(self):
        """ Reads all configuration files from the log path and
            returns a list of tuples with format:
            (category/conf-name, absolute path).
        """
        logpath = os.path.join(cfclient.config_path, 'log')
        filepaths = []

        for files in os.listdir(logpath):
            abspath = os.path.join(logpath, files)
            if os.path.isdir(abspath):
                for config in os.listdir(abspath):
                    if config.endswith('.json'):
                        filepaths.append(('/'.join([files, config]),
                                         os.path.join(abspath, config)))
            else:
                if files.endswith('.json'):
                    filepaths.append((files, os.path.join(abspath)))

        return filepaths

    def _read_config_files(self):
        """Read and parse log configurations"""

        configsfound = self._get_configpaths_recursively()

        new_dsList = []
        for conf in configsfound:
            try:
                logger.info("Parsing [%s]", conf[0])
                json_data = open(conf[1])
                self.data = json.load(json_data)
                infoNode = self.data["logconfig"]["logblock"]
                logConfName = conf[0].replace('.json', '')

                logConf = LogConfig(logConfName, int(infoNode["period"]))
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
        self._read_config_categories()
        # Just add all the configurations. Via callbacks other parts of the
        # application will pick up these configurations and use them
        for d in self.dsList:
            try:
                self._cf.log.add_config(d)
            except KeyError as e:
                logger.warning(str(e))
            except AttributeError as e:
                logger.warning(str(e))

    def getLogConfigs(self):
        """Return the log configurations"""
        return self.dsList

    def _getLogConfigs(self):
        """Return the log configurations"""
        return self._log_configs

    def saveLogConfigFile(self, category, logconfig):
        """Save a log configuration to file"""
        log_path = self._get_log_path(category)
        file_path = os.path.join(log_path, logconfig.name) + '.json'
        logger.info("Saving config for [%s]", file_path)

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

        for old_conf in self._log_configs[category]:
            if old_conf.name == logconfig.name:
                self._log_configs[category].remove(old_conf)
                self._log_configs[category].append(logconfig)

        with open(file_path, 'w') as f:
            f.write(json.dumps(saveConfig, indent=2))

        self._read_config_files()
