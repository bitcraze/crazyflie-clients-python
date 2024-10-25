from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
import pytest
import  cfclient.gui
from cfclient.ui.main import MainUI
@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])

def test_main_ui_window(qtbot, app):
    # Create an instance of the main UI window
    main_window = MainUI()
    qtbot.addWidget(main_window)

    # Show the main window and perform assertions
    main_window.show()
    assert main_window.isVisible()

    # Close the window after a delay to end the test
    qtbot.wait(1000)
    main_window.close()
    assert not main_window.isVisible()