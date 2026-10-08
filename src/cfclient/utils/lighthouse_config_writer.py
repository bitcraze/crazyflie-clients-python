# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2026 Bitcraze AB
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
Writes lighthouse system configurations (geometry, calibration and system type)
to the Crazyflie and persists them to permanent storage.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TypeVar

from cflib2 import Crazyflie
from cflib2.memory import LighthouseBsCalibration, LighthouseBsGeometry

__author__ = "Bitcraze AB"
__all__ = ["LighthouseWriteResult", "write_and_store_config"]

logger = logging.getLogger(__name__)

# Number of base station slots the protocol supports. The firmware may support
# fewer. Slots it does not support are rejected when written.
NR_OF_BASE_STATIONS = 16

# Changing the system type may trigger a lengthy operation in the Crazyflie (up
# to 0.5 s) if the persistent memory needs to be defragmented. Setting a
# parameter does not tell when it is done, so wait a while before continuing.
SYSTEM_TYPE_CHANGE_TIME = 0.8

T = TypeVar("T")


@dataclass
class LighthouseWriteResult:
    """The outcome of writing a lighthouse configuration to the Crazyflie"""

    persisted: bool = True
    """True if the written data was persisted to permanent storage"""

    rejected_geometries: list[int] = field(default_factory=list)
    """Base stations with geometry data that the Crazyflie does not support"""

    rejected_calibrations: list[int] = field(default_factory=list)
    """Base stations with calibration data that the Crazyflie does not support"""


async def write_and_store_config(
    cf: Crazyflie,
    geometries: dict[int, LighthouseBsGeometry] | None = None,
    calibrations: dict[int, LighthouseBsCalibration] | None = None,
    system_type: int | None = None,
) -> LighthouseWriteResult:
    """
    Write geometry and calibration data to the Crazyflie and persist it to permanent storage.

    If geometries or calibrations is None, no data is written for that data type. Otherwise the
    data for the base stations in the dict is written, and the data for all other base stations
    is invalidated.

    Data for base stations the Crazyflie does not support is skipped and listed in the result.
    """
    if system_type is not None:
        # Change the system type first, as this erases the geometry and calibration data in the Crazyflie
        await cf.param().set("lighthouse.systemType", system_type)
        await asyncio.sleep(SYSTEM_TYPE_CHANGE_TIME)

    result = LighthouseWriteResult()
    memory = cf.memory()

    geos_to_persist: list[int] = []
    if geometries is not None:
        report = await memory.write_lighthouse_geometries(
            _pad(geometries, LighthouseBsGeometry)
        )
        geos_to_persist = report.written
        result.rejected_geometries = [
            bs_id for bs_id in report.rejected if bs_id in geometries
        ]

    calibs_to_persist: list[int] = []
    if calibrations is not None:
        report = await memory.write_lighthouse_calibrations(
            _pad(calibrations, LighthouseBsCalibration)
        )
        calibs_to_persist = report.written
        result.rejected_calibrations = [
            bs_id for bs_id in report.rejected if bs_id in calibrations
        ]

    if geos_to_persist or calibs_to_persist:
        lighthouse = cf.localization().lighthouse()
        result.persisted = await lighthouse.persist_lighthouse_data(
            geos_to_persist, calibs_to_persist
        )

    if result.rejected_geometries or result.rejected_calibrations:
        logger.warning(
            "The Crazyflie does not support base stations: geometry %s, calibration %s",
            result.rejected_geometries,
            result.rejected_calibrations,
        )

    return result


def _pad(data: dict[int, T], empty: type[T]) -> dict[int, T]:
    """Add empty (invalid) entries for all base stations that are not in the dict"""
    result = dict(data)
    for bs_id in range(NR_OF_BASE_STATIONS):
        if bs_id not in result:
            result[bs_id] = empty()
    return result
