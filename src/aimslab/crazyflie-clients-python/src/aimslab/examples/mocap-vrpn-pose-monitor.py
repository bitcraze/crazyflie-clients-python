#!/usr/bin/env python3
"""Print raw VRPN pose data for one OptiTrack rigid body.

This is a read-only diagnostic. It does not connect to or command a Crazyflie.
"""

import time

import motioncapture


HOST_NAME = "192.168.1.42:3883"
RIGID_BODY_NAME = "crazyflie_21"
PRINT_INTERVAL_SECONDS = 0.2


def main():
    print(f"[INFO] Connecting to VRPN at {HOST_NAME}...")
    mocap = motioncapture.connect("vrpn", {"hostname": HOST_NAME})
    print(f"[INFO] Waiting for rigid body {RIGID_BODY_NAME!r}. Press Ctrl+C to stop.")

    last_print = 0.0
    found_body = False

    try:
        while True:
            mocap.waitForNextFrame()
            body = mocap.rigidBodies.get(RIGID_BODY_NAME)
            if body is None:
                continue

            if not found_body:
                print(f"[INFO] Found rigid body: {RIGID_BODY_NAME}")
                found_body = True

            now = time.monotonic()
            if now - last_print < PRINT_INTERVAL_SECONDS:
                continue

            position = body.position
            quaternion = body.rotation
            print(
                "Position: "
                f"{position[0]:.3f} {position[1]:.3f} {position[2]:.3f} | "
                "Quaternion (x y z w): "
                f"{quaternion.x:.3f} {quaternion.y:.3f} "
                f"{quaternion.z:.3f} {quaternion.w:.3f}"
            )
            last_print = now
    except KeyboardInterrupt:
        print("\n[INFO] VRPN monitor stopped.")


if __name__ == "__main__":
    main()
