import pytest
import cfclient
cfclient.config_path  = "test/cache"

from PyQt6 import QtCore
from PyQt6.QtWidgets import QTabWidget, QWidget, QTreeWidget, QMenuBar, QMenu
import cfclient
import shutil
import os


@pytest.fixture(autouse=True)
def main_window():
    cache_dir = cfclient.config_path
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
    os.makedirs(cache_dir)  # Re-create the empty cache directory
    from cfclient.ui.main import MainUI #Need to import here to avoid setting up the cache at the wrong place
    yield MainUI()
    


def test_main_ui_window(qtbot, main_window):
    # Create an instance of the main UI window

    qtbot.addWidget(main_window)

    # Show the main window and perform assertions
    main_window.show()
    assert main_window.isVisible()

    # Close the window after a delay to end the test
    qtbot.wait(1000)
    main_window.close()
    assert not main_window.isVisible()


def test_tab_visibility(qtbot,main_window):
    def test_tab(name):
        tab_name = name
        tab_action_item = next((a for a in main_window.tabs_menu_item.actions() if a.text() == tab_name), None)
        assert tab_action_item is not None, f"Tab action for '{tab_name}' not found"

        assert not tab_action_item.isChecked()
        tab_action_item.triggered.emit(True)
        assert tab_action_item.isChecked()
    # Create an instance of the main UI window
    qtbot.addWidget(main_window)

    main_window.show()
    tab_list = ["Console","Parameters","Loco Positioning","Lighthouse Positioning","Crtp sniffer","Log TOC", "LED","Log Blocks","Plotter", "Tuning", "Log Client"]
    for tab_name in tab_list:
        test_tab(tab_name)
        qtbot.wait(1000)