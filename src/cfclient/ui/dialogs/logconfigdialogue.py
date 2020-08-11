#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
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
This dialogue is used to configure different log configurations that is used to
enable logging of data from the Crazyflie. These can then be used in different
views in the UI.
"""

import logging
import struct

import cfclient
from cfclient.utils.ui import UiUtils
from PyQt5 import QtWidgets, uic, QtGui
from PyQt5.QtCore import Qt, QTimer

from cflib.crazyflie.log import LogConfig

__author__ = 'Bitcraze AB'
__all__ = ['LogConfigDialogue']

logger = logging.getLogger(__name__)

(logconfig_widget_class, connect_widget_base_class) = (
    uic.loadUiType(cfclient.module_path + '/ui/dialogs/logconfigdialogue.ui'))

NAME_FIELD = 0
ID_FIELD = 1
TYPE_FIELD = 2
SIZE_FIELD = 3
MAX_LOG_SIZE = 26


class LogConfigDialogue(QtWidgets.QWidget, logconfig_widget_class):

    def __init__(self, helper, *args):
        super(LogConfigDialogue, self).__init__(*args)
        self.setupUi(self)
        self.helper = helper

        self.logTree.setHeaderLabels(['Name', 'ID', 'Type', 'Size'])
        self.varTree.setHeaderLabels(['Name', 'ID', 'Type', 'Size'])
        self.categoryTree.setHeaderLabels(['Categories'])

        self.logTree.setSortingEnabled(True)
        self.varTree.setSortingEnabled(True)

        # Item-click callbacks.
        self.addButton.clicked.connect(lambda: self.moveNode(self.logTree,
                                                             self.varTree))
        self.removeButton.clicked.connect(lambda: self.moveNode(self.varTree,
                                                                self.logTree))
        self.saveButton.clicked.connect(self.saveConfig)

        self.categoryTree.itemSelectionChanged.connect(self._item_selected)
        self.categoryTree.itemPressed.connect(self._on_item_press)
        self.categoryTree.itemChanged.connect(self._config_changed)

        # Add/remove item on doubleclick.
        self.logTree.itemDoubleClicked.connect(self.itemDoubleClicked)
        self.varTree.itemDoubleClicked.connect(lambda: self.moveNode(
                                            self.varTree, self.logTree))
        self.loggingPeriod.textChanged.connect(self.periodChanged)

        self.currentSize = 0
        self.packetSize.setMaximum(100)
        self.packetSize.setValue(0)
        self.period = 0

        # Used when renaming a config/category
        self._last_pressed_item = None

        # set icons
        save_icon, delete_icon = self.helper.logConfigReader.get_icons()
        self.createCategoryBtn.setIcon(save_icon)
        self.createConfigBtn.setIcon(save_icon)
        self.deleteBtn.setIcon(delete_icon)

        # bind buttons
        self.createCategoryBtn.clicked.connect(self._create_category)
        self.createConfigBtn.clicked.connect(self._create_config)
        self.deleteBtn.clicked.connect(self._delete_config)

        # set tooltips
        self.createCategoryBtn.setToolTip('Create a new category')
        self.createConfigBtn.setToolTip('Create a new log-config')
        self.deleteBtn.setToolTip('Delete category')

        # enable right-click context-menu
        self.categoryTree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.categoryTree.customContextMenuRequested.connect(
                                                    self.menuContextTree)

        # keyboard shortcuts
        shortcut_delete = QtWidgets.QShortcut(QtGui.QKeySequence("Delete"),
                                              self)
        shortcut_delete.activated.connect(self._delete_config)

        shortcut_f2 = QtWidgets.QShortcut(QtGui.QKeySequence("F2"), self)
        shortcut_f2.activated.connect(self._edit_name)

        self._config_saved_timer = QTimer()
        self._config_saved_timer.timeout.connect(self._config_saved_status)

        self.closeOnSave.setChecked(True)

    def itemDoubleClicked(self):
        if self.categoryTree.selectedItems():
            self.moveNode(self.logTree, self.varTree)

    def _config_saved_status(self):
        self.statusText.setText('')
        self._config_saved_timer.stop()

    def _on_item_press(self, item):
        self._last_pressed_item = item, item.text(0)

    def _create_config(self):
        """ Creates a new log-configuration in the chosen
            category. If no category is selected, the
            configuration is stored in the 'Default' category.
        """
        items = self.categoryTree.selectedItems()

        if items:
            config = items[0]
            parent = config.parent()
            if parent:
                category = parent.text(0)
            else:
                category = config.text(0)

            conf_name = self.helper.logConfigReader.create_empty_log_conf(
                                                category)
            self._reload()
            # Load the newly created log-config.
            self._select_item(conf_name, category)
            self._edit_name()

    def _create_category(self):
        """ Creates a new category and enables editing the name.  """
        category_name = self.helper.logConfigReader.create_category()
        self._load_saved_configs()
        self.sortTrees()
        self._select_category(category_name)
        self._edit_name()

    def _delete_config(self):

        """ Deletes a category or a configuration
            depending on if the item has a parent or not.
        """

        items = self.categoryTree.selectedItems()
        if items:
            config = items[0]
            parent = config.parent()

            if parent:
                # Delete a configuration in the given category.
                category = parent.text(0)
                self.helper.logConfigReader.delete_config(config.text(0),
                                                          category)
                self._reload()
            else:
                # Delete a category and all its log-configurations
                category = config.text(0)
                if category != 'Default':
                    self.helper.logConfigReader.delete_category(category)
                    self._reload()

    def _config_changed(self, config):
        """ Changes the name for a log-configuration or a category.
            This is a callback function that gets called when an item
            is changed.
        """
        item, old_name = self._last_pressed_item

        parent = config.parent()
        if parent:
            # Change name for a log-config, inside of the category.
            new_conf_name = item.text(0)
            category = parent.text(0)
            self.helper.logConfigReader.change_name_config(old_name,
                                                           new_conf_name,
                                                           category)
        else:
            # Change name for the category.
            category = config.text(0)
            self.helper.logConfigReader.change_name_category(old_name,
                                                             category)

    def _edit_name(self):
        """ Enables editing the clicked item.
            When the edit is saved, a callback is fired.
        """
        items = self.categoryTree.selectedItems()
        if items:
            item_clicked = items[0]
            self.categoryTree.editItem(item_clicked, 0)

    def _reload(self):
        self.resetTrees()
        self._load_saved_configs()
        self.sortTrees()

    def menuContextTree(self, point):

        menu = QtWidgets.QMenu()

        createConfig = None
        createCategory = None
        delete = None
        edit = None

        item = self.categoryTree.itemAt(point)
        if item:
            createConfig = menu.addAction('Create new log configuration')
            edit = menu.addAction('Edit name')

            if item.parent():
                delete = menu.addAction('Delete config')
            else:
                delete = menu.addAction('Delete category')
        else:
            createCategory = menu.addAction('Create new Category')

        action = menu.exec_(self.categoryTree.mapToGlobal(point))

        if action == createConfig:
            self._create_config()
        elif createCategory:
            self._create_category()
        elif action == delete:
            self._delete_config()
        elif action == edit:
            self._edit_name()

    def _select_category(self, category):
        items = self.categoryTree.findItems(category,
                                            Qt.MatchFixedString
                                            | Qt.MatchRecursive)
        if items:
            category = items[0]
            self.categoryTree.setCurrentItem(category)
            self._last_pressed_item = category, category.text(0)

    def _select_item(self, conf_name, category):
        """ loads the given config in the correct category """
        items = self.categoryTree.findItems(conf_name,
                                            Qt.MatchFixedString
                                            | Qt.MatchRecursive)
        for item in items:
            if item.parent().text(0) == category:
                self._last_pressed_item = item, conf_name
                self._loadConfig(category, conf_name)
                self.categoryTree.setCurrentItem(item)

    def _item_selected(self):
        """ Opens the log configuration of the pressed
            item in the category-tree. """
        items = self.categoryTree.selectedItems()

        if items:
            config = items[0]
            category = config.parent()
            if category:
                self._loadConfig(category.text(NAME_FIELD),
                                 config.text(NAME_FIELD))
            else:
                # if category is None, it's the category that's clicked
                self._clear_trees_and_progressbar()

    def _clear_trees_and_progressbar(self):
        self.varTree.clear()
        self.logTree.clear()
        self.currentSize = 0
        self.loggingPeriod.setText('')
        self.updatePacketSizeBar()

    def _load_saved_configs(self):
        """ Read saved log-configs and display them on
            the left-side category-tree. """

        config = None
        config = self.helper.logConfigReader._getLogConfigs()

        if (config is None):
            logger.warning("Could not load config")
        else:
            self.categoryTree.clear()
            # Create category-tree.
            for conf_category in config:
                category = QtWidgets.QTreeWidgetItem()
                category.setData(NAME_FIELD, Qt.DisplayRole, conf_category)
                category.setFlags(category.flags() | Qt.ItemIsEditable)

                # Copulate category-tree with log configurations.
                for conf in config[conf_category]:
                    item = QtWidgets.QTreeWidgetItem()

                    # Check if name contains category/config-name.
                    # This is only true is a new config has been added
                    # during a session, and the window re-opened.
                    if '/' in conf.name:
                        conf_name = conf.name.split('/')[1]
                    else:
                        conf_name = conf.name

                    item.setData(NAME_FIELD, Qt.DisplayRole, conf_name)
                    category.addChild(item)

                    # Enable item-editing.
                    item.setFlags(item.flags() | Qt.ItemIsEditable)

                self.categoryTree.addTopLevelItem(category)
                self.categoryTree.expandItem(category)

            self.sortTrees()

    def _loadConfig(self, category, config_name):
        configs = self.helper.logConfigReader._getLogConfigs()[category]

        if (configs is None):
            logger.warning("Could not load config")

        else:
            for config in configs:
                name = self._parse_configname(config)
                if name == config_name:
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

            self.sortTrees()

    def resetTrees(self):
        self.varTree.clear()
        self.logTree.clear()
        self.updateToc()

    def sortTrees(self):
        """ Sorts all trees by their name. """
        for tree in [self.logTree, self.varTree, self.categoryTree]:
            tree.sortItems(NAME_FIELD, Qt.AscendingOrder)
            for node in self.getNodeChildren(tree.invisibleRootItem()):
                node.sortChildren(NAME_FIELD, Qt.AscendingOrder)

    def getNodeChildren(self, treeNode):
        children = []
        for i in range(treeNode.childCount()):
            children.append(treeNode.child(i))
        return children

    def updatePacketSizeBar(self):
        self.currentSize = 0
        for node in self.getNodeChildren(self.varTree.invisibleRootItem()):
            for leaf in self.getNodeChildren(node):
                self.currentSize = (self.currentSize +
                                    int(leaf.text(SIZE_FIELD)))

        self.packetSizeText.setText('%s/%s bytes' % (self.currentSize,
                                                     MAX_LOG_SIZE))

        if self.currentSize > MAX_LOG_SIZE:
            self.packetSize.setMaximum(self.currentSize / MAX_LOG_SIZE * 100)
            self.packetSize.setFormat("%v%")
            self.packetSize.setValue(self.currentSize / MAX_LOG_SIZE * 100)
            self.packetSize.setStyleSheet(
                        UiUtils.progressbar_stylesheet('red'))
        else:
            self.packetSize.setMaximum(MAX_LOG_SIZE)
            self.packetSize.setFormat("%p%")
            self.packetSize.setValue(self.currentSize)
            self.packetSize.setStyleSheet(
                        UiUtils.progressbar_stylesheet(UiUtils.COLOR_GREEN))

    def addNewVar(self, logTreeItem, target):
        parentName = logTreeItem.parent().text(NAME_FIELD)
        varParent = target.findItems(parentName, Qt.MatchExactly, NAME_FIELD)

        item = logTreeItem.clone()

        if (len(varParent) == 0):
            newParent = QtWidgets.QTreeWidgetItem()
            newParent.setData(0, Qt.DisplayRole, parentName)
            newParent.addChild(item)
            target.addTopLevelItem(newParent)
            target.expandItem(newParent)
        else:
            parent = varParent[0]
            parent.addChild(item)

    def moveNodeItem(self, source, target, item):
        if (item.parent() is None):
            children = self.getNodeChildren(item)
            for c in children:
                self.addNewVar(c, target)
            source.takeTopLevelItem(source.indexOfTopLevelItem(item))
        elif (item.parent().childCount() > 1):
            self.addNewVar(item, target)
            item.parent().removeChild(item)
        else:
            self.addNewVar(item, target)
            # item.parent().removeChild(item)
            source.takeTopLevelItem(source.indexOfTopLevelItem(item.parent()))
        self.updatePacketSizeBar()
        self.sortTrees()
        self.checkAndEnableSaveButton()

    def checkAndEnableSaveButton(self):
        if self.currentSize > 0 and self.period > 0 and self.currentSize <= 26:
            self.saveButton.setEnabled(True)
        else:
            self.saveButton.setEnabled(False)

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

    def showEvent(self, event):
        self._clear_trees_and_progressbar()
        self._load_saved_configs()

    def periodChanged(self, value):
        try:
            self.period = int(value)
            self.checkAndEnableSaveButton()
        except Exception:
            self.period = 0

    def showErrorPopup(self, caption, message):
        self.box = QtWidgets.QMessageBox()  # noqa
        self.box.setWindowTitle(caption)
        self.box.setText(message)
        # self.box.setButtonText(1, "Ok")
        self.box.setWindowFlags(Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint)
        self.box.show()

    def updateToc(self):
        self.logTree.clear()
        toc = self.helper.cf.log.toc

        for group in list(toc.toc.keys()):
            groupItem = QtWidgets.QTreeWidgetItem()
            groupItem.setData(NAME_FIELD, Qt.DisplayRole, group)
            for param in list(toc.toc[group].keys()):
                item = QtWidgets.QTreeWidgetItem()
                item.setData(NAME_FIELD, Qt.DisplayRole, param)
                item.setData(ID_FIELD, Qt.DisplayRole,
                             toc.toc[group][param].ident)
                item.setData(TYPE_FIELD, Qt.DisplayRole,
                             toc.toc[group][param].ctype)
                item.setData(SIZE_FIELD, Qt.DisplayRole,
                             struct.calcsize(toc.toc[group][param].pytype))
                groupItem.addChild(item)

            self.logTree.addTopLevelItem(groupItem)

    def populateDropDown(self):
        self.configNameCombo.clear()
        toc = self.helper.logConfigReader.getLogConfigs()
        for d in toc:
            self.configNameCombo.addItem(d.name)
        if (len(toc) > 0):
            self.loadButton.setEnabled(True)

    def saveConfig(self):
        items = self.categoryTree.selectedItems()

        if items:
            config = items[0]
            parent = config.parent()

            if parent:

                # If we're just editing an existing config, we'll delete
                # the old one first.
                self._delete_from_plottab(self._last_pressed_item[1])

                category = parent.text(NAME_FIELD)
                config_name = config.text(NAME_FIELD)
                updatedConfig = self.createConfigFromSelection(config_name)

                if category != 'Default':
                    plot_tab_name = '%s/%s' % (category, config_name)
                else:
                    plot_tab_name = config_name

                try:
                    self.helper.logConfigReader.saveLogConfigFile(
                                                            category,
                                                            updatedConfig)
                    self.statusText.setText('Log config succesfully saved!')
                    self._config_saved_timer.start(4000)
                    if self.closeOnSave.isChecked():
                        self.close()

                except Exception as e:
                    self.showErrorPopup("Error when saving file",
                                        "Error: %s" % e)

        # The name of the config is changed due to displaying
        # it as category/config-name in the plotter-tab.
        # The config is however saved with only the config-name.
        updatedConfig.name = plot_tab_name
        self.helper.cf.log.add_config(updatedConfig)

    def _parse_configname(self, config):
        """ If the configs are placed in a category,
            they are named as Category/confname.
        """
        parts = config.name.split('/')
        return parts[1] if len(parts) > 1 else parts[0]

    def _delete_from_plottab(self, conf_name):
        """ Removes a config from the plot-tab. """
        for logconfig in self.helper.cf.log.log_blocks:
            config_to_delete = self._parse_configname(logconfig)
            if config_to_delete == conf_name:
                self.helper.plotTab.remove_config(logconfig)
                self.helper.cf.log.log_blocks.remove(logconfig)
                logconfig.delete()

    def _get_node_children(self):
        root_item = self.varTree.invisibleRootItem()
        return [root_item.child(i) for i in range(root_item.childCount())]

    def createConfigFromSelection(self, config):
        logconfig = LogConfig(config, self.period)

        for node in self._get_node_children():
            parentName = node.text(NAME_FIELD)

            for leaf in self.getNodeChildren(node):
                varName = leaf.text(NAME_FIELD)
                varType = str(leaf.text(TYPE_FIELD))
                completeName = "%s.%s" % (parentName, varName)
                logconfig.add_variable(completeName, varType)

        return logconfig
