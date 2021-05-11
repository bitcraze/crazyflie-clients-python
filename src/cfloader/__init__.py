#!/usr/bin/env python3
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

# Crazy Loader bootloader utility
# Can reset bootload and reset back the bootloader

import sys

import cflib.crtp
from cflib.bootloader import Bootloader, Target
from cflib.bootloader.boottypes import BootVersion

from typing import Optional, List


def main():
    # Initialise the CRTP link driver
    try:
        cflib.crtp.init_drivers()
    except Exception as e:
        print("Error: {}".format(str(e)))
        sys.exit(-1)

    # Set the default parameters
    clink = None
    action = "info"
    boot = "cold"
    filename = None  # type: Optional[str]
    targets = None  # type: Optional[List[Target]]
    bl = None  # type: Optional[Bootloader]

    if len(sys.argv) < 2:
        print()
        print("==============================")
        print(" CrazyLoader Flash Utility")
        print("==============================")
        print()
        print(" Usage:", sys.argv[0], "[CRTP options] <action> [parameters]")
        print()
        print("The CRTP options are described above")
        print()
        print("Crazyload option:")
        print("   info                    : Print the info of the bootloader "
              "and quit.")
        print("                             Will let the target in bootloader "
              "mode")
        print("   reset                   : Reset the device in firmware mode")
        print("   flash <file> [targets]  : flash the <img> binary file from "
              "the first")
        print("                             possible  page in flash and reset "
              "to firmware")
        print("                             mode.")
        sys.exit(0)

    # Analyse the command line parameters
    sys.argv = sys.argv[1:]
    argv = []

    i = 0
    while i < len(sys.argv):
        if sys.argv[i] == "--cold-boot" or sys.argv[i] == "-c":
            boot = "cold"
        elif sys.argv[i] == "--warm-boot" or sys.argv[i] == "-w":
            boot = "reset"
            i += 1
            clink = sys.argv[i]
        else:
            argv += [sys.argv[i]]
        i += 1
    sys.argv = argv

    # Analyse the command
    if len(sys.argv) < 1:
        action = "info"
    elif sys.argv[0] == "info":
        action = "info"
    elif sys.argv[0] == "reset":
        action = "reset"
    elif sys.argv[0] == "flash":
        if len(sys.argv) < 2:
            print("The flash action require a file name.")
            sys.exit(-1)
        action = "flash"
        filename = sys.argv[1]
        targets = []  # Dict[Target]
        for t in sys.argv[2:]:
            if t.startswith("deck-"):
                [deck, target, type] = t.split("-")
                targets.append(Target("deck", target, type))
            else:
                [target, type] = t.split("-")
                targets.append(Target("cf2", target, type))
    else:
        print("Action", sys.argv[0], "unknown!")
        sys.exit(-1)

    try:
        # Initialise the bootloader lib
        bl = Bootloader(clink)

        warm_boot = (boot == "reset")
        if warm_boot:
            print("Reset to bootloader mode ...")
            sys.stdout.flush()
        else:  # The connection is done by a cold boot ...
            print("Restart the Crazyflie you want to bootload in the next"),
            print(" 10 seconds ..."),

            sys.stdout.flush()

        ######################################
        # Doing something (hopefully) useful
        ######################################

        if action == "info":
            def print_info(version: int, connected_targets: [Target]):
                print("Connected to bootloader on {} (version=0x{:X})".format(
                    BootVersion.to_ver_string(version),
                    version
                    )
                )
                for target in connected_targets:
                    print(target)

            # flash_full called with no filename will not flash, just call
            # our info callback
            bl.flash_full(None, None, warm_boot, None, print_info)
        elif action == "flash" and filename and targets:
            try:
                bl.flash_full(None, filename, warm_boot, targets)
            except Exception as e:
                print("Failed to flash: {}".format(e))
        elif action == "reset":
            bl.reset_to_firmware()
        else:
            None
    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stdout)
        print(e)

    finally:
        #########################
        # Closing the connection
        #########################
        if bl:
            bl.close()
