import sys
import json
import logging
import glob
import os
import copy

from .singleton import Singleton
from cflib.utils.callbacks import Caller

logger = logging.getLogger(__name__)

@Singleton
class ConfigManager():
    confNeedsReload = Caller()
    configs_dir = sys.path[1] + "/input"

    """ Singleton class for managing input processing """
    def __init__(self):
        self.listOfConfigs = []
        self.loadInputConfigFiles()

    def getConfig(self, config_name):
        """Get the configuration for an input device."""
        try:
            idx = self.listOfConfigs.index(config_name)
            return self.inputConfig[idx]
        except:
            return None

    def getListOfConfigs(self):
        """Get a list of all the input devices."""
        return self.listOfConfigs

    def loadInputConfigFiles(self):
        try:
            configs = [os.path.basename(f) for f in glob.glob(self.configs_dir + "/[A-Za-z]*.json")]
            self.inputConfig = []
            self.listOfConfigs = []
            for conf in configs:            
                logger.info("Parsing [%s]", conf)
                json_data = open(self.configs_dir + "/%s" % conf)                
                data = json.load(json_data)
                newInputDevice = {}
                for a in data["inputconfig"]["inputdevice"]["axis"]:
                    axis = {}
                    axis["scale"] = a["scale"]
                    axis["type"] = a["type"]
                    axis["key"] = a["key"]
                    axis["name"] = a["name"]
                    try:
                      ids = a["ids"]
                    except:
                      ids = [a["id"]]
                    for id in ids:
                      locaxis = copy.deepcopy(axis)
                      if "ids" in a:
                        if id == a["ids"][0]:
                          locaxis["scale"] = locaxis["scale"] * -1
                      locaxis["id"] = id
                      index = "%s-%d" % (a["type"], id) # 'type'-'id' defines unique index for axis    
                      newInputDevice[index] = locaxis
                self.inputConfig.append(newInputDevice)
                json_data.close()
                self.listOfConfigs.append(conf[:-5])
        except Exception as e:
            logger.warning("Exception while parsing inputconfig file: %s ", e)