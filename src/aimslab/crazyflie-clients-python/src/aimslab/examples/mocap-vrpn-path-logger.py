#!/usr/bin/env python3
"""Record a hand-guided VRPN path to CSV without commanding a Crazyflie.

Keep the Crazyflie unarmed and move it through the desired path by hand. The
CSV contains time in seconds, position in meters, and the rigid-body quaternion.
"""

import argparse
import csv
import time
from pathlib import Path

import motioncapture


HOST_NAME = '192.168.1.42:3883'
RIGID_BODY_NAME = 'crazyflie_21'


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output',
        default='logs/desired-path.csv',
        help='CSV file to create (default: %(default)s)',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] Connecting to VRPN at {HOST_NAME}...')
    mocap = motioncapture.connect('vrpn', {'hostname': HOST_NAME})
    print(f'[INFO] Waiting for rigid body {RIGID_BODY_NAME!r}.')
    print(f'[INFO] Recording to {output_path}. Press Ctrl+C to stop.')

    start_time = time.monotonic()
    sample_count = 0
    found_body = False

    with output_path.open('w', newline='', encoding='ascii') as output_file:
        writer = csv.writer(output_file)
        writer.writerow([
            'elapsed_seconds', 'x_m', 'y_m', 'z_m', 'qx', 'qy', 'qz', 'qw'
        ])

        try:
            while True:
                mocap.waitForNextFrame()
                body = mocap.rigidBodies.get(RIGID_BODY_NAME)
                if body is None:
                    continue

                if not found_body:
                    print(f'[INFO] Found rigid body: {RIGID_BODY_NAME}')
                    found_body = True

                position = body.position
                quaternion = body.rotation
                writer.writerow([
                    f'{time.monotonic() - start_time:.6f}',
                    f'{position[0]:.6f}', f'{position[1]:.6f}', f'{position[2]:.6f}',
                    f'{quaternion.x:.6f}', f'{quaternion.y:.6f}',
                    f'{quaternion.z:.6f}', f'{quaternion.w:.6f}',
                ])
                sample_count += 1

                if sample_count % 100 == 0:
                    output_file.flush()
                    print(
                        f'[INFO] Recorded {sample_count} samples; '
                        f'latest position=({position[0]:.3f}, '
                        f'{position[1]:.3f}, {position[2]:.3f})'
                    )
        except KeyboardInterrupt:
            output_file.flush()
            print(f'\n[INFO] Path recording stopped after {sample_count} samples.')


if __name__ == '__main__':
    main()
