# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2017 Bitcraze AB
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


class RangeRecorder:
    def __init__(self, update_period_ms, anchor_indexes):
        self._MAX_ANCHORS = 8

        self._update_period_ms = update_period_ms
        self._max_time_diff = update_period_ms / 3

        self._data_sets = []

        self._anchor_indexes = anchor_indexes
        self._anchor_count = len(self._anchor_indexes)

    def record(self, required_good_samples, data, recording_finished_callback,
               update_ui_callback, error_callback):
        recording_data = {
            'end_count': required_good_samples,
            'latest': 0,
            'workspace': [None] * self._MAX_ANCHORS,
            'data': data,
            'done_callback': recording_finished_callback,
            'update_ui_callback': update_ui_callback,
            'error_callback': error_callback,
            'done': False,
        }
        self._data_sets.append(recording_data)

    def range_received(self, anchor, distance, timestamp):
        for data_set in self._data_sets:
            self._process_range(data_set, anchor, distance, timestamp)

        for data_set in self._data_sets:
            try:
                nr_of_samples = len(data_set['data'])
                progress = nr_of_samples / data_set['end_count']
                data_set['update_ui_callback'](progress)

                if nr_of_samples >= data_set['end_count']:
                    data_set['done'] = True
                    data_set['update_ui_callback'](1.0)
                    data_set['done_callback']()
            except Exception as e:
                data_set['done'] = True
                data_set['error_callback'](e)

        self._data_sets = list(
            filter(lambda x: x['done'] is False, self._data_sets))

    def _process_range(self, data_set, anchor, distance, timestamp):
        # This method is called when log data arrives from the Crazyflie. The
        # range data arrives in chunks with some of the anchors in each chunk.
        # Each chunk have a timestamps and we use the
        # timestamps to try to figure out how to group them
        if (abs(timestamp - data_set['latest']) < self._max_time_diff):
            self._process_range_current_slot(data_set, anchor, distance)
        else:
            self._process_range_new_slot(data_set, anchor, distance, timestamp)

    def _process_range_new_slot(self, data_set, anchor, distance, timestamp):
        self._append_workspace_if_complete(data_set)
        data_set['latest'] = timestamp
        data_set['workspace'] = [None] * self._MAX_ANCHORS
        self._process_range_current_slot(data_set, anchor, distance)

    def _process_range_current_slot(self, data_set, anchor, distance):
        data_set['workspace'][anchor] = distance

    def _append_workspace_if_complete(self, data_set):
        ws = data_set['workspace']

        are_all_anchors_received = True
        for i in self._anchor_indexes:
            if not ws[i]:
                are_all_anchors_received = False
                break

        if are_all_anchors_received:
            self._append_packed(ws, data_set['data'])

            # Create a new empty workspace to avoid to add the workspace twice
            # if we get spurious anchor data that we do not want
            data_set['workspace'] = [None] * self._MAX_ANCHORS

    def _append_packed(self, workspace, data):
        packed = [None] * self._anchor_count

        for i in range(self._anchor_count):
            packed[i] = workspace[self._anchor_indexes[i]]

        data.append(packed)
