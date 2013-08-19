#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __                           
#  +------+      / __ )(_) /_______________ _____  ___ 
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2013 Bitcraze AB
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
Kinect/OpenCV interface
"""

from freenect import sync_get_depth as get_depth, sync_get_video as get_video
from frame_convert import video_cv, pretty_depth_cv
import cv  
import numpy as np
import time

IMG_WIDTH = 640
IMG_HEIGHT = 480

class Kinect:

    def __init__(self):
        self.text = []
        self.writer = cv.CreateVideoWriter("out.avi", cv.CV_FOURCC('F', 'L', 'V', '1'), 25, (IMG_WIDTH, IMG_HEIGHT), True)
        self.lasttime = time.time()
        return

    def _get_pos_spatial(self, th_img):
        moments = cv.Moments(cv.GetMat(th_img))
        mom10 = cv.GetSpatialMoment(moments, 1, 0)
        mom01 = cv.GetSpatialMoment(moments, 0, 1)
        area = cv.GetCentralMoment(moments, 0, 0)

        if area > 10:
            pos = [int(mom10/area), int(mom01/area)]
        else:
            pos = None

        return pos

    def _get_pos_countour(self, th_img):
        storage = cv.CreateMemStorage(0)
        contour = None
        ci = cv.CreateImage(cv.GetSize(th_img), 8, 1)
        ci = cv.CloneImage(th_img)

        contour = cv.FindContours(th_img, storage, cv.CV_RETR_CCOMP, cv.CV_CHAIN_APPROX_SIMPLE)
        points = []

        while contour:
            bound_rect = cv.BoundingRect(list(contour))
            contour = contour.h_next()
            pt1 = (bound_rect[0], bound_rect[1])
            pt2 = (bound_rect[0] + bound_rect[2], bound_rect[1] + bound_rect[3])
            points.append(pt1)
            points.append(pt2)
            #cv.Rectangle(img, pt1, pt2, cv.CV_RGB(255,0,0), 1)

        center_point = None

        if len(points):
            center_point = reduce(lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), points)
            #cv.Circle(depth, center_point, 10, cv.CV_RGB(255, 255, 255), 1)

        return center_point
        
    def _get_pos(self, img, debug=False):
        th_img = self._get_threashold_image_hsv(img)
        #sp = self._get_pos_spatial(th_img)
        cp = self._get_pos_countour(th_img)

        #if sp:
        #    cv.Circle(img, (sp[0], sp[1]) , 10, cv.CV_RGB(255, 255, 255), 1)
        if cp:        
            cv.Circle(img, (cp[0], cp[1]) , 10, cv.CV_RGB(255, 0, 0), 1)

        return cp

    def _get_threashold_image_hsv(self, img, debug=False):
        """Get the binary threashold image using a HSV method"""
        imgHSV = cv.CreateImage(cv.GetSize(img), 8, 3);
        cv.CvtColor(img, imgHSV, cv.CV_BGR2HSV);
        cv.Smooth(imgHSV, imgHSV, cv.CV_GAUSSIAN, 3, 0)
        img_th = cv.CreateImage(cv.GetSize(img), 8, 1);

        # Filter out red colors
        cv.InRangeS(imgHSV, cv.Scalar(160, 190, 30), cv.Scalar(180, 255, 200), img_th);
        # Fix the image a bit by eroding and dilating
        eroded = cv.CreateImage(cv.GetSize(img), 8, 1);
        cv.Erode( img_th, eroded, None, 1)
        dilated = cv.CreateImage(cv.GetSize(img), 8, 1);
        cv.Dilate( eroded, dilated, None, 4)   

        if debug:
            cv.ShowImage('HSV', imgHSV)
            cv.ShowImage('threas', img_th)
            cv.SaveImage('threas-%d.png' % (time.time()), img_th)
            cv.ShowImage('eroded', eroded)
            cv.ShowImage('dialated', dilated)

        return dilated

    def _get_depth(self, depth_image, debug=False):
        """Get the depth reading from the Kinect"""
        depth = None

        # Only use part of the span to avoid anything else than the Crazyflie
        img_th = cv.CreateImage(cv.GetSize(depth_image), 8, 1);
        cv.InRangeS(depth_image, 10, 210, img_th);

        # Calculate the mean depth
        depth = cv.Avg(depth_image, img_th)[0]

        if debug:
            font = cv.InitFont(cv.CV_FONT_HERSHEY_SIMPLEX, 1, 1, 0, 1, 1) 
            s2 = "%d" % depth
            cv.PutText(img_th, s2, (0,60),font, 200)
            cv.ShowImage('depth th', img_th)

        return depth


    def find_position(self):
        (kinect_depth,_), (rgb,_) = get_depth(), get_video()
        self.img = video_cv(rgb)
        depth_img = pretty_depth_cv(kinect_depth)
 
        position = self._get_pos(self.img)

        depth = self._get_depth(depth_img, debug=True)

        font = cv.InitFont(cv.CV_FONT_HERSHEY_SIMPLEX, 1, 1, 0, 1, 1) 

        fps = 1/(time.time() - self.lasttime)
        s1 = "FPS:%.1f" % fps
        self.lasttime = time.time()
        cv.PutText(self.img,s1, (0,30),font, cv.CV_RGB(255, 0, 0))

        dt = "Depth: %d" % depth
        if position:
            pt = "Pos: X=%d Y=%d" % (position[0], position[1])
        else:
            pt = "Pos: N/A"
        cv.PutText(self.img, dt, (0,60),font, cv.CV_RGB(255, 0, 0))
        cv.PutText(self.img, pt, (0,90),font, cv.CV_RGB(255, 0, 0))

        offset = 120
        for t in self.text:
            cv.PutText(self.img, t, (0,offset),font, cv.CV_RGB(255, 0, 0))
            offset += 30

        cv.ShowImage('RGB', self.img)
        #cv.SaveImage('RGB-%d.png' % (time.time()), self.img)
        #cv.ShowImage('DEPTH', depth_img)
        cv.WriteFrame(self.writer, self.img)
        cv.WaitKey(5)

        #cv.ShowImage('depth_mask', depth_mask)
        try:
            return (position[0], position[1], depth)
        except:
            return (None, None, None)

    def show(self, texts):
        self.text = texts

