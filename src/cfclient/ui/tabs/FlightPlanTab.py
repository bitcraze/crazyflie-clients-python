#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2021 Bitcraze AB
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

#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>

'''
Allow you to create a flight plan for your CrazyFlie using the high level
positioning library.
'''

import logging
import time

from PyQt5 import uic, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QObject, Qt, QMimeData, QThread

import cfclient
from cfclient.ui.tab import Tab

from cflib.positioning.position_hl_commander import PositionHlCommander

__author__ = 'Bitcraze AB'
__all__ = ['FlightPlanTab']

logger = logging.getLogger(__name__)

log_client_tab_class = uic.loadUiType(cfclient.module_path +
                                      '/ui/tabs/flightPlanTab.ui')[0]


def bgcolor_from_name(name):
    if name in ['Take Off', 'Land']:
        return '#e76f51'
    elif name in ['Left', 'Right', 'Forward', 'Back', 'Up', 'Down']:
        return '#264653'
    elif name in ['Goto', 'Move Distance']:
        return '#f4a261'
    else:
        return '#00c5ff'


def move_up(lst, item):
    row = lst.row(item)
    widget = lst.itemWidget(item)

    if row > 0:
        new = item.clone()
        lst.insertItem(row - 1, new)
        lst.setItemWidget(new, widget)
        lst.takeItem(row + 1)
        connect_widget_reorder(lst, widget, new)
        widget.changed.emit()


def move_down(lst, item):
    row = lst.row(item)
    widget = lst.itemWidget(item)

    if row == -1:
        return

    if row < lst.count():
        new = item.clone()
        lst.insertItem(row + 2, new)
        lst.setItemWidget(new, widget)
        lst.takeItem(row)
        connect_widget_reorder(lst, widget, new)
        widget.changed.emit()


def remove(lst, item):
    widget = lst.itemWidget(item)
    lst.takeItem(lst.row(item))
    widget.changed.emit()


def connect_widget_reorder(lst, widget, item):
    widget.reorderUp.disconnect()
    widget.reorderUp.clicked.connect(lambda: move_up(lst, item))

    widget.reorderDown.disconnect()
    widget.reorderDown.clicked.connect(lambda: move_down(lst, item))

    widget.closeButton.disconnect()
    widget.closeButton.clicked.connect(lambda: remove(lst, item))


def add_action_to_list(lst, action, row):
    item = QtWidgets.QListWidgetItem()

    if action in ['Take Off', 'Land']:
        widget = FlightActionSimple(action)
    elif action in ['Left', 'Right', 'Forward', 'Back', 'Up', 'Down']:
        widget = FlightActionStep(action)
    elif action in ['Goto', 'Move Distance']:
        widget = FlightActionCoordinate(action)
    elif action == 'Loop':
        widget = FlightActionContainer(action)
    elif action == 'Wait':
        widget = FlightActionInput(action)

    connect_widget_reorder(lst, widget, item)

    item.setSizeHint(widget.sizeHint())

    if row is None or row == -1:
        lst.addItem(item)
    else:
        lst.insertItem(row, item)

    lst.setItemWidget(item, widget)
    return (item, widget)


class CommandLabel(QtGui.QLabel):

    def __init__(self, parent=None):
        QtGui.QLabel.__init__(self, parent)

        self.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.setStyleSheet(
            """ QLabel {
                    background-color: %s;
                    color: #ececec;
                    font-weight: bold;
                    border: 1px inset grey;
                } """ % bgcolor_from_name(self.text())
        )

    def mouseMoveEvent(self, event):
        mimeData = QMimeData()
        mimeData.setText(self.text())

        drag = QtGui.QDrag(self)
        drag.setMimeData(mimeData)
        drag.setHotSpot(event.pos() - self.rect().topLeft())
        dropAction = drag.exec_(Qt.MoveAction)  # noqa: F841


class FlightAction(QtWidgets.QGroupBox):
    changed = pyqtSignal()

    def __init__(self, name):
        super(FlightAction, self).__init__()
        self.name = name
        self.setStyleSheet(
            """ QLabel {
                    background-color: %s;
                    color: #ececec;
                    font-weight: bold;
                    border: 1px inset grey;
                }

                QPushButton {
                    border: none;
                    background: transparent;
                }

                QPushButton:hover {
                    border: 1px solid blue;
                    background: lightgray;
                }""" % bgcolor_from_name(name)
        )


class FlightActionStep(FlightAction):
    def __init__(self, name):
        super(FlightActionStep, self).__init__(name)
        uic.loadUi(cfclient.module_path + '/ui/tabs/flightActionStep.ui', self)
        self.actionLabel.setText(name)

        self.velocityEdit.valueChanged.connect(self.changed.emit)
        self.distanceEdit.valueChanged.connect(self.changed.emit)

        self.show()

    def distance(self):
        return self.distanceEdit.value()

    def velocity(self):
        return self.velocityEdit.value()


class FlightActionInput(FlightAction):
    def __init__(self, name):
        super(FlightActionInput, self).__init__(name)
        uic.loadUi(cfclient.module_path +
                   '/ui/tabs/flightActionInput.ui', self)
        self.actionLabel.setText(name)

        self.show()

    def wait_ms(self):
        return self.inputBox.value()


