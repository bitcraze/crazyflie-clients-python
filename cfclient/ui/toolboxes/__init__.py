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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
List all the available toolboxes so they can be used by the UI.

Dropping a new .py file into this directory will automatically list and load
it into the UI when it is started.
"""

__author__ = 'Bitcraze AB'
__all__ = []

import os
import glob

foundToolboxes = [ os.path.basename(f)[:-3] for f in glob.glob(os.path.dirname(__file__)+"/[A-Za-z]*Toolbox.py")]

toolboxes = []

for tb in foundToolboxes:
    tbModule = __import__(tb, globals(), locals(), [tb], -1)
    toolboxes.append(getattr(tbModule, tb))

