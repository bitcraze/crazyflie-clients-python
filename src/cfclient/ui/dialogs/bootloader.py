#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2026 Bitcraze AB
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
The bootloader dialog is used to update the Crazyflie firmware and to
read/write the configuration block in the Crazyflie flash.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from urllib.error import URLError
from urllib.request import urlopen

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtUiTools import loadUiType

import cfclient
from cfclient.gui import create_task
from cfclient.utils.config import Config
from cflib2 import LinkContext
from cflib2.bootloader import (
    BootMode,
    FirmwareImage,
    filter_images,
    flash,
    parse_firmware_zip,
)

__author__ = "Bitcraze AB"
__all__ = ["BootloaderDialog"]

logger = logging.getLogger(__name__)

service_dialog_class = loadUiType(cfclient.module_path + "/ui/dialogs/bootloader.ui")[0]

RELEASE_URL = "https://api.github.com/repos/bitcraze/crazyflie-release/releases"

ICON_PATH = os.path.join(cfclient.module_path, "ui", "icons")


# Module-level cache so releases survive dialog close/reopen
class BootloaderDialog(QtWidgets.QWidget, service_dialog_class):
    """Dialog for flashing Crazyflie firmware using cflib2's bootloader."""

    _progress_signal = Signal(dict)
    _release_firmwares_found = Signal(object)
    _release_fetch_done = Signal()
    _release_downloaded = Signal(bytes)
    _release_fetch_failed = Signal()

    def __init__(self, helper, *args):
        super().__init__(*args)
        self.setupUi(self)

        self.tabName = "Service"
        self._helper = helper

        # Standalone link context for bootloader operations
        self._link_context = LinkContext()

        # Firmware state — separate per source so tab switching doesn't mix them.
        # Releases are cached by their dropdown name so previously-downloaded
        # ones stay ready when the user navigates back to them.
        self._downloaded_releases: dict[str, list[FirmwareImage]] = {}
        self._file_images: list[FirmwareImage] = []
        self._loaded_file_path: str | None = None
        self._pending_download_name: str | None = None
        self._releases_loading: bool = True
        self._releases_load_failed: bool = False
        self._download_in_progress: bool = False
        self._releases: dict[str, str] = {}
        self._platform_widget_names: dict[str, list[str]] = {}
        self._platform_filter_checkboxes: list[QtWidgets.QRadioButton] = []
        self._flash_target_checkboxes: list[QtWidgets.QCheckBox] = []
        self._recovery_target_checkboxes: list[QtWidgets.QCheckBox] = []
        self._flash_task: asyncio.Task | None = None
        self._scan_task: asyncio.Task | None = None

        # Wire up UI signals
        self.scanButton.clicked.connect(self._scan_clicked)
        self.imagePathBrowseButton.clicked.connect(self._browse_file)
        self.flashWarmButton.clicked.connect(self._flash_warm_clicked)
        self.flashColdButton.clicked.connect(self._flash_cold_clicked)
        self.sourceTab.currentChanged.connect(self._on_source_tab_changed)
        self.uriCombo.currentTextChanged.connect(lambda _: self._update_flash_buttons())
        self.downloadButton.clicked.connect(self._download_clicked)
        self.firmwareDropdown.currentTextChanged.connect(
            lambda _: self._populate_target_checkboxes()
        )
        self.imagePathLine.textChanged.connect(
            lambda _: self._populate_target_checkboxes()
        )

        # Progress signal bridge (callback runs in Rust thread)
        self._progress_signal.connect(self._update_progress_ui)

        # Release fetching / downloading
        self._release_firmwares_found.connect(self._populate_firmware_dropdown)
        self._release_fetch_done.connect(self._on_release_fetch_done)
        self._release_fetch_failed.connect(self._on_release_fetch_failed)
        self._release_downloaded.connect(self._on_release_downloaded)
        self.firmwareDropdown.currentTextChanged.connect(
            lambda _: self._update_download_status()
        )

        # Platform images and radio buttons
        self._set_image(self.image_1, os.path.join(ICON_PATH, "bolt.webp"))
        self._set_image(self.image_2, os.path.join(ICON_PATH, "cf21.webp"))
        self._set_image(self.image_3, os.path.join(ICON_PATH, "bl.webp"))
        self._set_image(self.image_4, os.path.join(ICON_PATH, "flapper.webp"))
        self._set_image(self.image_5, os.path.join(ICON_PATH, "tag.webp"))
        for platform in ["bolt", "cf2", "cf21bl", "flapper", "tag"]:
            radio_button = QtWidgets.QRadioButton(platform)
            radio_button.setFixedWidth(100)
            radio_button.toggled.connect(self._update_firmware_dropdown)
            radio_button.toggled.connect(self._update_flash_buttons)
            self._platform_filter_checkboxes.append(radio_button)
            # Insert before the trailing spacer
            self.filterLayout.insertWidget(self.filterLayout.count() - 1, radio_button)

        self.firmwareDropdown.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents
        )

        # Pre-fill URI from main window if connected, else from config
        prefill_uri = None
        main_ui = self._helper.mainUI
        if main_ui is not None and main_ui.cf is not None:
            prefill_uri = main_ui._connectivity_manager.get_interface()
            if prefill_uri and " - " in prefill_uri:
                prefill_uri = prefill_uri.split(" - ")[0]
        if not prefill_uri:
            try:
                prefill_uri = Config().get("link_uri")
            except KeyError:
                pass
        if prefill_uri:
            self.uriCombo.addItem(prefill_uri)
            self.uriCombo.setCurrentText(prefill_uri)

        # Fetch releases in a thread (not async, to avoid event loop
        # contention when the main window is connected)
        self._update_download_status()
        threading.Thread(target=self._fetch_releases_thread, daemon=True).start()

    def _get_scan_address(self) -> int:
        """Get the scan address from the main window or config."""
        main_ui = self._helper.mainUI
        if main_ui is not None:
            return main_ui.address.value()
        try:
            link_uri = Config().get("link_uri")
            if link_uri.startswith("radio://"):
                parts = link_uri.split("/")
                if len(parts) == 6:
                    return int(parts[-1], 16)
        except (KeyError, ValueError):
            pass
        return 0xE7E7E7E7E7

    # --- Image loading ---

    def _set_image(self, image_label, image_path):
        IMAGE_SIZE = 100
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            logger.warning(f"Failed to load image: {image_path}")
            image_label.setText("Missing image")
        else:
            scaled = pixmap.scaled(
                IMAGE_SIZE,
                IMAGE_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            image_label.setPixmap(scaled)

    # --- Scanning ---

    def _scan_clicked(self):
        if self._scan_task is not None:
            self._scan_task.cancel()
        self._scan_task = create_task(self._async_scan())

    async def _async_scan(self):
        self.scanButton.setEnabled(False)
        self.scanButton.setText("Scanning...")
        try:
            # Disconnect main window if connected — can't share the radio
            main_ui = self._helper.mainUI
            if main_ui is not None and main_ui.cf is not None:
                await main_ui._async_disconnect()

            address = self._get_scan_address()
            address_bytes = list(address.to_bytes(5, byteorder="big"))
            uris = await self._link_context.scan(address=address_bytes)

            selected = self.uriCombo.currentText()
            self.uriCombo.clear()
            for uri in uris:
                self.uriCombo.addItem(uri)

            if selected and selected in uris:
                self.uriCombo.setCurrentText(selected)
            elif len(uris) == 1:
                self.uriCombo.setCurrentIndex(0)
        finally:
            self.scanButton.setEnabled(True)
            self.scanButton.setText("Scan")
            self._scan_task = None
            self._update_flash_buttons()

    # --- Release fetching ---

    def _fetch_releases_thread(self):
        url = RELEASE_URL + "?per_page=50"
        while url:
            try:
                with urlopen(url, timeout=15) as resp:
                    body = resp.read()
                    data = json.loads(body)
                    url = self._get_next_page_url(resp)
            except (URLError, OSError, TimeoutError, json.JSONDecodeError):
                logger.warning("Failed to fetch firmware releases", exc_info=True)
                self._release_fetch_failed.emit()
                self._release_fetch_done.emit()
                return

            release_list = []
            for release in data:
                release_name = release.get("name")
                if release_name:
                    releases = [release_name]
                    for download in release.get("assets", []):
                        releases.append(
                            (download["name"], download["browser_download_url"])
                        )
                    release_list.append(releases)

            if release_list:
                self._release_firmwares_found.emit(release_list)

        self._release_fetch_done.emit()

    @staticmethod
    def _get_next_page_url(resp) -> str | None:
        link_header = resp.getheader("Link")
        if not link_header:
            return None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None

    def _on_release_fetch_failed(self):
        self._releases_load_failed = True
        self._update_download_status()

    def _on_release_fetch_done(self):
        self._releases_loading = False
        self._update_download_status()

    def _update_download_status(self):
        """Reflect the actual state of the dropdown selection in the status
        label next to the download button."""
        if self._download_in_progress:
            self.downloadStatus.setText("Downloading...")
            return
        if self._releases_load_failed:
            self.downloadStatus.setText("Failed to load releases")
            return
        if self._releases_loading:
            self.downloadStatus.setText("Loading releases...")
            return
        name = self.firmwareDropdown.currentText()
        if name and name in self._downloaded_releases:
            self.downloadStatus.setText("✓ Downloaded")
        else:
            self.downloadStatus.setText("")

    def _populate_firmware_dropdown(self, releases):
        existing_platforms = {b.text() for b in self._platform_filter_checkboxes}

        new_platforms = set()
        for release in releases:
            release_name = release[0]
            downloads = release[1:]
            downloads.sort(key=self._download_sorter)

            for download in downloads:
                download_name, download_link = download
                platform = self._extract_platform(download_name)
                if platform:
                    widget_name = "%s - %s" % (release_name, download_name)
                    if platform not in self._platform_widget_names:
                        self._platform_widget_names[platform] = []
                    self._platform_widget_names[platform].append(widget_name)
                    self._releases[widget_name] = download_link
                    new_platforms.add(platform)

        for platform in sorted(new_platforms - existing_platforms, reverse=True):
            radio_button = QtWidgets.QRadioButton(platform)
            radio_button.setFixedWidth(100)
            radio_button.toggled.connect(self._update_firmware_dropdown)
            radio_button.toggled.connect(self._update_flash_buttons)
            self._platform_filter_checkboxes.append(radio_button)
            self.filterLayout.insertWidget(0, radio_button)

        self._update_firmware_dropdown(True)

    def _update_firmware_dropdown(self, active):
        if active:
            platform = None
            for button in self._platform_filter_checkboxes:
                if button.isChecked():
                    platform = button.text()

            if platform and platform in self._platform_widget_names:
                self.firmwareDropdown.clear()
                for widget_name in self._platform_widget_names[platform]:
                    self.firmwareDropdown.addItem(widget_name)

    @staticmethod
    def _extract_platform(download_name: str) -> str | None:
        found = re.search(r"firmware-(\w+)-", download_name)
        if found and len(found.groups()) == 1:
            return found.group(1)
        return None

    @staticmethod
    def _download_sorter(element):
        name = element[0]
        return ("0" + name) if "cf2" in name else ("1" + name)

    # --- File browsing ---

    @Slot()
    def _browse_file(self):
        names = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Release file to flash",
            self._helper.current_folder,
            "*.zip",
        )
        if names[0] == "":
            return

        filename = names[0]
        self._helper.current_folder = os.path.dirname(filename)

        if filename.endswith(".zip"):
            self.imagePathLine.setText(filename)
            self._load_zip_from_path(filename)
        else:
            QtWidgets.QMessageBox.warning(
                self, "Invalid file", "Wrong file extension. Must be .zip."
            )

    # --- Firmware loading ---

    @property
    def _firmware_images(self) -> list[FirmwareImage]:
        if self.sourceTab.currentWidget() == self.tabFromFile:
            return self._file_images
        return self._downloaded_releases.get(self.firmwareDropdown.currentText(), [])

    def _on_source_tab_changed(self):
        self._populate_target_checkboxes()

    def _load_zip_from_path(self, path: str):
        try:
            with open(path, "rb") as f:
                data = f.read()
            _, images = parse_firmware_zip(data)
        except (OSError, RuntimeError) as e:
            logger.error("Failed to parse firmware zip: %s", e)
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to parse firmware zip:\n{e}"
            )
            return
        self._file_images = images
        self._loaded_file_path = path
        self._populate_target_checkboxes()

    def _is_firmware_ready(self) -> bool:
        """Return True only if the firmware shown in the active tab matches
        what's actually loaded — i.e. the dropdown selection has been
        downloaded, or the file path has been loaded."""
        if self.sourceTab.currentWidget() == self.tabFromFile:
            return (
                self._loaded_file_path is not None
                and self.imagePathLine.text() == self._loaded_file_path
                and bool(self._file_images)
            )
        platform_selected = any(b.isChecked() for b in self._platform_filter_checkboxes)
        name = self.firmwareDropdown.currentText()
        return (
            platform_selected
            and bool(name)
            and bool(self._downloaded_releases.get(name))
        )

    def _populate_target_checkboxes(self):
        # Clear existing checkboxes
        self._clear_target_checkboxes(
            self.flashTargetsLayout, self._flash_target_checkboxes
        )
        self._clear_target_checkboxes(
            self.recoveryTargetsLayout, self._recovery_target_checkboxes
        )

        if not self._is_firmware_ready():
            self.flashTargetsPlaceholder.setText(
                "Select firmware to see available targets"
            )
            self.flashTargetsPlaceholder.show()
            self.recoveryTargetsPlaceholder.setText(
                "Select firmware to see available targets"
            )
            self.recoveryTargetsPlaceholder.show()
            self._update_flash_buttons()
            return

        # Hide placeholder labels
        self.flashTargetsPlaceholder.hide()
        self.recoveryTargetsPlaceholder.hide()

        for image in self._firmware_images:
            key = image.target_key()
            target_name = image.target.target_name
            label = f"{target_name} ({image.fw_type})"

            # Flash tab: show all targets
            cb_flash = QtWidgets.QCheckBox(label)
            cb_flash.setChecked(True)
            cb_flash.setProperty("target_key", key)
            cb_flash.toggled.connect(self._update_flash_buttons)
            self._flash_target_checkboxes.append(cb_flash)
            self.flashTargetsLayout.addWidget(cb_flash)

            # Recovery tab: only STM32 and nRF51
            if target_name in ("stm32", "nrf51"):
                cb_recovery = QtWidgets.QCheckBox(label)
                cb_recovery.setChecked(True)
                cb_recovery.setProperty("target_key", key)
                cb_recovery.toggled.connect(self._update_flash_buttons)
                self._recovery_target_checkboxes.append(cb_recovery)
                self.recoveryTargetsLayout.addWidget(cb_recovery)

        if not self._recovery_target_checkboxes:
            self.recoveryTargetsPlaceholder.setText(
                "No STM32/nRF51 targets in this firmware"
            )
            self.recoveryTargetsPlaceholder.show()

        self._update_flash_buttons()

    def _clear_target_checkboxes(self, layout, checkbox_list):
        for cb in checkbox_list:
            layout.removeWidget(cb)
            cb.deleteLater()
        checkbox_list.clear()

    # --- Release download ---

    def _download_clicked(self):
        requested = self.firmwareDropdown.currentText()
        if requested not in self._releases:
            return
        self._pending_download_name = requested
        self._download_in_progress = True
        self.downloadButton.setEnabled(False)
        self._update_download_status()
        threading.Thread(
            target=self._download_release_thread,
            args=(self._releases[requested],),
            daemon=True,
        ).start()

    def _download_release_thread(self, url: str):
        try:
            with urlopen(url) as response:
                data = response.read()
            self._release_downloaded.emit(data)
        except URLError:
            logger.warning("Failed to download release from %s", url)

    def _on_release_downloaded(self, data: bytes):
        self.downloadButton.setEnabled(True)
        self._download_in_progress = False
        name = self._pending_download_name
        self._pending_download_name = None
        if name is None:
            self._update_download_status()
            return
        try:
            _, images = parse_firmware_zip(data)
        except RuntimeError as e:
            logger.error("Failed to parse firmware zip: %s", e)
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to parse firmware zip:\n{e}"
            )
            self._update_download_status()
            return
        self._downloaded_releases[name] = images
        self._update_download_status()
        self._populate_target_checkboxes()

    # --- Flash button state ---

    def _update_flash_buttons(self):
        has_uri = bool(self.uriCombo.currentText().strip())
        is_flashing = self._flash_task is not None

        has_flash_targets = any(cb.isChecked() for cb in self._flash_target_checkboxes)
        has_recovery_targets = any(
            cb.isChecked() for cb in self._recovery_target_checkboxes
        )

        self.flashWarmButton.setEnabled(
            has_uri and has_flash_targets and not is_flashing
        )
        self.flashColdButton.setEnabled(has_recovery_targets and not is_flashing)

    def _get_selected_keys(self, checkbox_list) -> list[str]:
        return [cb.property("target_key") for cb in checkbox_list if cb.isChecked()]

    # --- Flash actions ---

    def _flash_warm_clicked(self):
        uri = self.uriCombo.currentText().strip()
        if not uri:
            return
        selected_keys = self._get_selected_keys(self._flash_target_checkboxes)
        images = filter_images(self._firmware_images, selected_keys)
        self._start_flash(BootMode.warm(uri), uri, images)

    def _flash_cold_clicked(self):
        selected_keys = self._get_selected_keys(self._recovery_target_checkboxes)
        images = filter_images(self._firmware_images, selected_keys)
        self._start_flash(BootMode.cold(), None, images)

    def _start_flash(
        self,
        boot_mode: BootMode,
        uri: str | None,
        images: list[FirmwareImage],
    ):
        if self._flash_task is not None or not images:
            return

        self._flash_task = create_task(self._do_flash(boot_mode, uri, images))
        self._set_flashing_ui(True)

    async def _do_flash(
        self,
        boot_mode: BootMode,
        uri: str | None,
        images: list[FirmwareImage],
    ):
        # Request main window to disconnect if connected
        main_ui = self._helper.mainUI
        if main_ui is not None and main_ui.cf is not None:
            logger.info("Requesting main window disconnect for flashing")
            await main_ui._async_disconnect()

        self.stageLabel.setText("Status: <b>Starting flash...</b>")
        self.progressBar.setValue(0)
        try:
            await flash(
                self._link_context,
                boot_mode=boot_mode,
                uri=uri,
                images=images,
                progress=self._on_progress,
            )
            self._on_flash_success()
        except asyncio.CancelledError:
            self.stageLabel.setText("Status: <b>Cancelled</b>")
            raise
        except Exception as e:
            logger.error("Flash failed: %s", e)
            self._on_flash_error(str(e))
        finally:
            self._flash_task = None
            self._set_flashing_ui(False)

    # --- Progress ---

    def _on_progress(self, event: dict):
        self._progress_signal.emit(event)

    @Slot(dict)
    def _update_progress_ui(self, event: dict):
        event_type = event.get("type", "")

        if event_type == "entering_bootloader":
            self.stageLabel.setText("Status: <b>Entering bootloader...</b>")
        elif event_type == "bootloader_connected":
            self.stageLabel.setText("Status: <b>Connected to bootloader</b>")
        elif event_type == "flashing_target":
            target = event.get("target", "")
            written = event.get("bytes_written", 0)
            total = event.get("total_bytes", 1)
            pct = int(written / total * 100) if total > 0 else 0
            self.stageLabel.setText(f"Status: <b>Flashing {target}...</b>")
            self.progressBar.setValue(pct)
        elif event_type == "flash_complete":
            target = event.get("target", "")
            self.stageLabel.setText(f"Status: <b>Flash complete for {target}</b>")
            self.progressBar.setValue(100)
        elif event_type == "resetting_to_firmware":
            self.stageLabel.setText("Status: <b>Resetting to firmware...</b>")
        elif event_type == "waiting_for_reboot":
            secs = event.get("estimated_seconds", 0)
            self.stageLabel.setText(
                f"Status: <b>Waiting for reboot (~{secs:.0f}s)...</b>"
            )
        elif event_type == "connecting_for_deck_phase":
            self.stageLabel.setText("Status: <b>Reconnecting for deck updates...</b>")
        elif event_type == "discovering_decks":
            found = event.get("found", [])
            self.stageLabel.setText(
                f"Status: <b>Discovering decks ({len(found)} found)...</b>"
            )
        elif event_type == "flashing_deck":
            name = event.get("name", "")
            written = event.get("bytes_written", 0)
            total = event.get("total_bytes", 1)
            pct = int(written / total * 100) if total > 0 else 0
            self.stageLabel.setText(f"Status: <b>Flashing deck {name}...</b>")
            self.progressBar.setValue(pct)
        elif event_type == "deck_flash_complete":
            name = event.get("name", "")
            self.stageLabel.setText(f"Status: <b>Deck {name} flash complete</b>")
        elif event_type == "complete":
            self.stageLabel.setText("Status: <b>Flash complete!</b>")
            self.progressBar.setValue(100)

    # --- Flash completion ---

    def _on_flash_success(self):
        self.stageLabel.setText("Status: <b>Flash complete!</b>")
        self.progressBar.setValue(100)

    def _on_flash_error(self, error: str):
        self.stageLabel.setText(f"Status: <b>Flash failed: {error}</b>")

    def _set_flashing_ui(self, flashing: bool):
        self.flashWarmButton.setEnabled(not flashing)
        self.flashColdButton.setEnabled(not flashing)
        self.sourceTab.setEnabled(not flashing)
        self.bootModeTab.tabBar().setEnabled(not flashing)
        self.scanButton.setEnabled(not flashing)
        if not flashing:
            self._update_flash_buttons()

    # --- Cleanup ---

    def closeEvent(self, event):
        if self._flash_task is not None:
            self._flash_task.cancel()
        if self._scan_task is not None:
            self._scan_task.cancel()
