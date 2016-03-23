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
from cflib.bootloader import Bootloader
from cflib.bootloader.boottypes import BootVersion, TargetTypes


def main():
    # Initialise the CRTP link driver
    link = None
    try:
        cflib.crtp.init_drivers()
        link = cflib.crtp.get_link_driver("radio://")
    except Exception as e:
        print("Error: {}".format(str(e)))
        if link:
            link.close()
        sys.exit(-1)

    # Set the default parameters
    clink = None
    action = "info"
    boot = "cold"

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
        if link:
            link.close()
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
        # print len(sys.argv)
        if len(sys.argv) < 2:
            print("The flash action require a file name.")
            link.close()
            sys.exit(-1)
        action = "flash"
        filename = sys.argv[1]
        targetnames = {}
        for t in sys.argv[2:]:
            [target, type] = t.split("-")
            if target in targetnames:
                targetnames[target] += (type,)
            else:
                targetnames[target] = (type,)
    else:
        print("Action", sys.argv[0], "unknown!")
        link.close()
        sys.exit(-1)

    # Currently there's two different targets available
    targets = ()

    try:
        # Initialise the bootloader lib
        bl = Bootloader(clink)

        #########################################
        # Get the connection with the bootloader
        #########################################
        # The connection is done by reseting to the bootloader (default)
        if boot == "reset":
            print("Reset to bootloader mode ..."),
            sys.stdout.flush()
            if bl.start_bootloader(warm_boot=True):
                print(" done!")
            else:
                print("Failed to warmboot")
                bl.close()
                sys.exit(-1)
        else:  # The connection is done by a cold boot ...
            print("Restart the Crazyflie you want to bootload in the next"),
            print(" 10 seconds ..."),

            sys.stdout.flush()
            if bl.start_bootloader(warm_boot=False):
                print(" done!")
            else:
                print("Cannot connect the bootloader!")
                bl.close()
                sys.exit(-1)

        print("Connected to bootloader on {} (version=0x{:X})".format(
            BootVersion.to_ver_string(bl.protocol_version),
            bl.protocol_version))

        if bl.protocol_version == BootVersion.CF2_PROTO_VER:
            targets += (bl.get_target(TargetTypes.NRF51),)
        targets += (bl.get_target(TargetTypes.STM32),)

        ######################################
        # Doing something (hopefully) useful
        ######################################

        # Print information about the targets
        for target in targets:
            print(target)
        if action == "info":
            None  # Already done ...
        elif action == "reset":
            print
            print("Reset in firmware mode ...")
            bl.reset_to_firmware()
        elif action == "flash":
            bl.flash(filename, targetnames)
            print("Reset in firmware mode ...")
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
