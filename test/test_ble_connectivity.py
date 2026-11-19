"""Qt logic tests: no Bluetooth or native window is opened."""
import os
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton, QSpinBox
from cfclient.ui.connectivity_manager import ConnectivityManager
from cfclient.ui.main import ScannerThread


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_keeps_ble_uri_and_button_state(self):
        manager = ConnectivityManager()
        combo, connect, scan, address = QComboBox(), QPushButton(), QPushButton(), QSpinBox()
        # Custom address widget has extra methods, not used by this test.
        manager.register_ui_elements(manager.UiElementsContainer(combo, address, connect, scan))
        uri = 'ble://00000000-0000-4000-8000-000000000001?name=Crazyflie-ABCDEF'
        manager.set_interfaces([uri, 'radio://0/80/2M'], 0)
        self.assertEqual(manager.get_interface(), uri)
        self.assertTrue(connect.isEnabled())
        combo.setCurrentIndex(0)
        self.assertIsNone(manager.get_interface())
        self.assertFalse(connect.isEnabled())
        combo.setCurrentIndex(2)
        self.assertEqual(manager.get_interface(), 'radio://0/80/2M')
        self.assertTrue(connect.isEnabled())

    def test_ble_scan_does_not_scan_radio(self):
        scanner = ScannerThread(ble_only=True)
        with (
            patch('cflib.crtp.bledriver.BleDriver.scan_interface', return_value=[]) as ble,
            patch('cflib.crtp.scan_interfaces') as all_drivers,
        ):
            scanner.scan(None)
        ble.assert_called_once()
        all_drivers.assert_not_called()
