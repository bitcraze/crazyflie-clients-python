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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
The Crazyflie module is used to easily connect/send/receive data
from a Crazyflie.

Each function in the Crazyflie has a class in the module that can be used
to access that functionality. The same design is then used in the Crazyflie
firmware which makes the mapping 1:1 in most cases.
"""

__author__ = 'Bitcraze AB'
__all__ = ['Crazyflie']

import logging
logger = logging.getLogger(__name__)
import time
from threading import Thread

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
    """ The Crazyflie class used for access the functionality in this
    module """
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

    def __init__(self, link=None):
        """ Create the objects from this module and register callbacks. """
        self.link = link

        self.incomming = _IncomingPacketHandler(self)
        self.incomming.setDaemon(True)
        self.incomming.start()

        self.commander = Commander(self)
        self.log = Log(self)
        self.console = Console(self)
        self.param = Param(self)

        self._log_toc_updated = False
        self._param_toc_updated = False

        self.link_uri = ""

        # Used for retry when no reply was sent back
        self.receivedPacket.add_callback(self._check_for_initial_packet_cb)
        self.answer_timers = {}

        # Connect callbacks to logger
        self.disconnected.add_callback(
            lambda uri: logger.info("Callback->Disconnected from [%s]", uri))
        self.connected.add_callback(
            lambda uri: logger.info("Callback->Connected to [%s]", uri))
        self.connectionLost.add_callback(
            lambda uri, errmsg: logger.info("Callback->Connectionl ost to"
                                            " [%s]: %s", uri, errmsg))
        self.connectionFailed.add_callback(
            lambda uri, errmsg: logger.info("Callback->Connected failed to"
                                            " [%s]: %s", uri, errmsg))
        self.connectionInitiated.add_callback(
            lambda uri: logger.info("Callback->Connection initialized[%s]",
                                    uri))
        self.connectSetupFinished.add_callback(
            lambda uri: logger.info("Callback->Connection setup finished [%s]",
                                    uri))

    def _start_connection_setup(self):
        """Start the connection setup by refreshing the TOCs"""
        logger.info("We are connected[%s], request connection setup",
                    self.link_uri)
        self.log.refresh_toc(self._log_toc_updated_cb)

    def _param_toc_updated_cb(self):
        """Called when the param TOC has been fully updated"""
        logger.info("Param TOC finished updating")
        self._param_toc_updated = True
        if (self._log_toc_updated is True and self._param_toc_updated is True):
            self.connectSetupFinished.call(self.link_uri)

    def _log_toc_updated_cb(self):
        """Called when the log TOC has been fully updated"""
        logger.info("Log TOC finished updating")
        self._log_toc_updated = True
        self.param.refresh_toc(self._param_toc_updated_cb)

        if (self._log_toc_updated and self._param_toc_updated):
            logger.info("All TOCs finished updating")
            self.connectSetupFinished.call(self.link_uri)

    def _link_error_cb(self, errmsg):
        """Called from the link driver when there's an error"""
        logger.warning("Got link error callback [%s] in state [%s]",
                       errmsg, self.state)
        if (self.link is not None):
            self.link.close()
        self.link = None
        if (self.state == State.INITIALIZED):
            self.connectionFailed.call(self.link_uri, errmsg)
        if (self.state == State.CONNECTED or
                self.state == State.SETUP_FINISHED):
            self.disconnected.call(self.link_uri)
            self.connectionLost.call(self.link_uri, errmsg)
        self.state = State.DISCONNECTED

    def _link_quality_cb(self, percentage):
        """Called from link driver to report link quality"""
        self.linkQuality.call(percentage)

    def _check_for_initial_packet_cb(self, data):
        """Called when first packet arrives from Crazyflie.

        This is used to determine if we are connected to something that is
        answering.
        """
        self.state = State.CONNECTED
        self.connected.call(self.link_uri)
        self.receivedPacket.remove_callback(self._check_for_initial_packet_cb)

    def open_link(self, link_uri):
        """
        Open the communication link to a copter at the given URI and setup the
        connection (download log/parameter TOC).
        """
        self.connectionInitiated.call(link_uri)
        self.state = State.INITIALIZED
        self.link_uri = link_uri
        self._log_toc_updated = False
        self._param_toc_updated = False
        try:
            self.link = cflib.crtp.get_link_driver(link_uri,
                                                   self._link_quality_cb,
                                                   self._link_error_cb)

            # Add a callback so we can check that any data is comming
            # back from the copter
            self.receivedPacket.add_callback(self._check_for_initial_packet_cb)

            self._start_connection_setup()
        except Exception as e:
            import traceback
            logger.error("Couldn't load link driver: %s\n\n%s",
                         e, traceback.format_exc())
            exceptionText = "Couldn't load link driver: %s\n\n%s" % (
                            e, traceback.format_exc())
            if self.link:
                self.link.close()
            self.connectionFailed.call(link_uri, exceptionText)

    def close_link(self):
        """ Close the communication link. """
        logger.info("Closing link")
        if (self.link is not None):
            self.commander.send_setpoint(0, 0, 0, 0)
        if (self.link is not None):
            self.link.close()
        #self.link = None
        self.disconnected.call(self.link_uri)

    def add_port_callback(self, port, cb):
        self.incomming.add_port_callback(port, cb)

    def remove_port_callback(self, port, cb):
        self.incomming.remove_port_callback(port, cb)

    def _no_answer_do_retry(self, pk):
        logger.debug("ExpectAnswer: No answer on [%d], do retry", pk.port)
        # Cancel timer before calling for retry to help bug hunting
        oldTimer = self.answer_timers[pk.port]
        if (oldTimer is not None):
            oldTimer.cancel()
            self.send_packet(pk, True)
        else:
            logger.warning("ExpectAnswer: ERROR! Was doing retry but"
                           "timer was None")

    def send_packet(self, pk, expect_answer=False):
        """Send a packet through the link interface.

        pk -- Packet to send
        expect_answer -- True if a packet from the Crazyflie is expected to
                         be sent back, otherwise false

        """
        if (self.link is not None):
            self.link.send_packet(pk)
            if (expect_answer):
                logger.debug("ExpectAnswer: Will expect answer on port [%d]",
                             pk.port)
                new_timer = Timer(1, lambda: self._no_answer_do_retry(pk))
                try:
                    old_timer = self.answer_timers[pk.port]
                    if (old_timer is not None):
                        old_timer.cancel()
                        # If we get here a second call has been made to send
                        # packet on this port before we have gotten the first
                        # one back. This is an error and might cause loss of
                        # packets!!
                        logger.warning("ExpectAnswer: ERROR! Older timer whas"
                                       " running while scheduling new one on "
                                       "[%d]", pk.port)
                except KeyError:
                    pass
                self.answer_timers[pk.port] = new_timer
                new_timer.start()


