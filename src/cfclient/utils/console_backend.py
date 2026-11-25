#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2026 Bitcraze AB
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
#  this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
Connects the console tab to the console API of cflib. Console.list() and Console.open() block and
cannot be called from a cflib callback, so they run on a worker thread. The signals carry the
generation of the connection, so that the tab can ignore what is left from an earlier one.
"""

import logging
import queue
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from cflib.crazyflie.console import ConsoleError

__author__ = 'Bitcraze AB'
__all__ = ['ConsoleBackend']

logger = logging.getLogger(__name__)

# The firmware answers "not ready" for a while after it started, which is not an error
LIST_TIMEOUT = 15.0


class ConsoleBackend(QObject):
    # All start with the generation of the connection
    catalog = pyqtSignal(int, list)
    catalog_failed = pyqtSignal(int, object, str)   # errno, message
    opened = pyqtSignal(int, str)
    open_failed = pyqtSignal(int, str, object, str)   # path, errno, message
    chunk = pyqtSignal(int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = 0
        self._console = None
        self._handles = {}
        self._jobs = queue.Queue()
        self._thread = None

    def start(self, console):
        """Begin a session on a newly connected Crazyflie, returns its generation"""
        self._generation += 1
        self._console = console
        # Handles of the earlier connection are already closed by cflib
        self._handles = {}
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, name='ConsoleBackendThread', daemon=True)
            self._thread.start()
        return self._generation

    def stop(self):
        self._generation += 1
        self._console = None
        self._handles = {}

    def request_list(self):
        self._submit(self._do_list)

    def open(self, path):
        self._submit(lambda gen, console, handles: self._do_open(gen, console, handles, path))

    def _submit(self, job):
        if self._console is not None:
            self._jobs.put((self._generation, self._console, self._handles, job))

    def _work(self):
        while True:
            generation, console, handles, job = self._jobs.get()
            if generation != self._generation:
                continue
            try:
                job(generation, console, handles)
            except Exception:
                logger.exception('Unexpected error in the console worker')

    @staticmethod
    def _errno(error):
        return getattr(error, 'errno', None) if isinstance(error, ConsoleError) else None

    def _do_list(self, generation, console, handles):
        try:
            paths = console.list(timeout=LIST_TIMEOUT)
        except (ConsoleError, RuntimeError) as e:
            self.catalog_failed.emit(generation, self._errno(e), str(e))
        else:
            self.catalog.emit(generation, paths)

    def _do_open(self, generation, console, handles, path):
        if path in handles:
            return

        def text_cb(text):
            self.chunk.emit(generation, path, text)

        try:
            # The history is passed to text_cb before this returns
            handles[path] = console.open(path, text_cb=text_cb)
        except (ConsoleError, RuntimeError) as e:
            self.open_failed.emit(generation, path, self._errno(e), str(e))
        else:
            self.opened.emit(generation, path)
