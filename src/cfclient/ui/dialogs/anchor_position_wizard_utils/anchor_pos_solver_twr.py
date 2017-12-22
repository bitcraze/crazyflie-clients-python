# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2017 Bitcraze AB
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
Use the Gauss–Newton algorithm to estimate anchor positions from ranging data
(copter to anchors).

Inputs are ranges in a few selected points:
* The origin
* A point on the X-axis, X > 0
* A point in the X-Y plane, Y > 0
* A number of random points in space

x = [
    x of anchor 0
    y of anchor 0
    z of anchor 0
    x of anchor 1
    y of anchor 1
    z of anchor 1
    x, y, z of anchor 2
    ...
    x, y, z of last anchor
    x, y, z of origin position
    x, y, z of x axis position
    x, y, z of x-y plane position
    x, y, z of space position 0
    x, y, z of space position 1
    x, y, z of space position 2
    ...
    x, y, z of last space position
]

In the iteration loop, some data is removed since it is known.
x, y, z of origin position
y, z of x axis position
z of x-y plane position


The functions to minimize are based on
(Xa - Xp)^2 + (Ya - Yp)^2 + (Yz - Zp)^2 - D^2 = 0
Where
    a: anchor
    p: the point of the measurement
    D: Distance (range) measured by the system
"""

import random

import numpy as np


class AnchorPosSolverTwr:
    X = 0
    Y = 1
    Z = 2

    # data types
    ANCHOR = 1
    POINT = 2

    POINT_ORIGIN = 0
    POINT_X_AXIS = 1
    POINT_XY_PLANE = 2
    POINT_SPACE_BASE = 3

    def solve(self, anchor_count, d_origin, d_x_axis, d_x_y_plane, d_space):
        max_iterations = 100
        norm_min_diff = 0.1
        prev_norm = -100

        self.anchor_count = anchor_count

        # Randomize a x vector to start from
        xx = np.array(list(map(lambda i: random.uniform(0.0, 2.0),
                               range(self._nr_of_params(d_space)))))
        x = self._insert_zeros_for_fixed_params(xx)

        found_result = False
        for i in range(max_iterations):
            fx = self._f(x, d_origin, d_x_axis, d_x_y_plane, d_space)
            norm = np.linalg.norm(fx)

            if abs(norm - prev_norm) < norm_min_diff:
                found_result = True
                break

            prev_norm = norm

            j = self._J(x, d_origin, d_x_axis, d_x_y_plane, d_space)
            jj = self._remove_columns_for_unused_params(j)

            h = np.linalg.lstsq(jj, fx)[0]

            xx = self._remove_fixed_params(x)
            xx = xx - h
            x = self._insert_zeros_for_fixed_params(xx)

        if not found_result:
            raise Exception("Did not converge")

        result = []
        for anchor in range(self.anchor_count):
            anchor_pos = (
                x[self._xi(self.ANCHOR, anchor, self.X)],
                x[self._xi(self.ANCHOR, anchor, self.Y)],
                x[self._xi(self.ANCHOR, anchor, self.Z)],
            )
            result.append(anchor_pos)

        return self._flip(result, x)

    """
    Make sure the known parameters that should be 0 really are 0
    """
    def _insert_zeros_for_fixed_params(self, x):
        base = self._xi(self.POINT, self.POINT_ORIGIN, self.X)
        return np.insert(x, [base + 3, base + 1, base + 1, base + 0, base + 0,
                             base + 0], 0.0, axis=0)

    """
    Make a copy of the x vector and remove the known parameters to create the
    compressed x vector that is used in the calculations
    """
    def _remove_fixed_params(self, x):
        return np.delete(x, np.s_[
            self._xi(self.POINT, self.POINT_ORIGIN, self.X),
            self._xi(self.POINT, self.POINT_ORIGIN, self.Y),
            self._xi(self.POINT, self.POINT_ORIGIN, self.Z),
            self._xi(self.POINT, self.POINT_X_AXIS, self.Y),
            self._xi(self.POINT, self.POINT_X_AXIS, self.Z),
            self._xi(self.POINT, self.POINT_XY_PLANE, self.Z),
        ], 0)

    """
    Make a copy of J and remove the columns that corresponds to the known
    parameters in the x vector
    """
    def _remove_columns_for_unused_params(self, j):
        return np.delete(j, np.s_[
            self._xi(self.POINT, self.POINT_ORIGIN, self.X),
            self._xi(self.POINT, self.POINT_ORIGIN, self.Y),
            self._xi(self.POINT, self.POINT_ORIGIN, self.Z),
            self._xi(self.POINT, self.POINT_X_AXIS, self.Y),
            self._xi(self.POINT, self.POINT_X_AXIS, self.Z),
            self._xi(self.POINT, self.POINT_XY_PLANE, self.Z),
        ], 1)

    def _f(self, x, d_origin, d_x_axis, d_x_y_plane, d_space):
        return self._for_all_points(x, d_origin, d_x_axis, d_x_y_plane,
                                    d_space, self._f_row)

    def _J(self, x, d_origin, d_x_axis, d_x_y_plane, d_space):
        return self._for_all_points(x, d_origin, d_x_axis, d_x_y_plane,
                                    d_space, self._J_row)

    def _for_all_points(self, x, d_origin, d_x_axis, d_x_y_plane, d_space,
                        func):
        result = []

        for d in d_origin:
            result.extend(self._for_one_point(x, d, self.POINT_ORIGIN, func))

        for d in d_x_axis:
            result.extend(self._for_one_point(x, d, self.POINT_X_AXIS, func))

        for d in d_x_y_plane:
            result.extend(self._for_one_point(x, d, self.POINT_XY_PLANE, func))

        count = 0
        for d in d_space:
            result.extend(self._for_one_point(x, d,
                                              self.POINT_SPACE_BASE + count,
                                              func))
            count += 1

        return np.array(result)

    def _for_one_point(self, x, d, point_index, func):
        result = []

        for anchor_index in range(self.anchor_count):
            distance = d[anchor_index]
            result.append(func(x, distance, anchor_index, point_index))

        return result

    def _f_row(self, x, distance, anchor_index, point_index):
        X1 = self._xi(self.POINT, point_index, self.X)
        Y1 = self._xi(self.POINT, point_index, self.Y)
        Z1 = self._xi(self.POINT, point_index, self.Z)

        X2 = self._xi(self.ANCHOR, anchor_index, self.X)
        Y2 = self._xi(self.ANCHOR, anchor_index, self.Y)
        Z2 = self._xi(self.ANCHOR, anchor_index, self.Z)

        return (x[X2] - x[X1]) * (x[X2] - x[X1]) + \
               (x[Y2] - x[Y1]) * (x[Y2] - x[Y1]) + \
               (x[Z2] - x[Z1]) * (x[Z2] - x[Z1]) - \
               (distance * distance)

    def _J_row(self, x, distance, anchor_index, point_index):
        X1 = self._xi(self.POINT, point_index, self.X)
        Y1 = self._xi(self.POINT, point_index, self.Y)
        Z1 = self._xi(self.POINT, point_index, self.Z)

        X2 = self._xi(self.ANCHOR, anchor_index, self.X)
        Y2 = self._xi(self.ANCHOR, anchor_index, self.Y)
        Z2 = self._xi(self.ANCHOR, anchor_index, self.Z)

        result = [0.0] * (len(x))

        result[X1] = -2 * (x[X2] - x[X1])
        result[Y1] = -2 * (x[Y2] - x[Y1])
        result[Z1] = -2 * (x[Z2] - x[Z1])

        result[X2] = 2 * (x[X2] - x[X1])
        result[Y2] = 2 * (x[Y2] - x[Y1])
        result[Z2] = 2 * (x[Z2] - x[Z1])

        return result

    """
    It is possible that we have found a solution where the coordinate system
    is mirrored. Flip it back if needed.
    """
    def _flip(self, anchor_pos, x):
        result = anchor_pos

        if x[self._xi(self.POINT, self.POINT_X_AXIS, self.X)] < 0.0:
            result = list(map(lambda pos: (-pos[0], pos[1], pos[2]), result))

        if x[self._xi(self.POINT, self.POINT_XY_PLANE, self.Y)] < 0.0:
            result = list(map(lambda pos: (pos[0], -pos[1], pos[2]), result))

        if x[self._xi(self.POINT, self.POINT_SPACE_BASE, self.Z)] < 0.0:
            result = list(map(lambda pos: (pos[0], pos[1], -pos[2]), result))

        return result

    """
    Calculate the number of parameters in the compressed x vector
    """
    def _nr_of_params(self, d_space):
        return self.anchor_count * 3 + 0 + 1 + 2 + len(d_space) * 3

    """
    Calculate the index in x of an element and axis
    """
    def _xi(self, type, index=0, coord=X):
        if type == self.ANCHOR:
            return index * 3 + coord
        if type == self.POINT:
            return self.anchor_count * 3 + index * 3 + coord

        raise Exception('Unknown type')
