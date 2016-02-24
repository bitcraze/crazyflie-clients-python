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

#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc., 51
#  Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import os
import pkg_resources


def _init_config_path():
    import sys
    import os
    import os.path as _path
    from os.path import expanduser

    prefix = expanduser("~")

    if sys.platform == "linux2":
        if _path.exists(_path.join(prefix, ".local")):
            configPath = _path.join(prefix, ".local", __name__)
        else:
            configPath = _path.join(prefix, "." + __name__)
    elif sys.platform == "win32":
        configPath = _path.join(os.environ['APPDATA'], __name__)
    elif sys.platform == "darwin":
        from AppKit import NSSearchPathForDirectoriesInDomains
        # FIXME: Copy-pasted from StackOverflow, not tested!
        # http://developer.apple.com/DOCUMENTATION/Cocoa/Reference/Foundation/Miscellaneous/Foundation_Functions/Reference/reference.html#//apple_ref/c/func/NSSearchPathForDirectoriesInDomains # noqa
        # NSApplicationSupportDirectory = 14
        # NSUserDomainMask = 1
        # True for expanding the tilde into a fully qualified path
        configPath = _path.join(
            NSSearchPathForDirectoriesInDomains(14, 1, True)[0], __name__)
    else:
        # Unknown OS, I hope this is good enough
        configPath = _path.join(prefix, "." + __name__)

    if not _path.exists(configPath):
        os.makedirs(configPath)

    return configPath

# Path used all over the application
# FIXME: module_path is missused: it should not be used to load ressources if
#        we want to be able to follow PEP302 and run from zip!
module_path = os.path.dirname(__file__)
config_path = _init_config_path()

try:
    VERSION = pkg_resources.require("cfclient")[0].version
except pkg_resources.DistributionNotFound:
    VERSION = "dev"
