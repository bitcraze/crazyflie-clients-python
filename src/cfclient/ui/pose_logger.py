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
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.
"""
Sets up logging for the the full pose of the Crazyflie
"""
import logging
import math

from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.utils.callbacks import Caller

__author__ = 'Bitcraze AB'
__all__ = ['PoseLogger']

logger = logging.getLogger(__name__)


class PoseLogger:
    LOG_NAME_ESTIMATE_X = 'stateEstimate.x'
    LOG_NAME_ESTIMATE_Y = 'stateEstimate.y'
    LOG_NAME_ESTIMATE_Z = 'stateEstimate.z'
    LOG_NAME_ESTIMATE_ROLL = 'stateEstimate.roll'
    LOG_NAME_ESTIMATE_PITCH = 'stateEstimate.pitch'
    LOG_NAME_ESTIMATE_YAW = 'stateEstimate.yaw'
    NO_POSE = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def __init__(self, cf: Crazyflie) -> None:
        self._cf = cf
        self._cf.connected.add_callback(self._connected)
        self._cf.disconnected.add_callback(self._disconnected)

        self.data_received_cb = Caller()
        self.error_cb = Caller()

        # The pose is an array containing
        # X, Y, Z, roll, pitch, yaw
        # roll, pitch and yaw in degrees
        self.pose = self.NO_POSE

    @property
    def position(self):
        """Get the position part of the full pose"""
        return self.pose[0:3]

    @property
    def rpy(self):
        """Get the roll, pitch and yaw of the full pose in degrees"""
        return self.pose[3:6]

    @property
    def rpy_rad(self):
        """Get the roll, pitch and yaw of the full pose in radians"""
        return [math.radians(self.pose[3]), math.radians(self.pose[4]), math.radians(self.pose[5])]

    def _connected(self, link_uri) -> None:
        logConf = LogConfig("Pose", 40)
        logConf.add_variable(self.LOG_NAME_ESTIMATE_X, "float")
        logConf.add_variable(self.LOG_NAME_ESTIMATE_Y, "float")
        logConf.add_variable(self.LOG_NAME_ESTIMATE_Z, "float")
        logConf.add_variable(self.LOG_NAME_ESTIMATE_ROLL, "float")
        logConf.add_variable(self.LOG_NAME_ESTIMATE_PITCH, "float")
        logConf.add_variable(self.LOG_NAME_ESTIMATE_YAW, "float")

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
        self.pose = self.NO_POSE

    def _data_received(self, timestamp, data, logconf) -> None:
        self.pose = (
            data[self.LOG_NAME_ESTIMATE_X],
            data[self.LOG_NAME_ESTIMATE_Y],
            data[self.LOG_NAME_ESTIMATE_Z],
            data[self.LOG_NAME_ESTIMATE_ROLL],
            data[self.LOG_NAME_ESTIMATE_PITCH],
            data[self.LOG_NAME_ESTIMATE_YAW],
        )

        self.data_received_cb.call(self, self.pose)

    def _error(self, log_conf, msg) -> None:
        self.error_cb.call(self, msg)
