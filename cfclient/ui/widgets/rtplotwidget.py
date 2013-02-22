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

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
Simple plot widget designed for real-time plotting of data.
"""

__author__ = 'Bitcraze AB'
__all__ = ['PlotAxis', 'PlotDataSet','FastPlotWidget']

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, QLine, QPoint, QPointF, QSize, QRectF

from time import time
import math

class PlotAxis:
    def __init__(self, x, color = QtCore.Qt.black):
        self.color = color
        self.min = 0
        self.max = 0
        self.lines = []
        self.x = x
        self.data = []        

    def getLimits(self):
        return (self.min, self.max)

    def setLimits(self, limits):
        self.min = limits[0]
        self.max = limits[1]

    def getAxisLines(self):
        """Return all the lines for this axis"""
        return self.lines

    def updateAxisLines(self, yTop, yBottom):
        """The window has been resized, we need to update the lines"""
        self.lines = [QLine(self.x, yTop, self.x, yBottom)]
        return

    def setZoom(self, factor):
        for ds in self.data:
            ds.setZoom(factor)

    def addDataset(self, ds):
        self.data.append(ds)

    def removeDataset(self, ds):
        self.data.delete(ds)
    
    def __str__(self):
        return "Axis: X=%d with %d lines" % (self.x, len(self.lines))

class PlotDataSet:
    def __init__(self, title, color, yrange):
        self.color = color
        self.title = title
        self.data = []
        self.origdata = []
        self.offset = 0
        self.translate = 0
        self.maxItems = 0
        self.scaling = 1.0
        self.maxValue = yrange[0]
        self.minValue = yrange[1]
        self.enabled = True
        self.zoom = 1.0
        self.zooming = False

    def setEnabled(self, shouldEnable):
        self.enabled = shouldEnable

    def addData(self, data):
        # TODO Protect data when doing setupParams !
        self.offset = self.offset + 1
        self.data.append(QPointF(self.offset, data*self.scaling*self.zoom))
        self.origdata.append(data)
        if (len(self.data) == self.maxItems):
            self.data.pop(0)
            self.origdata.pop(0)
            self.translate = self.translate + 1

    def setMinMaxAxisValue(self, minValue, maxValue):
        self.minValue = minValue
        self.maxValue = maxValue
    
    def getMinMaxAxisValue(self):
        return (self.minValue, self.maxValue)

    def setZoom(self, zoom):
        self.zoom = zoom
        for i in range(0, len(self.data)):
            self.data[i].setY(self.origdata[i]*self.scaling*self.zoom)
            
    def setupParams(self, maxItems, maxYSpan):
        self.maxItems = maxItems
        self.scale = float(maxYSpan)/(abs(self.maxValue) + abs(self.minValue))
        if (len(self.data) > 0):
            if (maxItems < len(self.data)):
                itemsToRemove = len(self.data)-maxItems + 1
                self.data = self.data[itemsToRemove:]
                self.translate = self.translate + itemsToRemove
            # Recalc all the points in the graph..
            for i in range(0, len(self.data)):
                self.data[i].setY(self.origdata[i]*self.scaling)
            #for d in self.data:
            #    d.setY((d.y()/(self.scaling*self.prevZoom)) * newScale * self.zoom)
        #self.scaling = newScale
        #print "%d:%d" % (len(self.data), self.maxItems)
        #print "Scaling is %.02f (height=%i,dataswing=%i)" % (self.scaling,maxYSpan,(abs(self.maxValue) + abs(self.minValue)))

class FastPlotWidget(QtGui.QWidget):

    LEGEND_ON_BOTTOM = 1
    LEGEND_ON_RIGHT = 2

    # Add support for
    # * Multipe axis
    # * Klicking to pause
    # * Klicking to show data value (or mouse of if ok CPU wise..)
    # * Scrolling when paused
    # * Zooming
    # * Change axis
    # * Auto size of min/max X-axis
    # * Redraw of resize (stop on minimum size)
    # * Fill parent as much as possible
    # * Add legend (either hard, option or mouse over)

    def __init__(self, parent=None, fps=100):
        super(FastPlotWidget, self).__init__(parent)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.MinimumExpanding,QtGui.QSizePolicy.MinimumExpanding))

        self.setMinimumSize(self.minimumSizeHint())
        self.parent = parent

        self.edgeMargin = 2    
        self.legendHeight = 50
        
        #self.legendBoxMargin = 20
        #self.legendRowMargin = 5
        
        #self.maxY = 180
        #self.minY = -180
        self.maxSamples = self.width() - 2*self.edgeMargin
        #self.maxX = 100
        #self.minX = -100

        self.yAxisWith = 20
        self.yAxisMarkerWidth = 10
        
        self.dataStartX = self.edgeMargin
        self.dataStartY = self.height()/2

        self.fpsPrintTS = time()
        self.fps = 0
        self.renderings = 0
        self.fpsWriteFreq = 2.0
        self.datasets = []
        
        self.timer = QtCore.QTimer()
        self.timer.setInterval(1000/fps);
        self.timer.timeout.connect(self.redrawGraph)
        self.timer.start()
        
        #self.legendYBaseEven = 400
        #self.legendYBaseOdd = 420
        #self.legendXBase = 100
        #self.legendXStep = 100

        self.allAxis = []

        self.xAxisLines = []
        
        self.recalcAllComponents()

        #self.yAxisXOffset = 10
        self.yAxisCurrentXOffset = self.yAxisX

        self.enableDrawing = True
        self.defaultAxis = None

    def setZoom(self, factor):
        for a in self.allAxis:
            a.setZoom(factor)

    def addDataset(self, dataset):
        dataset.setupParams(self.maxSamples, self.plotHeight)
        # Check if this is the first dataset, if so create the default axis
        if (self.defaultAxis == None):
            self.defaultAxis = PlotAxis(self.yAxisCurrentXOffset)
            self.defaultAxis.setLimits(dataset.getMinMaxAxisValue())
            self.defaultAxis.updateAxisLines(self.yAxisYStart, self.yAxisYEnd)
            self.allAxis.append(self.defaultAxis)
            self.defaultAxis.addDataset(dataset)
        elif (self.defaultAxis.getLimits() != dataset.getMinMaxAxisValue()):
            self.yAxisCurrentXOffset += self.yAxisWith
            newAxis = PlotAxis(self.yAxisCurrentXOffset)
            newAxis.setLimits(dataset.getMinMaxAxisValue())
            newAxis.updateAxisLines(self.yAxisYStart, self.yAxisYEnd)
            self.allAxis.append(newAxis)
        else:
            self.defaultAxis.addDataset(dataset)

        self.datasets.append(dataset)
        #self.updateAxisCalculations()
        
    def removeDataset(self, dataset):
        print "Not supported"

    def removeAllDatasets(self):
        self.datasets = []

    def setEnabled(self, shouldEnable):
        self.enableDrawing = shouldEnable

    def redrawGraph(self):
        if (self.isVisible() == True and self.enableDrawing == True):
            self.update()

    #def sizeHint(self):
    #    return QtCore.QSize(800, 500)

    def recalcAllComponents(self):
        # This will also reset all the datsets and change the scaling/max samples.
        self.maxSamples = self.width() - 2*self.edgeMargin
        self.plotHeight = self.height() - 2*self.edgeMargin# - self.legendHeight
        self.plotWidth = self.width() - 2*self.edgeMargin
        for ds in self.datasets:
            ds.setupParams(self.plotWidth, self.plotHeight)
        self.dataStartX = self.edgeMargin
        self.dataStartY = self.edgeMargin+self.plotHeight/2
        self.updateAxisCalculations()

    def minimumSizeHint(self):
        return QtCore.QSize(400, 300)
        #return QtCore.QSize(self.parent.width(), self.parent.height())

    #def mouseMoveEvent( event )
    # use to show data
    
    def mousePressEvent(self, event):
        #Use to show data
        print "x=%i,y=%i" % (event.x(), event.y())
        #print "FastPlotWidget: Size (%i,%i)" % (self.width(), self.height())
        
    def resizeEvent(self, event):
        #print "Woha, resize to %ix%i" % (event.size().width(), event.size().height())
        self.recalcAllComponents()

    def updateXAxisLines(self):
        self.xAxisY = self.edgeMargin+self.plotHeight/2
        self.xAxisXStart = self.edgeMargin
        self.xAxisXEnd = self.width() - self.edgeMargin
        self.xAxisLines = [QLine(self.xAxisXStart, self.xAxisY, self.xAxisXEnd, self.xAxisY)]
                
    def updateAxisCalculations(self):
        self.yAxisX = self.edgeMargin
        self.yAxisYStart = self.edgeMargin
        self.yAxisYEnd = self.yAxisYStart+self.plotHeight# + self.legendHeight

        self.xAxisY = self.edgeMargin+self.plotHeight/2
        self.xAxisXStart = self.edgeMargin
        self.xAxisXEnd = self.width() - self.edgeMargin

        self.updateXAxisLines()
        for a in self.allAxis:
            a.updateAxisLines(self.yAxisYStart, self.yAxisYEnd)
        #yAxisX = self.edgeMargin
        #yAxisYStart = self.edgeMargin
        #yAxisYEnd = yAxisYStart+self.plotHeight# + self.legendHeight

        #xAxisY = self.edgeMargin+self.plotHeight/2
        #xAxisXStart = self.edgeMargin
        #xAxisXEnd = self.width() - self.edgeMargin

        #self.xAxisLines = [QLine(xAxisXStart, xAxisY, xAxisXEnd, xAxisY)]
        #self.yAxisLines = []
        #xOffset = yAxisX
        #for d in self.datasets:
        #    [yMin, yMax] = d.getMinMaxAxisValue()
        #    #print "%d, %d, %d, %d" % (xOffset, yAxisYStart, xOffset, yAxisYEnd)
        #    self.yAxisLines.append(QLine(xOffset, yAxisYStart, xOffset, yAxisYEnd))
        #    
        #    xOffset = xOffset + self.yAxisWith

        #self.yAxisLines = [QLine(yAxisX, yAxisYStart, yAxisX, yAxisYEnd)]

        #self.axis = [
        #    QLine(yAxisX, yAxisYStart, yAxisX, yAxisYEnd),
        #    QLine(xAxisXStart, xAxisY, xAxisXEnd, xAxisY),
        #            ]
        
    def drawAxis(self, painter):
        if (len(self.xAxisLines) > 0):
            painter.drawLines(self.xAxisLines)
        for a in self.allAxis:
            painter.drawLines(a.getAxisLines())
        
    def drawData(self, painter):
        for ds in self.datasets:
            if (len(ds.data) > 0 and ds.enabled):
                painter.translate(self.dataStartX-ds.translate, self.dataStartY)
                painter.setPen(ds.color)
                painter.drawPolyline(*ds.data)
                painter.translate(-self.dataStartX+ds.translate, -self.dataStartY)

    def drawLegend(self, painter):
        # These could be optomized to only the recalculated on added datasets and resize...
        dsIndex = 0
        cols = math.ceil(len(self.datasets)/2.0)
        rows = min(len(self.datasets), 2.0)
        offsetPerCol = self.plotWidth / cols
        offsetPerRow = painter.boundingRect(QRectF(), Qt.AlignLeft, "Test").height() + self.legendRowMargin
        #print "Cols=%i,rows=%i (offset is %i,%i)" % (cols, rows, offsetPerRow, offsetPerCol)
        #print "Drawing %i, %i" % (cols, rows)
        for ds in self.datasets:
            painter.setPen(ds.color)
            #r = painter.boundingRect(QRectF(), Qt.AlignLeft, ds.title)
            #print "%ix%i" % (r.width(), r.height())
            #rint "Special %i,%i" % (math.floor(dsIndex/2), dsIndex%rows)
            x = self.edgeMargin+self.legendBoxMargin+math.floor(dsIndex/2)*offsetPerCol
            y = self.edgeMargin+self.plotHeight+self.legendBoxMargin+(dsIndex%rows)*offsetPerRow
            #print "Drawing [%s] at %ix%i" % (ds.title, x,y)
            painter.drawText(x, y, ds.title)
            dsIndex = dsIndex + 1
        
    def paintEvent(self,event=None):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        
        # Debug data
        painter.setPen(QtCore.Qt.red)
        # Draw component bounding rect
        painter.drawRect(0, 0, self.width(), self.height())
        # Draw component bounding rect
        #painter.drawRect(self.edgeMargin, self.edgeMargin, self.plotWidth, self.plotHeight)
        # Draw legend bounding rect
        #painter.drawRect(self.edgeMargin, self.edgeMargin+self.plotHeight, self.plotWidth, self.legendHeight)

        # Calc FPS
        self.renderings = self.renderings + 1
        if (time() - self.fpsPrintTS > self.fpsWriteFreq):
            self.fps = self.renderings / self.fpsWriteFreq
            self.fpsPrintTS = time()
            self.renderings = 0
        fpsString = "FPS: %i" % int(self.fps)
        painter.drawText(10, 10, fpsString)
        
        # Dra axis and data
        painter.setPen(QtCore.Qt.black)     
        self.drawAxis(painter)
        if (len(self.datasets) > 0):
            self.drawData(painter)
            #self.drawLegend(painter)
        
        
