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

"""Initialization of the PC Client GUI."""

import sys
import os
import argparse
import datetime

import logging

import cfclient

__author__ = 'Bitcraze AB'
__all__ = []


def main():
    """
    Check starting conditions and start GUI.

    First, check command line arguments and start loggers. Set log levels. Try
    all imports and exit verbosely if a library is not found. Disable outputs
    to stdout and start the GUI.
    """

    # Set ERROR level for PyQt5 logger
    qtlogger = logging.getLogger('PyQt5')
    qtlogger.setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(
        description="cfclient - Crazyflie graphical control client")
    parser.add_argument('--debug', '-d', nargs=1, default='info', type=str,
                        help="set debug level "
                             "[minimal, info, debug, debugfile]")
    args = parser.parse_args()
    debug = args.debug

    cflogger = logging.getLogger('')

    # Set correct logging fuctionality according to commandline
    if ("debugfile" in debug):
        logging.basicConfig(level=logging.DEBUG)
        # Add extra format options for file logger (thread and time)
        formatter = logging.Formatter('%(asctime)s:%(threadName)s:%(name)'
                                      's:%(levelname)s:%(message)s')
        filename = "debug-%s.log" % datetime.datetime.now()
        filehandler = logging.FileHandler(filename)
        filehandler.setLevel(logging.DEBUG)
        filehandler.setFormatter(formatter)
        cflogger.addHandler(filehandler)
    elif ("debug" in debug):
        logging.basicConfig(level=logging.DEBUG)
    elif ("minimal" in debug):
        logging.basicConfig(level=logging.WARNING)
    elif ("info" in debug):
        logging.basicConfig(level=logging.INFO)

    logger = logging.getLogger(__name__)

    logger.debug("Using config path {}".format(cfclient.config_path))
    logger.debug("sys.path={}".format(sys.path))

    # Try all the imports used in the project here to control what happens....
    try:
        import usb  # noqa
    except ImportError:
        logger.critical("No pyusb installation found, exiting!")
        sys.exit(1)

    if not sys.platform.startswith('linux'):
        try:
            import sdl2  # noqa
        except ImportError:
            logger.critical("No pysdl2 installation found, exiting!")
            sys.exit(1)

    try:
        import PyQt5  # noqa
    except ImportError:
        logger.critical("No PyQT5 installation found, exiting!")
        sys.exit(1)

    # Disable printouts from STL
    if os.name == 'posix':
        stdout = os.dup(1)
        os.dup2(os.open('/dev/null', os.O_WRONLY), 1)
        sys.stdout = os.fdopen(stdout, 'w')
        logger.info("Disabling STL printouts")

    if os.name == 'nt':
        stdout = os.dup(1)
        os.dup2(os.open('NUL', os.O_WRONLY), 1)
        sys.stdout = os.fdopen(stdout, 'w')
        logger.info("Disabling STL printouts")

    if sys.platform == 'darwin':
        try:
            import Foundation
            bundle = Foundation.NSBundle.mainBundle()
            if bundle:
                info = (bundle.localizedInfoDictionary() or
                        bundle.infoDictionary())
                if info:
                    info['CFBundleName'] = 'Crazyflie'
        except ImportError:
            logger.info("Foundation not found. Menu will show python as "
                        "application name")

    # Start up the main user-interface
    from .ui.main import MainUI
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QIcon

    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(cfclient.module_path + "/icon-256.png"))
    # Make sure the right icon is set in Windows 7+ taskbar
    if os.name == 'nt':
        import ctypes

        try:
            myappid = 'mycompany.myproduct.subproduct.version'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                myappid)
        except Exception:
            pass

    main_window = MainUI()
    main_window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
