import logging

import cfclient
from PyQt5 import Qt, QtWidgets, uic
from PyQt5.QtCore import *  # noqa
from PyQt5.QtWidgets import *  # noqa
from PyQt5.Qt import *  # noqa

from cflib.crazyflie.log import LogConfig

__author__ = 'Bitcraze AB'
__all__ = ['LogConfigDialogue']

logger = logging.getLogger(__name__)

(logconfig_widget_class, connect_widget_base_class) = (
    uic.loadUiType(cfclient.module_path + '/ui/dialogs/testdialogue.ui'))

NAME_FIELD = 0
ID_FIELD = 1
PTYPE_FIELD = 2
CTYPE_FIELD = 3


class TestDialogue(QtWidgets.QWidget, logconfig_widget_class):

    def __init__(self, helper, *args):
        super(TestDialogue, self).__init__(*args)
        self.setupUi(self)
        self.helper = helper

        self.logConfTree.setHeaderLabels(['Topic', 'Log configuration'])
        self.logTree.setHeaderLabels(['Name', 'ID', 'Unpack', 'Storage'])
        self.varTree.setHeaderLabels(['Name', 'ID', 'Unpack', 'Storage'])
        
        # used to lookup log configs when certain config is requested
        # the configs can be indexed by the name of the log-cofig
        self._log_configs = {}

        """
        test_item = QtWidgets.QTreeWidgetItem()
        test_item.setData(0, Qt.DisplayRole, 'hey')
        
        for i in ['hey', 'yo', 'test']:
            item = QtWidgets.QTreeWidgetItem()
            item.setData(0, Qt.DisplayRole, i)
            test_item.addChild(item)
        """

        self.logConfTree.itemClicked.connect(self.onItemClicked)

    @pyqtSlot(QtWidgets.QTreeWidgetItem, int)
    def onItemClicked(self, it, col):
        log_conf_name = it.text(col)
        print(it, col, log_conf_name)
        self._display_selected_log(log_conf_name)


    def showEvent(self, event):
        self._load_saved_configs()

    def _load_saved_configs(self):
        """ read saved log-configs and display them on
            the left category-tree """
        config = None
        config = self.helper.logConfigReader.getLogConfigs()
        
        if (config is None):
            logger.warning("Could not load config")
        else:
            for conf in config:
                # add the config to the dict
                self._log_configs[conf.name] = conf

                conf_item = QtWidgets.QTreeWidgetItem()
                conf_item.setData(0, Qt.DisplayRole, conf.name)
                self.logConfTree.addTopLevelItem(conf_item)
    
        
    def load_config(self):


        """
        cText = self.configNameCombo.currentText()
        config = None
        for d in self.helper.logConfigReader.getLogConfigs():
            if (d.name == cText):
                config = d
        if (config is None):
            logger.warning("Could not load config")
        else:
            self.resetTrees()
            self.loggingPeriod.setText("%d" % config.period_in_ms)
            self.period = config.period_in_ms
            for v in config.variables:
                if (v.is_toc_variable()):
                    parts = v.name.split(".")
                    varParent = parts[0]
                    varName = parts[1]
                    if self.moveNodeByName(
                            self.logTree, self.varTree, varParent,
                            varName) is False:
                        logger.warning("Could not find node %s.%s!!",
                                       varParent, varName)
                else:
                    logger.warning("Error: Mem vars not supported!")
        """
            
    def _display_selected_log(self, log_config):
        

        toc = self.helper.cf.log.toc
        print(type(toc))
        for group, log_tocs in toc.toc.items():
            print(type(group))
            print(type(log_tocs))

            string = 'Group: %s   => ' % group

            for name, tocs in log_tocs.items():
                string += '%s: ' % name
                string += 'ident: %s ' % tocs.ident
                string += 'pytype: %s ' % tocs.pytype
                string += 'ctype: %s ' % tocs.ctype
                
            string += '\n'
            print(string)



        # get requested config by name 
        config = self._log_configs[log_config]
        self.loadConfig(log_config)
        print(config.name)

        for var in config.variables:
            print(var)


        """
        self.logTree.clear()

        toc = self.helper.cf.log.toc

        for group, log_tocs in toc.toc.items():

            group_item = QtWidgets.QTreeWidgetItem()
            group_item.setData(0, Qt.DisplayRole, group)

            for name, tocs in log_tocs.items():

                child_item = QtWidgets.QTreeWidgetItem()
                child_item.setData(1, Qt.DisplayRole, tocs.ident)
                child_item.setData(2, Qt.DisplayRole, tocs.pytype)
                child_item.setData(3, Qt.DisplayRole, tocs.ctype)
                group_item.addChild(child_item)


            self.logTree.addTopLevelItem(group_item)
            #self.logTree.expandItem(group_item)
                
        
        for group in list(toc.toc.keys()):
            groupItem = QtWidgets.QTreeWidgetItem()
            groupItem.setData(NAME_FIELD, Qt.DisplayRole, group)
            for param in list(toc.toc[group].keys()):
                item = QtWidgets.QTreeWidgetItem()
                item.setData(NAME_FIELD, Qt.DisplayRole, param)
                item.setData(ID_FIELD, Qt.DisplayRole,
                             toc.toc[group][param].ident)
                item.setData(PTYPE_FIELD, Qt.DisplayRole,
                             toc.toc[group][param].pytype)
                item.setData(CTYPE_FIELD, Qt.DisplayRole,
                             toc.toc[group][param].ctype)
                groupItem.addChild(item)
        """

    def resetTrees(self):
        self.varTree.clear()
        #self.updateToc()        

    def moveNode(self, source, target):
        self.moveNodeItem(source, target, source.currentItem())

    def moveNodeByName(self, source, target, parentName, itemName):
        parents = source.findItems(parentName, Qt.MatchExactly, NAME_FIELD)
        node = None
        if (len(parents) > 0):
            parent = parents[0]
            for n in range(parent.childCount()):
                if (parent.child(n).text(NAME_FIELD) == itemName):
                    node = parent.child(n)
                    break
        if (node is not None):
            self.moveNodeItem(source, target, node)
            return True
        return False

    def loadConfig(self, log_config):
        config = None
        for d in self.helper.logConfigReader.getLogConfigs():
            if (d.name == log_config):
                config = d
        if (config is None):
            logger.warning("Could not load config")
        else:
            self.resetTrees()
            ##self.loggingPeriod.setText("%d" % config.period_in_ms)
            self.period = config.period_in_ms
            for v in config.variables:
                if (v.is_toc_variable()):
                    parts = v.name.split(".")
                    varParent = parts[0]
                    varName = parts[1]
                    if self.moveNodeByName(
                            self.logTree, self.varTree, varParent,
                            varName) is False:
                        logger.warning("Could not find node %s.%s!!",
                                       varParent, varName)
                else:
                    logger.warning("Error: Mem vars not supported!")