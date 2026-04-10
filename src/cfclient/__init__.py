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

import json
import logging
import os
from appdirs import AppDirs
import sys
from threading import Timer

# Path used all over the application
if not hasattr(sys, 'frozen'):
    module_path = os.path.dirname(__file__)
else:
    module_path = os.path.join(os.path.dirname(sys.executable),
                               'lib', 'cfclient')
config_path = AppDirs("cfclient", "Bitcraze").user_config_dir

if not hasattr(sys, 'frozen'):
    from importlib.metadata import version, PackageNotFoundError
    try:
        VERSION = version("cfclient")
    except PackageNotFoundError:
        VERSION = "dev"
else:
    try:
        from .version import __version__ as imported_version
        VERSION = imported_version
    except ImportError:
        VERSION = "dev"
try:
    with open(os.path.join(module_path, "resources/log_param_doc.json")) as f:
        log_param_doc = json.load(f)
except (IOError, OSError, json.JSONDecodeError):
    log_param_doc = None

logger = logging.getLogger(__name__)


def _enable_legacy_platform_probe_fallback():
    try:
        from cflib.crazyflie.platformservice import PlatformService
    except ImportError:
        return

    if getattr(PlatformService, "_cfclient_legacy_probe_patch", False):
        return

    original_fetch_platform_informations = PlatformService.fetch_platform_informations

    def fetch_platform_informations(self, callback):
        self._cfclient_platform_info_complete = False

        timer = getattr(self, "_cfclient_platform_info_timer", None)
        if timer:
            timer.cancel()

        def complete():
            if self._cfclient_platform_info_complete:
                return

            self._cfclient_platform_info_complete = True
            timer = getattr(self, "_cfclient_platform_info_timer", None)
            if timer:
                timer.cancel()
                self._cfclient_platform_info_timer = None

            callback()

        def on_timeout():
            logger.info("Platform info fetch timed out, assuming legacy firmware")
            self._protocolVersion = -1
            complete()

        self._cfclient_platform_info_timer = Timer(1.0, on_timeout)
        self._cfclient_platform_info_timer.daemon = True
        self._cfclient_platform_info_timer.start()

        original_fetch_platform_informations(self, complete)

    PlatformService.fetch_platform_informations = fetch_platform_informations
    PlatformService._cfclient_legacy_probe_patch = True


_enable_legacy_platform_probe_fallback()
