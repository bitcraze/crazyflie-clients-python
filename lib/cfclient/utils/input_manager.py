import logging
import sys
from .singleton import Singleton

logger = logging.getLogger(__name__)

@Singleton
class InputManager():
    input_dir = sys.path[1] + "/input"