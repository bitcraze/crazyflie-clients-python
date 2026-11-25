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
The state of the consoles shown in the console tab. The library has no timestamps, so every line
is stamped with the time the client received it, in seconds since connect.
"""

import heapq
import time
from collections import deque

__author__ = 'Bitcraze AB'
__all__ = ['ALL', 'STM32_PATH', 'ConsoleModel', 'display_name', 'segment_label', 'split_path']

STM32_PATH = 'cf:stm32'
# Names of the consoles that are known, others are shown with their path. There is no other console
# on the Crazyflie itself, so cf:stm32 is the Crazyflie.
SEGMENT_LABELS = {STM32_PATH: 'Crazyflie', 'deck:bcCam': 'Wifi Camera Deck'}
# Key of the view that merges all open consoles
ALL = 'all'

# Assigned in list() order. Colors next to each other differ in lightness and not only in hue,
# so they can be told apart by people with color vision deficiency and in grayscale.
PALETTE = ['#1f5fbf', '#d2691e', '#552c9a', '#17a398', '#6b4500']


def color_for_index(index):
    # With more consoles than colors the colors are reused, the names tell them apart
    return PALETTE[index % len(PALETTE)]


def split_path(path):
    """'deck:bcCam' gives ('deck:', 'bcCam')"""
    head, sep, tail = path.rpartition(':')
    return head + sep, tail


def display_name(path):
    return SEGMENT_LABELS.get(path) or split_path(path)[1]


def segment_label(path):
    return SEGMENT_LABELS.get(path)


class Line:
    __slots__ = ('seq', 't', 'path', 'text', 'separator')

    def __init__(self, seq, t, path, text, separator=False):
        self.seq = seq      # Order of completion over all consoles
        self.t = t          # Seconds since the first connect when the first character was received
        self.path = path
        self.text = text
        self.separator = separator  # Marks a new connection, not output from the Crazyflie


class ConsoleState:

    def __init__(self, path, index):
        self.path = path
        self.color = color_for_index(index)
        self.lines = deque()
        self.partial = None         # (t, text) of a line that has not ended yet
        self.is_open = False
        self.opening = False        # Open requested, replay of history not finished


class ConsoleModel:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.reset()

    def reset(self):
        self._connect_time = self._clock()
        self._connected_before = False
        self._seq = 0
        self.states = {}
        self.catalog = []
        self.selected = STM32_PATH
        self.set_catalog([STM32_PATH])

    def reconnect(self):
        """A new connection: the output stays, with a separator, but the consoles have to be opened again"""
        if not self._connected_before:
            # Times count from the first connect
            self._connected_before = True
            self._connect_time = self._clock()
        for state in self.states.values():
            if state.partial is not None:
                self._seq += 1
                state.lines.append(Line(self._seq, state.partial[0], state.path, state.partial[1]))
                state.partial = None
        # The same sequence number for every console, so that All shows one separator
        self._seq += 1
        now = self.now()
        for state in self.states.values():
            if state.lines and not state.lines[-1].separator:
                state.lines.append(Line(self._seq, now, state.path, 'Reconnected', True))
            state.is_open = False
            state.opening = False
        self.set_catalog([STM32_PATH])
        if self.selected not in self.catalog:
            self.selected = STM32_PATH

    def now(self):
        return self._clock() - self._connect_time

    def set_catalog(self, paths):
        paths = [STM32_PATH] + [p for p in paths if p != STM32_PATH]
        self.catalog = paths
        for index, path in enumerate(paths):
            if path not in self.states:
                self.states[path] = ConsoleState(path, index)

    @property
    def other_paths(self):
        return [p for p in self.catalog if p != STM32_PATH]

    @property
    def open_paths(self):
        return [p for p in self.catalog if self.states[p].is_open]

    def begin_open(self, path):
        # Output received until mark_open() is the replay of the history
        state = self.states[path]
        state.opening = True

    def mark_open(self, path):
        state = self.states[path]
        state.opening = False
        state.is_open = True

    def mark_open_failed(self, path):
        state = self.states[path]
        state.opening = False
        state.is_open = False

    def feed(self, path, text):
        """Add text received from a console, a line that has not ended is kept as a partial line"""
        state = self.states.get(path)
        if state is None or not (state.is_open or state.opening):
            return

        now = self.now()
        pieces = text.split('\n')
        for index, piece in enumerate(pieces):
            if state.partial is None and piece:
                state.partial = (now, '')
            if state.partial is not None:
                state.partial = (state.partial[0], state.partial[1] + piece)
            if index == len(pieces) - 1:
                break
            # Lines can end with '\r\n' or '\n\r'
            t, line = state.partial if state.partial is not None else (now, '')
            state.partial = None
            self._seq += 1
            state.lines.append(Line(self._seq, t, path, line.strip('\r')))
        if state.partial is not None:
            state.partial = (state.partial[0], state.partial[1].lstrip('\r'))
            if not state.partial[1]:
                state.partial = None

    def select(self, key):
        self.selected = key

    def _view(self, key):
        """The consoles shown by a view"""
        if key == ALL:
            return [self.states[p] for p in self.open_paths]
        return [self.states[key]]

    @staticmethod
    def _one_separator(lines):
        """Lines in order, with the separators of the consoles of one reconnect as one"""
        return [line for index, line in enumerate(lines)
                if not (line.separator and index and lines[index - 1].separator and lines[index - 1].seq == line.seq)]

    def view_lines(self, key):
        return self._one_separator(list(heapq.merge(*[s.lines for s in self._view(key)], key=lambda line: line.seq)))

    def lines_after(self, key, after_seq):
        found = []
        for state in self._view(key):
            newest_first = []
            for line in reversed(state.lines):
                if line.seq <= after_seq:
                    break
                newest_first.append(line)
            found.extend(newest_first)
        found.sort(key=lambda line: line.seq)
        return self._one_separator(found)

    def view_partials(self, key):
        partials = [Line(0, s.partial[0], s.path, s.partial[1]) for s in self._view(key) if s.partial]
        return sorted(partials, key=lambda line: line.t)

    def clear(self, key):
        for state in self._view(key):
            state.lines.clear()
