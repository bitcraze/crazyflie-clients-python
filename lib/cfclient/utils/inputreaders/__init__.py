#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2014 Bitcraze AB
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Find all the available input readers and try to import them.

To create a new input device reader drop a .py file into this
directory and it will be picked up automatically.
"""

__author__ = 'Bitcraze AB'
__all__ = []

import os
import glob
import logging

logger = logging.getLogger(__name__)

found_readers = [os.path.splitext(os.path.basename(f))[0] for
             f in glob.glob(os.path.dirname(__file__) + "/[A-Za-z]*.py")]
if len(found_readers) == 0:
    found_readers = [os.path.splitext(os.path.basename(f))[0] for
                 f in glob.glob(os.path.dirname(__file__) +
                                "/[A-Za-z]*.pyc")]

logger.info("Found readers: {}".format(found_readers))

readers = []

for reader in found_readers:
    try:
        module = __import__(reader, globals(), locals(), [reader], -1)
        main_name = getattr(module, "MODULE_MAIN")
        readers.append(getattr(module, main_name))
        logger.info("Successfully initialized [{}]".format(reader))
    except Exception as e:
        logger.info("Could not initialize [{}]: {}".format(reader, e))
        #import traceback
        #logger.info(traceback.format_exc())