class FlightActionCoordinate(FlightAction):
    def __init__(self, name):
        super(FlightActionCoordinate, self).__init__(name)
        uic.loadUi(cfclient.module_path +
                   '/ui/tabs/flightActionCoordinate.ui', self)
        self.actionLabel.setText(name)

        self.xBox.valueChanged.connect(self.changed.emit)
        self.yBox.valueChanged.connect(self.changed.emit)
        self.zBox.valueChanged.connect(self.changed.emit)

        self.show()

    def x(self):
        return self.xBox.value()

    def y(self):
        return self.yBox.value()

    def z(self):
        return self.zBox.value()


class FlightActionSimple(FlightAction):
    def __init__(self, name):
        super(FlightActionSimple, self).__init__(name)
        uic.loadUi(cfclient.module_path +
                   '/ui/tabs/flightActionSimple.ui', self)
        self.actionLabel.setText(name)

        self.show()


class FlightActionContainer(FlightAction):
    def __init__(self, name):
        super(FlightActionContainer, self).__init__(name)
        uic.loadUi(cfclient.module_path +
                   '/ui/tabs/flightActionContainer.ui', self)
        self.actionLabel.setText(name)

        self.inputBox.valueChanged.connect(self.changed.emit)
        self.containerList.model().rowsRemoved.connect(self.changed.emit)

        self.containerList.dropEvent = self._dropEvent
        self.containerList.dragEnterEvent = self._dragEnterEvent
        self.containerList.dragMoveEvent = lambda e: e.accept()

        self.show()

    def input(self):
        return self.inputBox.value()

    def _add(self, action, row):
        item, widget = add_action_to_list(self.containerList, action, row)
        self.changed.emit()

    def _dropEvent(self, event):
        if event.mimeData().hasText():
            row = self.containerList.indexAt(event.pos()).row()
            self._add(event.mimeData().text(), row)
            event.setDropAction(Qt.MoveAction)
            event.accept()

    def _dragEnterEvent(self, event):
        event.accept()


