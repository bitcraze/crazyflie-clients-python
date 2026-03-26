#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2021-2025 Bitcraze AB
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

from __future__ import annotations

import asyncio
import logging
import math

from cflib2 import Crazyflie
from cflib2.error import DisconnectedError

from cfclient.gui import create_task
from cfclient.utils.callbacks import Caller

__author__ = "Bitcraze AB"
__all__ = ["PoseLogger"]

logger = logging.getLogger(__name__)


class PoseLogger:
    LOG_NAME_ESTIMATE_X = "stateEstimate.x"
    LOG_NAME_ESTIMATE_Y = "stateEstimate.y"
    LOG_NAME_ESTIMATE_Z = "stateEstimate.z"
    LOG_NAME_ESTIMATE_ROLL = "stateEstimate.roll"
    LOG_NAME_ESTIMATE_PITCH = "stateEstimate.pitch"
    LOG_NAME_ESTIMATE_YAW = "stateEstimate.yaw"
    NO_POSE = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def __init__(self) -> None:
        self.data_received_cb = Caller()
        self.error_cb = Caller()

        # The pose is a tuple containing
        # X, Y, Z, roll, pitch, yaw
        # roll, pitch and yaw in degrees
        self.pose = self.NO_POSE
        self._stream_task = None

    @property
    def position(self) -> tuple[float, ...]:
        """Get the position part of the full pose"""
        return self.pose[0:3]

    @property
    def rpy(self) -> tuple[float, ...]:
        """Get the roll, pitch and yaw of the full pose in degrees"""
        return self.pose[3:6]

    @property
    def rpy_rad(self) -> list[float]:
        """Get the roll, pitch and yaw of the full pose in radians"""
        return [
            math.radians(self.pose[3]),
            math.radians(self.pose[4]),
            math.radians(self.pose[5]),
        ]

    def start(self, cf: Crazyflie) -> None:
        """Start streaming pose data from the Crazyflie."""
        self._stream_task = create_task(self._stream_loop(cf))

    def stop(self) -> None:
        """Stop streaming pose data."""
        if self._stream_task is not None:
            self._stream_task.cancel()
            self._stream_task = None
        self.pose = self.NO_POSE

    async def _stream_loop(self, cf: Crazyflie) -> None:
        log = cf.log()
        stream = None
        try:
            block = await log.create_block()
            await block.add_variable(self.LOG_NAME_ESTIMATE_X)
            await block.add_variable(self.LOG_NAME_ESTIMATE_Y)
            await block.add_variable(self.LOG_NAME_ESTIMATE_Z)
            await block.add_variable(self.LOG_NAME_ESTIMATE_ROLL)
            await block.add_variable(self.LOG_NAME_ESTIMATE_PITCH)
            await block.add_variable(self.LOG_NAME_ESTIMATE_YAW)

            stream = await block.start(40)  # 40ms period
            while True:
                data = await stream.next()
                self.pose = (
                    data.data[self.LOG_NAME_ESTIMATE_X],
                    data.data[self.LOG_NAME_ESTIMATE_Y],
                    data.data[self.LOG_NAME_ESTIMATE_Z],
                    data.data[self.LOG_NAME_ESTIMATE_ROLL],
                    data.data[self.LOG_NAME_ESTIMATE_PITCH],
                    data.data[self.LOG_NAME_ESTIMATE_YAW],
                )
                self.data_received_cb.call(self, self.pose)
        except DisconnectedError:
            pass
        finally:
            if stream is not None:
                try:
                    await asyncio.shield(stream.stop())
                except (DisconnectedError, asyncio.CancelledError):
                    pass
