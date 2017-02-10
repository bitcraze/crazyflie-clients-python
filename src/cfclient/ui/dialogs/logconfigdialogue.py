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
    uic.loadUiType(cfclient.module_path + '/ui/dialogs/logconfigdialogue.ui'))

NAME_FIELD = 0
ID_FIELD = 1
PTYPE_FIELD = 2
CTYPE_FIELD = 3


class LogConfigDialogue(QtWidgets.QWidget, logconfig_widget_class):

    def __init__(self, helper, *args):
        super(LogConfigDialogue, self).__init__(*args)
        self.setupUi(self)
        self.helper = helper

        self.logTree.setHeaderLabels(['Name', 'ID', 'Unpack', 'Storage'])
        self.varTree.setHeaderLabels(['Name', 'ID', 'Unpack', 'Storage'])

        self.addButton.clicked.connect(lambda: self.moveNode(self.logTree,
                                                             self.varTree))
        self.removeButton.clicked.connect(lambda: self.moveNode(self.varTree,
                                                                self.logTree))
        self.cancelButton.clicked.connect(self.close)
        self.loadButton.clicked.connect(self.loadConfig)
        self.saveButton.clicked.connect(self.saveConfig)

        self.loggingPeriod.textChanged.connect(self.periodChanged)

        self.packetSize.setMaximum(26)
        self.currentSize = 0
        self.packetSize.setValue(0)
        self.period = 0

    def decodeSize(self, s):
        size = 0
        if ("16" in s):
            size = 2
        if ("float" in s):
            size = 4
        if ("8" in s):
            size = 1
        if ("FP16" in s):
            size = 2
        if ("32" in s):
            size = 4
        return size

    def sortTrees(self):
        self.varTree.invisibleRootItem().sortChildren(NAME_FIELD,
                                                      Qt.AscendingOrder)
        for node in self.getNodeChildren(self.varTree.invisibleRootItem()):
            node.sortChildren(NAME_FIELD, Qt.AscendingOrder)
        self.logTree.invisibleRootItem().sortChildren(NAME_FIELD,
                                                      Qt.AscendingOrder)
        for node in self.getNodeChildren(self.logTree.invisibleRootItem()):
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
                                    self.decodeSize(leaf.text(CTYPE_FIELD)))
        if self.currentSize > 26:
            self.packetSize.setMaximum(self.currentSize / 26.0 * 100.0)
            self.packetSize.setFormat("%v%")
            self.packetSize.setValue(self.currentSize / 26.0 * 100.0)
        else:
            self.packetSize.setMaximum(26)
            self.packetSize.setFormat("%p%")
            self.packetSize.setValue(self.currentSize)

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
        self.updateToc()
        self.populateDropDown()
        toc = self.helper.cf.log.toc
        if (len(list(toc.toc.keys())) > 0):
            self.configNameCombo.setEnabled(True)
        else:
            self.configNameCombo.setEnabled(False)

    def resetTrees(self):
        self.varTree.clear()
        self.updateToc()

    def periodChanged(self, value):
        try:
            self.period = int(value)
            self.checkAndEnableSaveButton()
        except:
            self.period = 0

    def showErrorPopup(self, caption, message):
        self.box = QMessageBox()  # noqa
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
                item.setData(PTYPE_FIELD, Qt.DisplayRole,
                             toc.toc[group][param].pytype)
                item.setData(CTYPE_FIELD, Qt.DisplayRole,
                             toc.toc[group][param].ctype)
                groupItem.addChild(item)

            self.logTree.addTopLevelItem(groupItem)
            self.logTree.expandItem(groupItem)
        self.sortTrees()

    def populateDropDown(self):
        self.configNameCombo.clear()
        toc = self.helper.logConfigReader.getLogConfigs()
        for d in toc:
            self.configNameCombo.addItem(d.name)
        if (len(toc) > 0):
            self.loadButton.setEnabled(True)

    def loadConfig(self):
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

    def saveConfig(self):
        updatedConfig = self.createConfigFromSelection()
        try:
            self.helper.logConfigReader.saveLogConfigFile(updatedConfig)
            self.close()
        except Exception as e:
            self.showErrorPopup("Error when saving file", "Error: %s" % e)
        self.helper.cf.log.add_config(updatedConfig)

    def createConfigFromSelection(self):
        logconfig = LogConfig(str(self.configNameCombo.currentText()),
                              self.period)
        for node in self.getNodeChildren(self.varTree.invisibleRootItem()):
            parentName = node.text(NAME_FIELD)
            for leaf in self.getNodeChildren(node):
                varName = leaf.text(NAME_FIELD)
                varType = str(leaf.text(CTYPE_FIELD))
                completeName = "%s.%s" % (parentName, varName)
                logconfig.add_variable(completeName, varType)
        return logconfig
