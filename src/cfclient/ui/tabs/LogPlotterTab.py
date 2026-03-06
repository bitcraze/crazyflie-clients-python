#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2024 Bitcraze AB
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
"""Tab for visualizing Crazyflie log CSV files."""

import logging
import os
from collections import OrderedDict

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from PyQt6 import uic
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox

__author__ = 'Bitcraze AB'
__all__ = ['LogPlotterTab']

logger = logging.getLogger(__name__)

log_plotter_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/logPlotterTab.ui")[0]

SUBPLOT_HEIGHT_PX = 300


class LogPlotterTab(TabToolbox, log_plotter_tab_class):
    """Tab for visualizing Crazyflie log CSV files."""

    def __init__(self, helper):
        super().__init__(helper, 'Log Plotter')
        self.setupUi(self)

        # Ordered dict: file_path -> {'df': DataFrame, 'display_name': str}
        self._file_data = OrderedDict()
        # Guard against recursive itemChanged signals while building tree
        self._building_tree = False

        # Debounce timer: defers plot re-render so checkbox interactions feel instant
        self._replot_timer = QTimer(self)
        self._replot_timer.setSingleShot(True)
        self._replot_timer.setInterval(150)
        self._replot_timer.timeout.connect(self._update_plots)

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.mainLayout.addWidget(main_splitter)

        # Left panel: vertical splitter with three subframes
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(self._create_file_picker())
        left_splitter.addWidget(self._create_signal_picker())
        left_splitter.addWidget(self._create_plot_config())
        main_splitter.addWidget(left_splitter)

        # Right panel: matplotlib toolbar + scrollable canvas
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        self._figure = Figure()
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, right_widget)
        right_layout.addWidget(self._toolbar)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setWidget(self._canvas)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_layout.addWidget(self._scroll_area, 1)

        main_splitter.addWidget(right_widget)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)

        self._update_plots()

    def _create_file_picker(self):
        group = QGroupBox("Files")
        layout = QVBoxLayout(group)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("Add Files\u2026")
        self._remove_btn = QPushButton("Remove File")
        self._clear_btn = QPushButton("Clear All")
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._remove_btn)
        btn_layout.addWidget(self._clear_btn)
        layout.addLayout(btn_layout)

        self._file_list = QListWidget()
        layout.addWidget(self._file_list)

        self._add_btn.clicked.connect(self._add_files)
        self._remove_btn.clicked.connect(self._remove_file)
        self._clear_btn.clicked.connect(self._clear_all)

        return group

    def _create_signal_picker(self):
        group = QGroupBox("Signals")
        layout = QVBoxLayout(group)

        self._signal_tree = QTreeWidget()
        self._signal_tree.setHeaderHidden(True)
        layout.addWidget(self._signal_tree)

        self._signal_tree.itemChanged.connect(self._on_item_changed)

        return group

    def _create_plot_config(self):
        group = QGroupBox("Plot Configuration")
        layout = QVBoxLayout(group)

        self._zero_time_cb = QCheckBox("Start time from zero")
        self._zero_time_cb.setChecked(True)
        self._link_x_cb = QCheckBox("Link X axes")
        self._link_x_cb.setChecked(True)
        self._grid_cb = QCheckBox("Grid")
        self._grid_cb.setChecked(True)

        layout.addWidget(self._zero_time_cb)
        layout.addWidget(self._link_x_cb)
        layout.addWidget(self._grid_cb)
        layout.addStretch()

        self._zero_time_cb.stateChanged.connect(self._update_plots)
        self._link_x_cb.stateChanged.connect(self._update_plots)
        self._grid_cb.stateChanged.connect(self._update_plots)

        return group

    # ------------------------------------------------------------------
    # File picker actions
    # ------------------------------------------------------------------

    def _add_files(self):
        default_dir = os.path.join(cfclient.config_path, "logdata")
        if not os.path.isdir(default_dir):
            default_dir = ""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Log Files", default_dir, "CSV Files (*.csv)"
        )
        needs_update = False
        for path in paths:
            if path in self._file_data:
                continue  # silently ignore duplicates
            df = self._load_csv(path)
            if df is None:
                continue
            display_name = self._get_display_name(path)
            self._file_data[path] = {'df': df, 'display_name': display_name}
            item = QListWidgetItem(display_name)
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._file_list.addItem(item)
            self._add_file_to_tree(path)
            needs_update = True
        if needs_update:
            self._update_plots()

    def _remove_file(self):
        selected = self._file_list.selectedItems()
        if not selected:
            return
        item = selected[0]
        path = item.data(Qt.ItemDataRole.UserRole)
        self._file_list.takeItem(self._file_list.row(item))
        del self._file_data[path]
        root = self._signal_tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == path:
                root.removeChild(child)
                break
        self._update_plots()

    def _clear_all(self):
        self._file_data.clear()
        self._file_list.clear()
        self._signal_tree.clear()
        self._update_plots()

    # ------------------------------------------------------------------
    # CSV loading
    # ------------------------------------------------------------------

    def _load_csv(self, path):
        try:
            df = pd.read_csv(path)
        except Exception as e:
            QMessageBox.warning(
                self, "Error loading file",
                f"Could not read {os.path.basename(path)}:\n{e}"
            )
            return None

        if 'Timestamp' in df.columns:
            ts_col = 'Timestamp'
        elif 'timestamp_ms' in df.columns:
            ts_col = 'timestamp_ms'
        else:
            QMessageBox.warning(
                self, "Error loading file",
                f"{os.path.basename(path)}: No Timestamp column found."
            )
            return None

        try:
            df[ts_col] = pd.to_numeric(df[ts_col], errors='raise')
        except (ValueError, TypeError):
            QMessageBox.warning(
                self, "Error loading file",
                f"{os.path.basename(path)}: Timestamp values are not numeric."
            )
            return None

        df = df.copy()
        df['_time_s'] = df[ts_col] / 1000.0

        drop_cols = {ts_col, 'block', '_time_s'}
        signal_cols = [c for c in df.columns if c not in drop_cols]
        return df[['_time_s'] + signal_cols]

    def _get_display_name(self, path):
        base = os.path.basename(path)
        existing = {d['display_name'] for d in self._file_data.values()}
        if base not in existing:
            return base
        counter = 2
        while f"{base} ({counter})" in existing:
            counter += 1
        return f"{base} ({counter})"

    # ------------------------------------------------------------------
    # Signal picker tree
    # ------------------------------------------------------------------

    def _add_file_to_tree(self, path):
        data = self._file_data[path]
        df = data['df']

        self._building_tree = True

        file_item = QTreeWidgetItem([data['display_name']])
        file_item.setData(0, Qt.ItemDataRole.UserRole, path)
        file_item.setFlags(
            file_item.flags()
            | Qt.ItemFlag.ItemIsAutoTristate
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        file_item.setCheckState(0, Qt.CheckState.Unchecked)

        signal_cols = [c for c in df.columns if c != '_time_s']

        groups = OrderedDict()
        for col in signal_cols:
            dot_pos = col.find('.')
            group = col[:dot_pos] if dot_pos > 0 else '(ungrouped)'
            groups.setdefault(group, []).append(col)

        for group_name, signals in groups.items():
            group_item = QTreeWidgetItem([group_name])
            group_item.setData(0, Qt.ItemDataRole.UserRole, None)
            group_item.setFlags(
                group_item.flags()
                | Qt.ItemFlag.ItemIsAutoTristate
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            group_item.setCheckState(0, Qt.CheckState.Unchecked)

            for signal in signals:
                sig_item = QTreeWidgetItem([signal])
                sig_item.setData(0, Qt.ItemDataRole.UserRole, (path, signal))
                sig_item.setFlags(sig_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                sig_item.setCheckState(0, Qt.CheckState.Unchecked)
                group_item.addChild(sig_item)

            file_item.addChild(group_item)

        self._signal_tree.addTopLevelItem(file_item)
        file_item.setExpanded(True)
        for i in range(file_item.childCount()):
            file_item.child(i).setExpanded(True)

        self._building_tree = False

    def _on_item_changed(self, item, column):
        if self._building_tree:
            return

        # Cascade check state downward when a file or group node is toggled
        state = item.checkState(0)
        if state != Qt.CheckState.PartiallyChecked and item.childCount() > 0:
            self._building_tree = True
            self._cascade_check(item, state)
            self._building_tree = False

        self._replot_timer.start()

    def _cascade_check(self, parent, state):
        for i in range(parent.childCount()):
            child = parent.child(i)
            child.setCheckState(0, state)
            self._cascade_check(child, state)

    def _get_checked_signals(self):
        """Return ordered list of (file_path, signal_name) for all checked leaves."""
        result = []
        root = self._signal_tree.invisibleRootItem()
        for path in self._file_data:
            file_item = None
            for i in range(root.childCount()):
                if root.child(i).data(0, Qt.ItemDataRole.UserRole) == path:
                    file_item = root.child(i)
                    break
            if file_item is None:
                continue
            for gi in range(file_item.childCount()):
                group_item = file_item.child(gi)
                for si in range(group_item.childCount()):
                    sig_item = group_item.child(si)
                    if sig_item.checkState(0) == Qt.CheckState.Checked:
                        entry = sig_item.data(0, Qt.ItemDataRole.UserRole)
                        if entry:
                            result.append(entry)
        return result

    # ------------------------------------------------------------------
    # Plot rendering
    # ------------------------------------------------------------------

    def _update_plots(self, *args):
        checked = self._get_checked_signals()
        self._figure.clear()

        if not checked:
            ax = self._figure.add_subplot(1, 1, 1)
            ax.axis('off')
            ax.text(
                0.5, 0.5, 'No signals selected',
                ha='center', va='center',
                transform=ax.transAxes,
                fontsize=14, color='gray',
            )
            self._canvas.setFixedSize(800, 400)
            self._canvas.draw()
            return

        n = len(checked)
        zero_time = self._zero_time_cb.isChecked()
        link_x = self._link_x_cb.isChecked()
        show_grid = self._grid_cb.isChecked()

        # Global time offset (minimum timestamp across all selected signals)
        t_offset = 0.0
        if zero_time:
            all_mins = []
            for path, _sig in checked:
                valid = self._file_data[path]['df']['_time_s'].dropna()
                if not valid.empty:
                    all_mins.append(valid.min())
            if all_mins:
                t_offset = min(all_mins)

        # Size the canvas: width fills viewport, height proportional to subplot count
        vp_width = self._scroll_area.viewport().width()
        width = max(vp_width - 4, 600)
        height = n * SUBPLOT_HEIGHT_PX
        self._canvas.setFixedSize(width, height)

        axes = []
        for i, (path, signal) in enumerate(checked):
            sharex = axes[0] if link_x and axes else None
            ax = self._figure.add_subplot(n, 1, i + 1, sharex=sharex)
            axes.append(ax)

            df = self._file_data[path]['df']
            display_name = self._file_data[path]['display_name']

            t = df['_time_s'] - t_offset
            y = df[signal]
            mask = y.notna()
            t_plot = t[mask]
            y_plot = y[mask]

            if not t_plot.empty:
                ax.plot(t_plot.values, y_plot.values)

            ax.set_title(f"{display_name}:{signal}")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel(signal)
            ax.grid(show_grid)

        self._figure.tight_layout()
        self._canvas.draw()
