# -*- coding: utf-8 -*-
#
#    ||          ____  _ __                           
# +------+      / __ )(_) /_______________ _____  ___ 
# | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#  ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Crazyflie client software
#
# Copyright (C) 2011-2012 Bitcraze AB
#

#Crazy Loader bootloader utility
#Can reset bootload and reset back the bootloader

import sys, os
import time
import struct

sys.path.append("..")

import cflib.crtp
from cflib.bootloader.cloader import Cloader

#Initialise the CRTP link driver
link = None
cload = None
try:
    cflib.crtp.initDrivers()
    link = cflib.crtp.getDriver("radio://0")
except(Exception):
    print "=============================="
    print " CrazyLoader Flash Utility"
    print "=============================="
    print
    print " Usage:", sys.argv[0], "[CRTP options] <action> [parameters]"
    print
    print "The CRTP options are described above"
    print
    print "Crazyload option:"
    print "   info        : Print the info of the bootloader and quit."
    print "                 Will let the target in bootloader mode"
    print "   reset       : Reset the device in firmware mode"
    print "   flash <img> : flash the <img> binary file from the first possible"
    print "                 page in flash and reset to firmware mode."
    sys.exit(0)
except Exception as e:
    print "CRTP Driver loading error:", e
    if link:
        link.close()
    sys.exit(-1)

#Set the default parameters
cpu_id = "32:00:6e:06:58:37:35:32:60:58:01:43" #Default to the arnaud's copter
clink = "radio://0/110"
action = "info"
boot = "cold"

#Analyse the command line parameters
sys.argv = sys.argv[1:]
argv = []

i=0;
while i<len(sys.argv):
    if sys.argv[i] == "-i":
        i+=1
        cpu_id = sys.argv[i]
    elif sys.argv[i] == "--cold-boot" or sys.argv[i] == "-c":
        boot = "cold"
    else:
        argv += [sys.argv[i]]
    i+=1
sys.argv = argv

#Try the alias for the cpu ids
try:
    cpu_id = idAlias[cpu_id]
except Exception:
    None

#Analyse the command
if len(sys.argv)<1:
    action="info"
elif sys.argv[0]=="info":
    actrion="info"
elif sys.argv[0]=="reset":
    action="reset"
elif sys.argv[0]=="flash":
    #print len(sys.argv)
    if len(sys.argv)<2:
        print "The flash action require a file name."
        link.close()
        sys.exit(-1)
    action = "flash"
    filename = sys.argv[1]
else:
    print "Action", sys.argv[0], "unknown!"
    link.close()
    sys.exit(-1)

try:
    #Initialise the cflib
    cload = Cloader(link, clink)

    #########################################
    # Get the connection with the bootloader
    #########################################
    if boot=="reset":  #The connection is done by reseting to the bootloader (default)
        sys.stdout.write("Reset to bootloader mode ...")
        sys.stdout.flush()
        if cload.resetBootloader(cload.decodeCpuId(cpu_id)):
            print " Done."
        else:
            print "\nFailed!\nThe loader with the ID", cpu_id, "does not answer."
            cload.close()
            sys.exit(-1)
    else: #The connection is done by a cold boot ...
        print "Restart the CrazyFlie you want to bootload in the next 10 seconds ..."

        if cload.coldBoot():
            print "Connection established!"
        else:
            print "Cannot connect the bootloader!"
            cload.close()
            sys.exit(-1)

    ######################################
    # Doing something (hopefully) usefull
    ######################################
    print "Flash pages: %d | Page size: %d | Buffer pages: %d | Start page: %d" % (cload.flashPages, cload.pageSize, cload.bufferPages, cload.startPage)
    print "%d KBytes of flash avaliable for firmware image." % ((cload.flashPages-cload.startPage)*cload.pageSize/1024)

    if action=="info":
        None #Already done ...
    elif action=="reset":
        print
        print "Reset in firmware mode ..."
        cload.resetFirmware(cload.decodeCpuId(cpu_id))
        print "Done!"
    elif action=="flash":
        print
        f=open(filename, "rb")
        if not f:
            print "Canno open image file", filename
            raise Exception()
        image = f.read()
        f.close()

        if len(image)>((cload.flashPages-cload.startPage)*cload.pageSize):
            print "Error: Not enough space to flash the image file."
            raise Exception()

        sys.stdout.write(("Flashing %d bytes (%d pages) " % ((len(image)-1), int(len(image)/cload.pageSize)+1)))
        sys.stdout.flush()

        #For each page
        ctr=0  #Buffer counter
        for i in range(0, int((len(image)-1)/cload.pageSize)+1):
            #Load the buffer
            if ((i+1)*cload.pageSize)>len(image):
                cload.loadBuffer(ctr, 0, image[i*cload.pageSize:])
            else:
                cload.loadBuffer(ctr, 0, image[i*cload.pageSize:(i+1)*cload.pageSize])

            ctr += 1

            sys.stdout.write(".")
            sys.stdout.flush()

            #Flash when the complete buffers are full
            if ctr>=cload.bufferPages:
                sys.stdout.write("%d" % ctr)
                sys.stdout.flush()
                if not cload.flash(0, cload.startPage+i-(ctr-1), ctr):
                    print "\nError during flash operation (code %d). Maybe wrong radio link?" % cload.getErrorCode()
                    raise Exception()

                ctr = 0

        if ctr>0:
            sys.stdout.write("%d" % ctr)
            sys.stdout.flush()
            if not cload.flash(0, cload.startPage+(int((len(image)-1)/cload.pageSize))-(ctr-1), ctr):
                print "\nError during flash operation (code %d). Maybe wrong radio link?1" % cload.getErrorCode()
                raise Exception()


        print

        print "Reset in firmware mode ..."
        cload.resetFirmware(cload.decodeCpuId(cpu_id))
        print "Done!"
    else:
        None
finally:
    #########################
    # Closing the connection
    #########################
    if (cload != None):
        cload.close()
