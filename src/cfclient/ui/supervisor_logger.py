#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2021 Bitcraze AB
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
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>
"""
Sets up logging supervisor data from the Crazyflie
"""
import logging

from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.utils.callbacks import Caller

__author__ = 'Bitcraze AB'
__all__ = ['SupervisorLogger']

logger = logging.getLogger(__name__)


class SupervisorLogger:
    LOG_NAME_CAN_FLY = 'sys.canfly'
    LOG_NAME_IS_FLYING = 'sys.isFlying'
    LOG_NAME_IS_TUMBLED = 'sys.isTumbled'

    def __init__(self, cf: Crazyflie) -> None:
        self._cf = cf
        self._cf.connected.add_callback(self._connected)
        self._cf.disconnected.add_callback(self._disconnected)

        self.data_received_cb = Caller()
        self.error_cb = Caller()

        self._can_fly = False
        self._is_flying = False
        self._is_tumbled = False

    @property
    def can_fly(self):
        """True if the Crazyflie reports that it can take off"""
        return self._can_fly

    @property
    def is_flying(self):
        """True if the Crazyflie reports that is is flying"""
        return self._is_flying

    @property
    def is_tumbled(self):
        """True if the Crazyflie reports that is is tumbled (up-side-down)"""
        return self._is_tumbled

    def _connected(self, link_uri) -> None:
        logConf = LogConfig("Supervisor", 100)
        logConf.add_variable(self.LOG_NAME_CAN_FLY)
        logConf.add_variable(self.LOG_NAME_IS_FLYING)
        logConf.add_variable(self.LOG_NAME_IS_TUMBLED)

        try:
            self._cf.log.add_config(logConf)
            logConf.data_received_cb.add_callback(self._data_received)
            logConf.error_cb.add_callback(self._error)
            logConf.start()
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))

    def _disconnected(self, link_uri) -> None:
        self._can_fly = False
        self._is_flying = False
        self._is_tumbled = False

    def _data_received(self, timestamp, data, logconf) -> None:
        self._can_fly = data[self.LOG_NAME_CAN_FLY] == 1
        self._is_flying = data[self.LOG_NAME_IS_FLYING] == 1
        self._is_tumbled = data[self.LOG_NAME_IS_TUMBLED] == 1

        self.data_received_cb.call(self)

    def _error(self, log_conf, msg) -> None:
        self.error_cb.call(self, msg)
