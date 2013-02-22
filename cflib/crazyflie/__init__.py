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
The Crazyflie module is used to easily connect/send/receive data
from a Crazyflie.

Each function in the Crazyflie has a class in the module that can be used
to access that functionality. The same design is then used in the Crazyflie
firmware which makes the mapping 1:1 in most cases.
"""

__author__ = 'Bitcraze AB'
__all__ = ['Crazyflie']


from cflib.crtp.crtpstack import CRTPPacket, CRTPPort

from threading import Thread
import time

import struct

from threading import Timer

from .commander import Commander
from .console import Console
from .param import Param
from .log import Log

import cflib.crtp

from cflib.utils.callbacks import Caller

class State:
    """ Stat of the connection procedure """
    DISCONNECTED = 0
    INITIALIZED = 1
    CONNECTED = 2
    SETUP_FINISHED = 3

class Crazyflie():
    """ The Crazyflie class used for access the functionality in this module """
    # Callback callers
    disconnected = Caller()
    connectionLost = Caller()
    connected = Caller()
    connectionInitiated = Caller()
    connectSetupFinished = Caller()
    connectionFailed = Caller()
    receivedPacket = Caller()
    linkQuality = Caller()

    state = State.DISCONNECTED

    def __init__(self, link = None):
        """ Create the objects from this module and register callbacks. """
        self.link = link

        self.incomming = CrazyflieIncomming(self)
        self.incomming.setDaemon(True)
        self.incomming.start()
        
        self.commander = Commander(self)
        self.log = Log(self)
        self.console = Console(self)
        self.param = Param(self)

        self.linkURI = ""

        # Used for retry when no reply was sent back
        self.receivedPacket.addCallback(self.checkIncommingAnswers)
        self.answerTimers = {}

        
    def doConnectionSetup(self, link):
        print "Crazyflie: We are connected[%s], request connection setup" % link
        self.linkString = link
        
        self.log.refreshTOC(self.logTOCUpdated)

    def paramTOCUpdated(self):
        print "Crazyflie: Param TOC finished updating"
        self.paramTocUpdated = True
        if (self.logTocUpdated == True and self.paramTocUpdated == True):
            self.connectSetupFinished.call(self.linkString)

    def logTOCUpdated(self):
        print "Crazyflie: Log TOC finished updating"
        self.logTocUpdated = True
        self.param.refreshTOC(self.paramTOCUpdated)

        if (self.logTocUpdated == True and self.paramTocUpdated == True):
            print "Crazyflie: All TOCs finished updating"
            self.connectSetupFinished.call(self.linkString)
        
    def linkErrorCallback(self, errmsg):
        print "Got linkErrorCallback"
        if (self.link != None):
            self.link.close()
        self.link = None
        if (self.state == State.INITIALIZED):
            self.connectionFailed.call(self.linkURI, errmsg)
        if (self.state == State.CONNECTED or self.state == State.SETUP_FINISHED):
            self.disconnected.call(self.linkURI)
            self.connectionLost.call(self.linkURI, errmsg)
        self.state = State.DISCONNECTED

    def linkQualityCallback(self, percentage):
        self.linkQuality.call(percentage)
        
    def checkIncommingPacket(self, data):
        self.state = State.CONNECTED
        self.connected.call(self.linkURI)
        self.receivedPacket.removeCallback(self.checkIncommingPacket)

    def openLink(self, linkString):
        """
        Open the communication link to a copter at the given URI and setup the
        connection (download log/parameter TOC).
        """
        self.connectionInitiated.call(linkString)
        self.state = State.INITIALIZED
        self.linkURI = linkString
        self.logTocUpdated = False
        self.paramTocUpdated = False
        try:
            self.link = cflib.crtp.getDriver(linkString, self.linkQualityCallback, self.linkErrorCallback)

            # Add a callback so we can check that any data is comming back from the copter
            self.receivedPacket.addCallback(self.checkIncommingPacket)

            self.doConnectionSetup(linkString)    
        except Exception as e:
            import traceback
            exceptionText = "Couldn't load link driver: %s\n\n%s" % (e, traceback.format_exc())
            if self.link:
                self.link.close()
            self.connectionFailed.call(linkString, exceptionText)

    def isLinkUp(self):
        if (self.link == None):
            return False
        return True

    def closeLink(self):
        """ Close the communication link. """
        print "CF: Closing link"
        if (self.isLinkUp()):
            self.commander.sendControlSetpoint(0,0,0,0)
        if (self.link != None):
            self.link.close()
        #self.link = None
        self.disconnected.call(self.linkURI)

    def addPortCallback(self, port, cb):
        self.incomming.addPortCallback(port, cb)

    def removePortCallback(self, port, cb):
        self.incomming.removePortCallback(port, cb)

    def noAnswerDoRetry(self, pk):
        print "ExpectAnswer: No answer on [%d], do retry" % pk.getPort()
        # Cancel timer before calling for retry to help bug hunting
        oldTimer = self.answerTimers[pk.getPort()]
        if (oldTimer != None):
            oldTimer.cancel()
            self.sendLinkPacket(pk, True)
        else:
            print "ExpectAnswer: ERROR! Was doing retry but timer was None"

    def checkIncommingAnswers(self, pk):
        try:
            timer = self.answerTimers[pk.getPort()]
            if (timer != None):
                print "ExpectAnswer: Got answer back on port [%d], cancelling timer" % pk.getPort()
                timer.cancel()
                self.answerTimers[pk.getPort()] = None
        except Exception as e:
            #print "ExpectAnswer: Checking incomming answer on [%d] but not requested (%s)" % (pk.getPort(), e)
            return

    def sendLinkPacket(self, pk, expectAnswer=False):
        #print "ExpectAnswer: sendLinkPacket on [%d], safe? %s" % (pk.getPort(), expectAnswer)
        if (self.link != None):
            self.link.sendPacket(pk)
            if (expectAnswer == True):
                print "ExpectAnswer: Will expect answer on port [%d]" % pk.getPort()
                newTimer = Timer(1, lambda : self.noAnswerDoRetry(pk))
                try:
                    oldTimer = self.answerTimers[pk.getPort()]
                    if (oldTimer != None):
                        oldTimer.cancel()
                        # If we get here a second call has been made to send packet on this port before
                        # we have gotten the first one back. This is an error and might cause loss of packets!!
                        print "ExpectAnswer: ERROR! Older timer whas running while scheduling new one on [%d]" % pk.getPort()
                except Exception:
                    pass
                self.answerTimers[pk.getPort()] = newTimer
                newTimer.start() 

class CrazyflieIncomming(Thread):
   
    def __init__(self, cf):
        Thread.__init__(self)
        self.cf = cf
        self.cb = []

    def addPortCallback(self, port, cb):
        print "CF: Adding callback on port [%d] to [%s]" % (port, cb)
        self.addHeaderCallback(cb, port, 0, 0xff, 0x0);

    def removePortCallback(self, port, cb):
        print "CF: Removing callback on port [%d] to [%s]" % (port, cb)
        for p in self.cb:
            if (p[0] == port and p[4] == cb):
                self.cb.remove(p)
    
    def addHeaderCallback(self, cb, port, channel, portMask=0xFF, channelMask=0xFF):
        self.cb.append([port, portMask, channel, channelMask, cb])

    def run(self):
        while(True):
            pk = None
            try:
                pk = self.cf.link.receivePacket(1)
            except Exception as e:
                #print e
                time.sleep(1)  
                
            if pk == None:
                continue
            
            #All-packet callbacks
            self.cf.receivedPacket.call(pk)
            
            found = False
            for cb in self.cb:
                if cb[0] == pk.getPort()&cb[1] and cb[2] == pk.getChannel()&cb[3]:
                    try:
                        cb[4](pk)
                    except Exception as e:
                        import traceback
                        print "CF: Exception while doing callback on port [%d]\n\n%s" % (pk.getPort(), traceback.format_exc())
                    if (cb[0] != 0xFF):
                        found = True

            if not found:
                print "CF: Got packet on header (%d,%d) but no callback to handle it" % (pk.getPort(), pk.getChannel())
                print "Data: {}".format(pk.data)


from Queue import Queue

class PacketReceiver:
    """Helper class that permits to implement synchronous packet receiver"""
    
    def __init__(self, cf, port, channel=None):
        self.queue = Queue()
        self.cf = cf
        
        if channel:
            self.cf.incomming.addHeaderCallback(self.incoming, port, channel)
        else:
            self.cf.incomming.addPortCallback(port, self.incoming)
    
    def incoming(self, pk):
        self.queue.put(pk)
    
    def receive(self, timeout):
        try:
            return self.queue.get(True, timeout)
        except:
            return None