class FlightPlanList(QtWidgets.QListWidget):
    changed = pyqtSignal()

    def __init__(self, parent):
        super(FlightPlanList, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setSizeAdjustPolicy(QtWidgets.QListWidget.AdjustToContents)
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.bounds = {
            'Up': 0.0,
            'Left': 0.0,
            'Right': 0.0,
            'Back': 0.0,
            'Forward': 0.0
        }

    def dragMoveEvent(self, event):
        event.accept()

    def dragEnterEvent(self, event):
        row = self.indexAt(event.pos()).row()
        self.setCurrentRow(row)
        event.accept()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            row = self.indexAt(event.pos()).row()
            self.add_action(event.mimeData().text(), row)
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            super(FlightPlanList, self).dropEvent(event)

        self.clearSelection()
        self.compile()
        self.changed.emit()

    def _update_bounds(self, coords, bounds, widget):
        action = widget.name

        if action == 'Forward':
            coords[0] += widget.distance()
        elif action == 'Back':
            coords[0] -= widget.distance()
        elif action == 'Left':
            coords[1] += widget.distance()
        elif action == 'Right':
            coords[1] -= widget.distance()
        elif action == 'Up':
            coords[2] += widget.distance()
        elif action == 'Down':
            coords[2] -= widget.distance()
        elif action == 'Move Distance':
            coords[0] += widget.x()
            coords[1] += widget.y()
            coords[2] += widget.z()
        elif action == 'Goto':
            coords[0] = widget.x()
            coords[1] = widget.y()
            coords[2] = widget.z()
        elif action == 'Take Off':
            coords[2] = 0.5

        if coords[0] > bounds['Forward']:
            bounds['Forward'] = coords[0]
        if coords[0] < bounds['Back']:
            bounds['Back'] = coords[0]

        if coords[1] > bounds['Left']:
            bounds['Left'] = coords[1]
        if coords[1] < bounds['Right']:
            bounds['Right'] = coords[1]

        if coords[2] > bounds['Up']:
            bounds['Up'] = coords[2]

        return bounds

    def compile(self):
        bounds = {
            'Up': 0.0,
            'Left': 0.0,
            'Right': 0.0,
            'Back': 0.0,
            'Forward': 0.0
        }
        coords = [0.0, 0.0, 0.0]
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget is None:
                continue

            if widget.name == 'Loop':
                for _ in range(widget.input()):
                    for loop_i in range(widget.containerList.count()):
                        loop_item = widget.containerList.item(loop_i)
                        loop_w = widget.containerList.itemWidget(loop_item)
                        if loop_w is None:
                            continue

                        bounds = self._update_bounds(coords, bounds, loop_w)
            else:
                bounds = self._update_bounds(coords, bounds, widget)

            self.bounds = bounds

    def _update_action(self):
        self.compile()
        self.changed.emit()

    def add_action(self, action, row=None):
        item, widget = add_action_to_list(self, action, row)
        widget.changed.connect(self._update_action)


class FlightPlanExecutor(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def __init__(self, plan, cf):
        self.plan = plan
        self.cf = cf
        self.abort = False
        super(FlightPlanExecutor, self).__init__()

    def stop(self):
        print('ABORT SIGNALED!')
        self.abort = True

    def _perform_action(self, commander, action):
        if self.abort:
            commander.land()
            return False

        if action.name == 'Loop':
            lst = action.containerList
            for i in range(action.input()):
                action.setToolTip('iteration %d/%d' % (i, action.input()))
                for j in range(lst.count()):
                    item = lst.item(j)
                    lst.setCurrentItem(item)
                    widget = lst.itemWidget(item)
                    if not self._perform_action(commander, widget):
                        return False
                lst.clearSelection()
        elif action.name == 'Wait':
            seconds = action.wait_ms() / 1000.0
            time.sleep(seconds)
        elif action.name == 'Take Off':
            commander.take_off()
        elif action.name == 'Land':
            commander.land()
        elif action.name == 'Forward':
            commander.forward(action.distance(), action.velocity())
        elif action.name == 'Back':
            commander.back(action.distance(), action.velocity())
        elif action.name == 'Left':
            commander.left(action.distance(), action.velocity())
        elif action.name == 'Right':
            commander.right(action.distance(), action.velocity())
        elif action.name == 'Up':
            commander.up(action.distance(), action.velocity())
        elif action.name == 'Down':
            commander.down(action.distance(), action.velocity())
        elif action.name == 'Move Distance':
            commander.move_distance(action.x(), action.y(), action.z())
        elif action.name == 'Goto':
            commander.go_to(action.x(), action.y(), action.z())

        return True

    def run(self):
        try:
            #
            # Reset the Kalman filter before taking off, to avoid
            # positional confusion.
            #
            self.cf.param.set_value('kalman.resetEstimation', '1')
            time.sleep(1)

            commander = PositionHlCommander(
                self.cf,
                x=0.0, y=0.0, z=0.0,
                default_velocity=0.3,
                default_height=0.5,
                controller=PositionHlCommander.CONTROLLER_PID
            )
            for i in range(self.plan.count()):
                item = self.plan.item(i)
                self.plan.setCurrentItem(item)
                action = self.plan.itemWidget(item)

                if not self._perform_action(commander, action):
                    break

                time.sleep(1)
                self.progress.emit(i + 1)
        except Exception as err:
            logger.warning('Exception running flight plan: %s' % str(err))

        self.finished.emit()


class FlightPlanTab(Tab, log_client_tab_class, logging.StreamHandler):
    def __init__(self, tabWidget, helper, *args):
        super(FlightPlanTab, self).__init__(*args)
        logging.StreamHandler.__init__(self)
        self.setupUi(self)

        self.tabName = 'Flight Planner'
        self.menuName = 'Flight Planner'

        self.tabWidget = tabWidget
        self._helper = helper
        self.worker = None
        self.thread = None

        self._init_ui()

    def _init_ui(self):
        # init flight plan view
        self.plan = FlightPlanList(self)
        self.plan.add_action('Take Off')
        self.plan.compile()
        self.planGrid.addWidget(self.plan, 0, 0)

        # init command grid
        self.command_items = [
            [
                'Take Off',
                'Land',
                'Forward',
                'Back',
                'Left',
            ], [
                'Right',
                'Up',
                'Down',
                'Goto',
                'Move Distance',
            ], [
                'Loop',
                'Wait'
            ],
        ]
        commandGrid = QtGui.QWidget()
        commandLayout = QtGui.QGridLayout()
        commandGrid.setLayout(commandLayout)
        self.planGrid.addWidget(commandGrid, 1, 0)
        for (row_idx, row) in enumerate(self.command_items):
            for (col_idx, item) in enumerate(row):
                button = CommandLabel(item)
                commandLayout.addWidget(button, row_idx, col_idx)

        # init control view
        self._update_space_requirements()
        self.plan.changed.connect(
            lambda: self._update_space_requirements()
        )
        self.execButton.clicked.connect(self._execute_plan)
        self.abortButton.clicked.connect(self._abort_plan)

    def _update_space_requirements(self):
        self.spaceAbove.setText('%f m' % abs(self.plan.bounds['Up']))
        self.spaceForward.setText('%f m' % abs(self.plan.bounds['Forward']))
        self.spaceBack.setText('%f m' % abs(self.plan.bounds['Back']))
        self.spaceLeft.setText('%f m' % abs(self.plan.bounds['Left']))
        self.spaceRight.setText('%f m' % abs(self.plan.bounds['Right']))

    def _worker_cleanup(self):
        self.thread.quit()
        self.worker.deleteLater()

    def _thread_cleanup(self):
        self.plan.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.execButton.setEnabled(True)
        self.thread.deleteLater()

    def _execute_plan(self):
        self.plan.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self.thread = QThread()
        self.worker = FlightPlanExecutor(self.plan, self._helper.cf)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

        self.execButton.setEnabled(False)

        self.worker.finished.connect(self._worker_cleanup)
        self.thread.finished.connect(self._thread_cleanup)

    def _abort_plan(self):
        if self.worker is not None:
            self.worker.abort = True
