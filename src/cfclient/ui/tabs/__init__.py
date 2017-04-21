#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2017 Bitcraze AB
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
#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
Find all the available tabs so they can be loaded.

Dropping a new .py file into this directory will automatically list and load
it into the UI when it is started.
"""
from .ConsoleTab import ConsoleTab
# from .ExampleTab import ExampleTab
from .FlightTab import FlightTab
# from .GpsTab import GpsTab
from .LEDTab import LEDTab
from .LogBlockTab import LogBlockTab
from .LogTab import LogTab
from .ParamTab import ParamTab
from .PlotTab import PlotTab
from .locopositioning_tab import LocoPositioningTab

__author__ = 'Bitcraze AB'
__all__ = []

available = [
    ConsoleTab,
    # ExampleTab,
    FlightTab,
    # GpsTab,
    LEDTab,
    LogBlockTab,
    LogTab,
    ParamTab,
    PlotTab,
    LocoPositioningTab,
]
