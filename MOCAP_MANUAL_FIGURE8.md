# Manual Mocap Figure-8

This is the current working AIMSLab flight workflow. It uses the Crazyflie's
low-level commander: the pilot owns takeoff and landing thrust, while the
script uses OptiTrack/VRPN pose data to assist X/Y position, yaw, the 3 ft
pre-figure-8 climb, and figure-8 altitude correction.

The flight script is [`mocap_manual_thrust_assisted_figure8.py`](mocap_manual_thrust_assisted_figure8.py).
Its configuration lives at the top of that file. Do not copy constants from
older handoff notes without checking the script first.

## Setup

Install this repository's Python dependencies, including `motioncapture`.
`matplotlib` is optional but enables automatic 3D path images after each run.

Before a powered run:

- Close `cfclient` and any other program using the Crazyradio.
- Confirm Motive tracks the configured rigid body and VRPN is available.
- Check that the cage is clear and that an operator has a physical power-cut
  option ready.
- Confirm the URI, VRPN host, rigid-body name, and cage-corner values near the
  top of the flight script match the lab setup.

Run from the repository root:

```bash
python3 mocap_manual_thrust_assisted_figure8.py
```

The script writes a CSV to `flight_logs/` and, when matplotlib is available,
writes a matching `-3d-path.png` image. These are local experiment artifacts;
they are not committed to Git.

While the flight runs, the script starts `plot_crazyflie_3d_track.py` as a live
viewer and asks it to save the final 3D path image when the flight loop ends.
The console prints both output paths. If matplotlib is unavailable in the
plotter's Python environment, the flight still completes and the console
reports that the image could not be produced.

## Proven Flight Sequence

The current baseline is the successful run from 2026-07-13. It completed one
48-second figure-8 at roughly 3 ft, then returned to its figure-8 start point
and landed. Use this sequence:

1. Arm when prompted, then press `R` to ramp to ready thrust.
2. Establish a low, stable hover.
3. Press `T` to enable the 3 ft height helper. Wait until the on-screen status
   reports `3ft ready: YES`.
4. Press `F` once to start the figure-8 from the current position and height.
5. Press `F` again to stop the path, return to the figure-8 start point, and
   begin landing.

The figure-8 only starts when mocap is fresh and the drone is sufficiently
settled in horizontal and vertical speed. This is deliberate: starting while
the drone is still climbing produces a distorted path.

## Current Verified Baseline

The latest verified run used this sequence successfully:

- `R` ramped to the ready-thrust target and established a low hover.
- `T` engaged the pre-figure-8 height helper and settled near `0.91 m` above
  the recorded start position.
- One `F` press started a `48 s` figure-8. A second `F` press initiated the
  return-to-start and landing sequence.
- The path stayed close to its height target, recovered from one brief mocap
  dropout, and ended with `return_home_landing_complete`, not a safety stop.

`FIGURE8_RADIUS_X_M` and `FIGURE8_RADIUS_Y_M` describe the requested path, not
a guaranteed physical size. Before flight, the script reduces that request to
fit the configured cage bounds and tracking reserve. The verified run planned
and observed a horizontal path of about `5.4 m x 5.4 m`.

## Keyboard Controls

| Key | Action |
| --- | --- |
| `R` | Ramp to the ready-thrust target. |
| `T` | Toggle the pre-figure-8 3 ft height helper. |
| Up / Down | Before height hold: change raw thrust. During 3 ft hold or figure-8: nudge the height target. |
| PageUp | Larger upward thrust or height-target nudge. |
| PageDown | Normal descent ramp. |
| `F` | Start figure-8; when active, return to the figure-8 start and land. |
| `H` | Lock the current X/Y hold target. |
| `A` / `D` | Roll trim. |
| `W` / `S` | Pitch trim. |
| `J` / `L` | Yaw-target trim. |
| `C` | Clear attitude and yaw trims. |
| Space | Immediate zero-thrust command. |
| `Q` / Esc | Zero thrust and quit. |

## What the Script Uses From OptiTrack

The VRPN rigid-body pose is transformed into the local flight frame as:

```text
local X = -raw Y
local Y =  raw X
local Z =  raw Z
```

It logs the transformed position (`mocap_x`, `mocap_y`, `mocap_z`), raw rigid
body orientation as a normalized quaternion, pose age, frame count, controller
commands, safety state, and target/error data. The controller uses the position
and yaw derived from the quaternion; it does not send VRPN data directly to the
Crazyflie's estimator in this manual-thrust workflow.

## Boundaries and Safety

The active safety values are deliberately all visible at the top of the flight
script. In particular, cage bounds, stale-mocap handling, climb-rate protection,
and emergency zero-thrust behavior remain active. The hard height limits are
currently disabled by `ENFORCE_HEIGHT_LIMITS = False`; that is an intentional
experiment setting, not a claim that high-altitude flight is intrinsically safe.

`MOCAP_STALE_RESUME_FIGURE8_S` permits brief coverage gaps to recover without
pausing the figure-8 timeline. A prolonged stale interval levels the commands
and eventually initiates the configured safety descent.

## Repository Notes

`AIMSLAB_AUTONOMY_RUNBOOK.md` and `HANDOFF.md` preserve earlier high-level
commander and calibration work. They are useful background, but this document
and the constants in the manual-thrust script describe the current flight
baseline.