class _IncomingPacketHandler(Thread):
    """Handles incoming packets and sends the data to the correct receivers"""
    def __init__(self, cf):
        Thread.__init__(self)
        self.cf = cf
        self.cb = []

    def add_port_callback(self, port, cb):
        """Add a callback for data that comes on a specific port"""
        logger.debug("Adding callback on port [%d] to [%s]", port, cb)
        self.add_header_callback(cb, port, 0, 0xff, 0x0)

    def remove_port_callback(self, port, cb):
        """Remove a callback for data that comes on a specific port"""
        logger.debug("Removing callback on port [%d] to [%s]", port, cb)
        for port_callback in self.cb:
            if (port_callback[0] == port and port_callback[4] == cb):
                self.cb.remove(port_callback)

    def add_header_callback(self, cb, port, channel, port_mask=0xFF,
                            channel_mask=0xFF):
        """
        Add a callback for a specific port/header callback with the
        possibility to add a mask for channel and port for multiple
        hits for same callback.
        """
        self.cb.append([port, port_mask, channel, channel_mask, cb])

    def run(self):
        while(True):
            if self.cf.link is None:
                time.sleep(1)
                continue
            pk = self.cf.link.receive_packet(1)

            if pk is None:
                continue

            #All-packet callbacks
            self.cf.receivedPacket.call(pk)

            found = False
            for cb in self.cb:
                if (cb[0] == pk.port & cb[1] and
                        cb[2] == pk.channel & cb[3]):
                    try:
                        cb[4](pk)
                    except Exception:  # pylint: disable=W0703
                        # Disregard pylint warning since we want to catch all
                        # exceptions and we can't know what will happen in
                        # the callbacks.
                        import traceback
                        logger.warning("Exception while doing callback on port"
                                       " [%d]\n\n%s", pk.port,
                                       traceback.format_exc())
                    if (cb[0] != 0xFF):
                        found = True

            if not found:
                logger.warning("Got packet on header (%d,%d) but no callback "
                               "to handle it", pk.port, pk.channel)
