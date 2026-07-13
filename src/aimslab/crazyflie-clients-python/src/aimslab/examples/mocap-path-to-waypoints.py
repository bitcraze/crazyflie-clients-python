#!/usr/bin/env python3
"""Convert a hand-guided mocap CSV path into small local XY waypoints.

This tool is intentionally offline: it does not connect to the Crazyflie,
arm it, or send any setpoints. The output uses metres, starts at local
(0, 0), holds a fixed requested height, and fits the path inside a requested
horizontal extent. It is suitable for reviewing or later converting to a
Bitcraze high-level trajectory after the estimator frame has been verified.
"""

import argparse
import csv
import math
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--input',
        default='logs/desired-figure8.csv',
        help='Recorded VRPN path CSV (default: %(default)s)',
    )
    parser.add_argument(
        '--output',
        default='logs/desired-figure8-waypoints.csv',
        help='Waypoint CSV to create (default: %(default)s)',
    )
    parser.add_argument(
        '--segments',
        type=int,
        default=16,
        help='Number of path segments, from 1 to 31 (default: %(default)s)',
    )
    parser.add_argument(
        '--max-extent',
        type=float,
        default=0.10,
        help='Maximum absolute local X or Y coordinate in metres (default: %(default)s)',
    )
    parser.add_argument(
        '--height',
        type=float,
        default=0.50,
        help='Fixed Z value written to each waypoint in metres (default: %(default)s)',
    )
    parser.add_argument(
        '--duration',
        type=float,
        default=40.0,
        help='Total planned duration represented by the waypoints in seconds (default: %(default)s)',
    )
    args = parser.parse_args()

    if not 1 <= args.segments <= 31:
        parser.error('--segments must be between 1 and 31')
    if args.max_extent <= 0.0:
        parser.error('--max-extent must be positive')
    if args.height < 0.0:
        parser.error('--height must be non-negative')
    if args.duration <= 0.0:
        parser.error('--duration must be positive')
    return args


def read_positions(input_path):
    with input_path.open(newline='', encoding='ascii') as input_file:
        reader = csv.DictReader(input_file)
        expected_columns = {'x_m', 'y_m'}
        if reader.fieldnames is None or not expected_columns.issubset(reader.fieldnames):
            raise ValueError('Input CSV must contain x_m and y_m columns')

        positions = []
        for line_number, row in enumerate(reader, start=2):
            try:
                positions.append((float(row['x_m']), float(row['y_m'])))
            except (TypeError, ValueError) as error:
                raise ValueError(f'Invalid position on CSV line {line_number}') from error

    if len(positions) < 2:
        raise ValueError('Input CSV must contain at least two positions')
    return positions


def cumulative_distances(positions):
    distances = [0.0]
    for start, end in zip(positions, positions[1:]):
        distances.append(distances[-1] + math.dist(start, end))
    return distances


def sample_by_distance(positions, segment_count):
    distances = cumulative_distances(positions)
    total_distance = distances[-1]
    if total_distance == 0.0:
        raise ValueError('Input path has no horizontal movement')

    samples = []
    source_index = 0
    for waypoint_index in range(segment_count + 1):
        target_distance = total_distance * waypoint_index / segment_count
        while (source_index < len(distances) - 2 and
               distances[source_index + 1] < target_distance):
            source_index += 1

        start_distance = distances[source_index]
        end_distance = distances[source_index + 1]
        fraction = (target_distance - start_distance) / (end_distance - start_distance)
        start = positions[source_index]
        end = positions[source_index + 1]
        samples.append((
            start[0] + fraction * (end[0] - start[0]),
            start[1] + fraction * (end[1] - start[1]),
        ))
    return samples, total_distance


def scale_to_local_coordinates(samples, max_extent):
    origin_x, origin_y = samples[0]
    offsets = [(x - origin_x, y - origin_y) for x, y in samples]
    raw_extent = max(max(abs(x), abs(y)) for x, y in offsets)
    if raw_extent == 0.0:
        raise ValueError('Sampled path has no horizontal extent')

    scale = max_extent / raw_extent
    return [(x * scale, y * scale) for x, y in offsets], scale


def write_waypoints(output_path, waypoints, height, duration):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    segment_duration = duration / (len(waypoints) - 1)
    with output_path.open('w', newline='', encoding='ascii') as output_file:
        writer = csv.writer(output_file)
        writer.writerow(['time_s', 'x_m', 'y_m', 'z_m', 'yaw_rad'])
        for index, (x, y) in enumerate(waypoints):
            writer.writerow([
                f'{index * segment_duration:.3f}',
                f'{x:.6f}',
                f'{y:.6f}',
                f'{height:.6f}',
                '0.000000',
            ])


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    positions = read_positions(input_path)
    sampled_positions, raw_distance = sample_by_distance(positions, args.segments)
    waypoints, scale = scale_to_local_coordinates(sampled_positions, args.max_extent)
    write_waypoints(output_path, waypoints, args.height, args.duration)

    max_x = max(abs(x) for x, _ in waypoints)
    max_y = max(abs(y) for _, y in waypoints)
    print(f'[INFO] Read {len(positions)} mocap samples from {input_path}')
    print(f'[INFO] Resampled {raw_distance:.3f}m of hand movement into {args.segments} segments')
    print(f'[INFO] Applied scale factor {scale:.6f}; local extent X={max_x:.3f}m, Y={max_y:.3f}m')
    print(f'[INFO] Wrote {len(waypoints)} fixed-height waypoints to {output_path}')
    print('[INFO] This file is offline only; it sends no commands to a Crazyflie.')


if __name__ == '__main__':
    main()
