#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Configuration block compiler/decompiler
# Fully static version (to be considered as a prototype...)!
from ConfigParser import ConfigParser
import struct
import sys

#Radio speed enum type
speeds = ["250K", "1M", "2M"]
radioSpeedPos = 2

defaultConfig = """#Crazyflie config block
#default version generated from squatch
[radio]
channel= 100
speed= 2M

[calib]
pitchTrim= 0.0
rollTrim= 0.0
"""

config = """#Crazyflie config block
#Block version %d extracted from copter
[radio]
channel= %d
speed= %s

[calib]
pitchTrim= %f
rollTrim= %f
"""

configVersion = 0
structFormat = "<BBBff"

def checksum256(st):
    return reduce(lambda x,y:x+y, map(ord, st)) % 256

def compileBlock(configFile, binFile):
  config = ConfigParser()
  
  config.read(configFile)

  block = (configVersion, )

  block += (config.getint("radio", "channel"),)
  block += (speeds.index(config.get("radio", "speed").upper()),)

  block += (config.getfloat("calib", "pitchTrim"),)
  block += (config.getfloat("calib", "rollTrim"),)

  bin = struct.pack(structFormat, *block)

  #Adding some magic:
  bin = "0xBC" + bin

  bin += struct.pack("B", 256-checksum256(bin))
  
  #print("Config block checksum: %02x" % bin[len(bin)-1])
  
  bfile = open(binFile, "w")
  bfile.write(bin)
  bfile.close()
  
  print "Config block compiled successfully to", binFile

def decompileBlock(binFile, configFile):
  bfile = open(binFile)
  bin = bfile.read()
  bfile.close()
  
  if bin[0:4]!="0xBC" or len(bin)<(struct.calcsize(structFormat)+5) or checksum256(bin[0:struct.calcsize(structFormat)+5])!=0:
    print "Config block erased of altered, generating default file"
    cfile = open(configFile, "w")
    cfile.write(defaultConfig)
    cfile.close()
  else:
    block = struct.unpack(structFormat, bin[4:struct.calcsize(structFormat)+4])
    if block[0]!=configVersion:
      print "Error! wrong configuration block version, this program must certainly be updated!"
      return
    
    block = block[0:radioSpeedPos] + (speeds[block[radioSpeedPos]],) + block[radioSpeedPos+1:len(block)]
    
    cfile = open(configFile, "w")
    cfile.write(config %block)
    cfile.close()
    print "Config block successfully extracted to", configFile

if __name__=="__main__":
  if len(sys.argv)<4 or (sys.argv[1]!="generate" and sys.argv[1]!="extract"):
    print "Configuration block compiler/decompiler."
    print "  Usage: %s <generage|extract> <infile> <outfile>" % sys.argv[0]

  if sys.argv[1] == "generate":
    compileBlock(sys.argv[2], sys.argv[3])
  else:
    decompileBlock(sys.argv[2], sys.argv[3])


