import pytest
import cfclient
cfclient.config_path  = "./config"
import cfclient
import shutil
import os
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread

# Configure logging to display info messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Print a message before each test starts
def pytest_runtest_setup(item):
    print(f"\nStarting test: {item.name}")

# Print a message after each test finishes
def pytest_runtest_teardown(item, nextitem):
    print(f"Finished test: {item.name}")

def pytest_addoption(parser):
    parser.addoption(
        "--local", action="store_true", default=False, help="Run in local mode i.e show UI for a bit longer"
    )

@pytest.fixture
def local(request):
    return request.config.getoption("--local")

@pytest.fixture(autouse=True)
def main_window():
    cache_dir = cfclient.config_path
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
    os.makedirs(cache_dir)  # Re-create the empty cache directory
    from cfclient.ui.main import MainUI #Need to import here to avoid setting up the cache at the wrong place
    yield MainUI()
