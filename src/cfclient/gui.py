# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2023 Bitcraze AB
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

"""Initialization of the PC Client GUI."""

import platform
import sys
import os
import dataclasses
import datetime
from typing import Literal

import asyncio
import logging

from cflib2 import DisconnectedError
import PySide6.QtAsyncio as QtAsyncio


import tyro

import cfclient

__author__ = "Bitcraze AB"
__all__ = []

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Args:
    """cfclient - Crazyflie graphical control client"""

    debug: Literal["minimal", "info", "debug", "debugfile"] = "info"
    """set debug level"""

    check_imports: bool = False
    """Check python imports and exit successfully (intended for CI)"""


def _task_done_callback(task):
    if task.cancelled():
        return
    try:
        task.result()
    except DisconnectedError:
        logger.debug("Task interrupted by disconnect: %s", task)
    except Exception:
        import traceback

        traceback.print_exc()
        os._exit(1)


def create_task(coro):
    """Schedule a coroutine as a task with automatic exception logging.

    Use this instead of asyncio.ensure_future() to ensure exceptions
    are logged immediately rather than silently swallowed.
    """
    logger.debug(f"create_task: {coro}")
    task = asyncio.ensure_future(coro)
    task.add_done_callback(_task_done_callback)
    return task


def main():
    """
    Check starting conditions and start GUI.

    First, check command line arguments and start loggers. Set log levels. Try
    all imports and exit verbosely if a library is not found. Disable outputs
    to stdout and start the GUI.
    """

    # Allows frozen mac build to load libraries from app bundle
    if getattr(sys, "frozen", False) and platform.system() == "Darwin":
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = os.path.dirname(sys.executable)

    # Set ERROR level for PySide6 logger
    qtlogger = logging.getLogger("PySide6")
    qtlogger.setLevel(logging.ERROR)

    args = tyro.cli(Args)
    debug = args.debug

    cflogger = logging.getLogger("")

    # Set correct logging fuctionality according to commandline
    if "debugfile" in debug:
        logging.basicConfig(level=logging.DEBUG)
        # Add extra format options for file logger (thread and time)
        formatter = logging.Formatter(
            "%(asctime)s:%(threadName)s:%(name)s:%(levelname)s:%(message)s"
        )
        filename = "debug-%s.log" % datetime.datetime.now()
        filehandler = logging.FileHandler(filename)
        filehandler.setLevel(logging.DEBUG)
        filehandler.setFormatter(formatter)
        cflogger.addHandler(filehandler)
    elif "debug" in debug:
        logging.basicConfig(level=logging.DEBUG)
    elif "minimal" in debug:
        logging.basicConfig(level=logging.WARNING)
    elif "info" in debug:
        logging.basicConfig(level=logging.INFO)

    logger.debug("Using config path {}".format(cfclient.config_path))
    logger.debug("sys.path={}".format(sys.path))

    if not sys.platform.startswith("linux"):
        try:
            import sdl2  # noqa
        except ImportError:
            logger.critical("No pysdl2 installation found, exiting!")
            sys.exit(1)

    try:
        import PySide6  # noqa
    except ImportError:
        logger.critical("No PySide6 installation found, exiting!")
        sys.exit(1)

    # Disable printouts from STL
    if os.name == "posix":
        stdout = os.dup(1)
        os.dup2(os.open("/dev/null", os.O_WRONLY), 1)
        sys.stdout = os.fdopen(stdout, "w")
        logger.info("Disabling STL printouts")

    if os.name == "nt":
        stdout = os.dup(1)
        os.dup2(os.open("NUL", os.O_WRONLY), 1)
        sys.stdout = os.fdopen(stdout, "w")
        logger.info("Disabling STL printouts")

    if sys.platform == "darwin":
        try:
            import Foundation

            bundle = Foundation.NSBundle.mainBundle()
            if bundle:
                info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
                if info:
                    info["CFBundleName"] = "Crazyflie"
        except ImportError:
            logger.info(
                "Foundation not found. Menu will show python as application name"
            )

    if args.check_imports:
        logger.info("All imports successful!")
        sys.exit(0)

    # Start up the main user-interface
    from .ui.main import MainUI
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon

    if os.name == "posix":
        logger.info(
            'If startup fails because of "xcb", install dependency with `sudo apt install libxcb-xinerama0`.'
        )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from cfclient.utils.ui import UiUtils

    app.setWindowIcon(QIcon(cfclient.module_path + "/ui/icons/icon-256.png"))
    app.setApplicationName("Crazyflie client")
    # Make sure the right icon is set in Windows 7+ taskbar
    if os.name == "nt":
        import ctypes

        try:
            myappid = "mycompany.myproduct.subproduct.version"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    main_window = MainUI()
    app.setFont(UiUtils.FONT)
    main_window.show()
    main_window.set_default_theme()

    # Use os._exit() to avoid PySide6 aborting when Python's GC
    # destroys QThread objects (e.g. from vispy) in the wrong order.
    # Hardcode 0: QtAsyncio.run() returns None when keep_running=True (the default).
    QtAsyncio.run(handle_sigint=True)
    os._exit(0)


if __name__ == "__main__":
    main()
