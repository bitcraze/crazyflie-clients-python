#!/usr/bin/env python3
"""Display a Crazyflie's mocap flight path in an interactive 3D plot.

Use it with the CSV written by ``mocap_manual_thrust_assisted_figure8.py``::

    python3 plot_crazyflie_3d_track.py flight_logs/mocap-assisted-figure8-*.csv --live

With ``--live`` the viewer rereads the CSV while the flight is running.  Drag
the plot to rotate it, and use the toolbar to zoom or save an image.
"""

import argparse
import csv
import math
import time
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


# These must match the local-frame transform and cage points in the flight
# script: local +X <- raw -Y, local +Y <- raw +X, local +Z <- raw +Z.
RAW_CAGE_CORNER_POINTS = (
    (-1.027, 1.015, 0.046),
    (-1.020, -0.999, 0.046),
    (1.035, -1.019, 0.033),
    (1.037, 0.981, 0.038),
)


def raw_position_to_local(raw_position):
    raw_x, raw_y, raw_z = (float(value) for value in raw_position)
    return -raw_y, raw_x, raw_z


def read_samples(path, max_samples):
    """Return valid mocap samples, tolerating a partially written final row."""
    samples = []
    try:
        with path.open(newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                try:
                    x = float(row["mocap_x"])
                    y = float(row["mocap_y"])
                    z = float(row["mocap_z"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not all(math.isfinite(value) for value in (x, y, z)):
                    continue
                samples.append((x, y, z, row.get("phase", ""),
                                row.get("target_x"), row.get("target_y")))
    except FileNotFoundError:
        return []
    return samples[-max_samples:]


def numeric_targets(samples):
    targets = []
    for _, _, _, _, target_x, target_y in samples:
        try:
            targets.append((float(target_x), float(target_y)))
        except (TypeError, ValueError):
            targets.append(None)
    return targets


def set_equal_3d_scale(axis, xs, ys, zs):
    """Use equal visual scale so one metre looks the same on every axis."""
    ranges = [max(values) - min(values) for values in (xs, ys, zs)]
    radius = max(max(ranges) / 2.0, 0.25)
    centers = [(max(values) + min(values)) / 2.0 for values in (xs, ys, zs)]
    axis.set_xlim(centers[0] - radius, centers[0] + radius)
    axis.set_ylim(centers[1] - radius, centers[1] + radius)
    axis.set_zlim(centers[2] - radius, centers[2] + radius)
    try:
        axis.set_box_aspect((1, 1, 1))
    except AttributeError:
        pass


def add_cage(axis):
    corners = [raw_position_to_local(point) for point in RAW_CAGE_CORNER_POINTS]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    ground_z = min(point[2] for point in corners)
    for index, point in enumerate(corners):
        other = corners[(index + 1) % len(corners)]
        axis.plot((point[0], other[0]), (point[1], other[1]),
                  (ground_z, ground_z), color="0.45", linewidth=1.2)
    return xs, ys, [ground_z]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="flight CSV containing mocap_x/y/z columns")
    parser.add_argument("--live", action="store_true", help="refresh while the flight logger appends rows")
    parser.add_argument("--interval-ms", type=int, default=200, help="live refresh period (default: 200)")
    parser.add_argument("--max-samples", type=int, default=3000, help="maximum trail points (default: 3000)")
    parser.add_argument("--no-cage", action="store_true", help="hide the ground-level cage outline")
    parser.add_argument("--save", type=Path, help="save a static PNG/SVG/PDF instead of opening a window")
    args = parser.parse_args()

    if args.interval_ms < 50 or args.max_samples < 2:
        parser.error("--interval-ms must be >= 50 and --max-samples must be >= 2")

    figure = plt.figure("Crazyflie 3D flight tracker", figsize=(9, 7))
    axis = figure.add_subplot(projection="3d")
    axis.set_xlabel("Local X (m)")
    axis.set_ylabel("Local Y (m)")
    axis.set_zlabel("Local Z (m)")
    axis.view_init(elev=25, azim=-55)

    cage_xs, cage_ys, cage_zs = ([], [], [])
    if not args.no_cage:
        cage_xs, cage_ys, cage_zs = add_cage(axis)
    trail, = axis.plot([], [], [], color="#1976d2", linewidth=1.8, label="mocap trail")
    target, = axis.plot([], [], [], "--", color="#ff9800", linewidth=1.2, label="X/Y target")
    drone, = axis.plot([], [], [], "o", color="#e53935", markersize=8, label="Crazyflie now")
    status = axis.text2D(0.02, 0.96, "Waiting for mocap samples…", transform=axis.transAxes)
    axis.legend(loc="upper right")

    last_count = -1

    def refresh(_frame):
        nonlocal last_count
        samples = read_samples(args.log, args.max_samples)
        if not samples:
            status.set_text(f"Waiting for samples in {args.log.name}")
            return trail, target, drone, status
        if len(samples) == last_count and args.live:
            return trail, target, drone, status
        last_count = len(samples)

        xs = [sample[0] for sample in samples]
        ys = [sample[1] for sample in samples]
        zs = [sample[2] for sample in samples]
        trail.set_data(xs, ys)
        trail.set_3d_properties(zs)
        drone.set_data([xs[-1]], [ys[-1]])
        drone.set_3d_properties([zs[-1]])

        targets = numeric_targets(samples)
        target_xs = [value[0] if value else math.nan for value in targets]
        target_ys = [value[1] if value else math.nan for value in targets]
        target.set_data(target_xs, target_ys)
        target.set_3d_properties(zs)

        set_equal_3d_scale(axis, xs + cage_xs, ys + cage_ys, zs + cage_zs)
        phase = samples[-1][3] or "unknown"
        status.set_text(
            f"{len(samples)} samples | phase: {phase} | "
            f"position: ({xs[-1]:+.2f}, {ys[-1]:+.2f}, {zs[-1]:+.2f}) m"
        )
        return trail, target, drone, status

    refresh(None)
    if args.live:
        # Keep a reference: matplotlib otherwise garbage-collects the timer.
        figure._crazyflie_animation = FuncAnimation(  # pylint: disable=protected-access
            figure, refresh, interval=args.interval_ms, cache_frame_data=False
        )
    if args.save:
        if args.live:
            parser.error("--save cannot be combined with --live")
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180, bbox_inches="tight")
        print(f"Saved 3D flight path: {args.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
