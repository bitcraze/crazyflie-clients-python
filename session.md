# Session Notes

Date: 2026-05-12
Repo: `/home/alwin-raj/Desktop/drone/crazyflie-clients-python`
Branch: `aimslab/work`

## Goal

Work through the local Crazyflie client repo, review recent `alwnraj` changes, get the repo running, validate controller input, and diagnose mocap flight behavior.

## 2026-07-13 Current Manual Figure-8 Baseline

The active powered-flight script is `mocap_manual_thrust_assisted_figure8.py`.
The verified sequence is: press `R` for ready thrust, establish a low hover,
press `T` for the mocap 3 ft helper and wait for `3ft ready: YES`, then press
`F` to start the figure-8. Pressing `F` again returns to the figure-8 start and
lands.

The latest verified run completed one 48-second cage-limited figure-8 at about
`0.91 m` above the start height, recovered from a brief mocap dropout, and
completed the return-and-land sequence without a safety descent. The configured
figure-8 dimensions are requests that are shrunk at runtime to fit the cage;
the observed path was about `5.4 m x 5.4 m` in local X/Y.

Flight CSVs and visualizations are local-only artifacts under `flight_logs/`.
The script launches `plot_crazyflie_3d_track.py` for a live/final 3D view when
matplotlib is available.

## Commit Review

Reviewed reachable commits by author `alwnraj`.

Found one reachable commit:

- `e801be6` - `Fix controller safety and mocap trajectory startup`

Review findings:

1. High: `mocap-extpose-figure8.py` now skips the pre-takeoff relocation to the computed safe launch point and instead takes off from the current position before later safety checks.
2. Medium: `test_flight_with_controller.py` now waits for low thrust after arming, which can leave the Crazyflie armed indefinitely if the thrust axis is never detected or mapped wrong.
3. Medium: controller autodiscovery now picks the first `/dev/input/js*` device without verifying it is actually the Logitech F310.

## Repo Run Path

Main app / GUI:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cfclient
```

Alternative GUI launch:

```bash
python3 -m cfclient.gui
```

Custom controller workflow in this repo:

```bash
./RUN_THIS_FIRST.sh
python3 demo_controller_live.py
python3 test_flight_with_controller.py
```

## Radio / Connectivity Debugging

Initial mocap example attempts:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-example.py
```

Observed issues:

- `Too many packets lost`
- `Resource busy`

Interpretation:

- `Too many packets lost` happened while opening the Crazyflie radio link, before mocap logic.
- `Resource busy` indicated the Crazyradio dongle was already held by another process, likely `cfclient` or a previous crashed script.

Later state:

- radio link became stable
- mocap example connected
- VRPN saw rigid body `crazyflie_21`
- estimator converged successfully

Warnings observed during successful connection:

- VRPN minor version mismatch warning
- `platform.send_arming_request` deprecation warning
- Crazyflie reported CRTP protocol version `9`, causing legacy fallback
- VRPN cleanup warning on shutdown

## Controller Detection Debugging

Problem:

- Logitech controller appeared not to work with `test_logitech_controller.py`

Initial discovery:

```bash
ls -la /dev/input/js*
```

showed:

- `/dev/input/js0`

The test script read `/dev/input/js0` but showed:

- empty device name
- `Axes: 2, Buttons: 2`
- no useful button/stick response

Device identification:

`/dev/input/js0` turned out to be:

- `Melfas LGD AIT Touch Controller Mouse`

So the script was reading the wrong joystick-class device, not the Logitech pad.

Root cause found by user:

- the Logitech controller was plugged into a dead USB port

After moving to a working port:

- the controller worked correctly

## Manual Controller Flight Validation

The direct controller flight path worked through:

```bash
python3 test_flight_with_controller.py
```

Key conclusion:

- low-level command streaming via `cf.commander.send_setpoint(...)` works on this setup

Observed behavior from log output:

- roll, pitch, yaw, and thrust all responded
- cleanup and disarm worked

Important interpretation:

- the printed `Alt: ...` values in `test_flight_with_controller.py` are not trustworthy as real altitude truth for flight validation
- the useful signal from that test was that manual command channels were reaching the drone correctly

Manual flight tuning learned by user:

- about `57%` thrust is the practical hover / liftoff sweet spot
- pitch trim of about `1.8` helps keep the drone stable

## Mocap High-Level Commander Diagnosis

Problem:

- `mocap-map-boundaries.py` armed and printed takeoff messages, but the drone did not actually rise
- reported position stayed near ground level, around `z ~= 0.03`

Root cause identified:

- controller/manual script uses low-level `send_setpoint(...)`
- mocap scripts use high-level commander functions like:
  - `takeoff()`
  - `go_to()`
  - `start_trajectory()`
- GUI code in `src/cfclient/ui/tabs/FlightTab.py` enables `commander.enHighLevel = 1` before using takeoff
- mocap scripts were not enabling `commander.enHighLevel`

Conclusion:

- on this firmware/setup, high-level motion commands were being ignored until `commander.enHighLevel` was enabled

## Code Changes Made

Made the minimal possible change: enabled the high-level commander in these mocap scripts before issuing high-level commands:

- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-example.py`
- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-map-boundaries.py`
- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-boundary-aware.py`
- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-figure8.py`

Nature of change:

- added helper `enable_high_level_commander(cf)`
- called `cf.param.set_value('commander.enHighLevel', '1')`
- no other flight logic was intentionally changed

## Result After High-Level Enablement

Re-tested:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-example.py
```

Result:

- drone took off quickly and crashed

Interpretation:

- previous "not moving" issue is fixed
- high-level commander is now actively executing commands
- current failure is flight behavior / state estimation / frame alignment, not command delivery

## Mocap / Pose Data Observations

User-reported pose at takeoff on ground:

- Quaternions: `0.282, -0.015, 0.09, 0.959`
- Position: `-0.107 -0.941 0.033`

User-reported pose shortly after takeoff in mid-air:

- Quaternions: `-0.789, -0.005, -0.012, 0.614`
- Position: `-0.369 0.168 0.091`

Important interpretation:

- a small vertical takeoff should mostly increase `z`
- instead, `y` changed by about `+1.11 m`
- `x` changed by about `-0.26 m`
- `z` changed only from about `0.033` to `0.091`

This strongly suggests frame / pose interpretation problems, such as:

- rigid body origin offset
- wrong quaternion / axis convention from VRPN
- mismatch between mocap world frame and estimator expectations
- bad yaw / orientation alignment causing lateral correction during takeoff

## Later Calibration Findings

User later established a more reliable cage-center reference point:

- cage center reports approximately `0.000 0.000 0.037`
- first reported horizontal value corresponds to `y`
- second reported horizontal value corresponds to `x`
- the reported floor baseline for `z` is about `0.037`

Working interpretation:

- the cage center is the mocap origin in `x/y`
- `z = 0.037` is effectively the floor-level baseline for this rigid body setup
- practical height above floor should be treated as:
  - `height_above_floor = reported_z - 0.037`

Examples:

- reported `z = 0.037` -> on the floor
- reported `z = 0.137` -> about `10 cm` above the floor
- reported `z = 0.837` -> about `80 cm` above the floor

This makes the `z` offset itself unsurprising; the larger remaining concern is orientation alignment.

## Orientation Validation Attempts

The user next suspected that `x/y` might actually be fine and that orientation was the real issue.

### First orientation check

User held the drone at a maintained height and reported:

- rightside up:
  - quaternion: `0.989 0.039 0.003 -0.140`
- upside-down:
  - quaternion: `0.543 0.835 0.050 -0.065`

Important caveat:

- upside-down readings were not continuous because the OptiTrack cameras are above the cage
- this was not a useful yaw-alignment test because flipping upside down mixes roll/pitch and visibility issues

### Flat yaw-style orientation checks

The next recommendation was to keep the drone level and rotate it in 90 degree steps:

- nose forward
- nose right
- nose backward
- nose left

First reported set:

- nose forward:
  - quaternion: `0.806 -0.068 -0.046 0.586`
  - position: `0.014 -0.019 0.146`
- nose right:
  - quaternion: `0.995 0.002 0.005 -0.099`
  - position: `0.035 -0.049 0.150`
- nose backward:
  - quaternion: `0.688 -0.182 0.727 -0.012`
  - position: `0.015 -0.037 0.133`
- nose left:
  - quaternion: `0.565 0.478 0.572 0.346`
  - position: `0.040 0.002 0.138`

Issue with that set:

- the user noted the backward sample was actually "nose up"
- that means pitch contaminated the test, so it did not isolate yaw cleanly

Second reported set, again with quaternions from OptiTrack:

- nose forward:
  - quaternion: `0.776 -0.020 0.025 0.630`
  - position: `0.029 -0.017 0.170`
- nose right:
  - quaternion: `0.999 -0.020 -0.008 -0.023`
  - position: `0.034 -0.032 0.152`
- nose backward:
  - quaternion: `0.760 0.065 -0.644 -0.065`
  - position: `0.013 -0.021 0.170`
- nose left:
  - quaternion: `0.567 0.555 -0.375 0.480`
  - position: `0.036 -0.016 0.149`

Issue with that set:

- the user noted the backward case was actually "nose facing down"
- again, that means the test was not a clean level-only yaw sweep

What these orientation tests do show:

- position stayed relatively stable during manual holding/rotation
- horizontal position changes were only a few centimeters
- `z` stayed in a narrow band

Current interpretation:

- position tracking looks much more credible than it did during the autonomous crash
- orientation tracking is changing, but has not yet been validated in a clean way
- the autonomous takeoff/crash could still be caused by bad attitude alignment, wrong forward-direction assumptions, or quaternion/frame convention mismatch

## Current Best Understanding

What is confirmed working:

- repo builds and runs in the local venv
- Crazyradio link works
- mocap feed connects
- rigid body `crazyflie_21` is seen
- Kalman estimator can converge
- Logitech controller works
- low-level manual control works
- cage center / floor baseline are partially calibrated:
  - `y ~= 0.000`, `x ~= 0.000`, `z ~= 0.037` at cage center on the floor

What is still not trustworthy:

- autonomous mocap takeoff
- high-level trajectory flight
- mocap pose / orientation alignment for autonomous stabilization
- OptiTrack quaternion interpretation for level yaw orientation

## Recommended Next Steps

1. Do not run autonomous mocap trajectory scripts again yet:
   - `mocap-extpose-example.py`
   - `mocap-extpose-figure8.py`

2. Validate mocap pose with props off:
   - stream pose continuously
   - move the drone by hand along one axis at a time
   - verify `x`, `y`, and `z` change in expected directions
   - rotate yaw by hand and verify orientation changes cleanly while the drone stays level
   - avoid upside-down or pitched tests; they do not isolate yaw

3. Do a conservative props-on manual test:
   - use controller only
   - use the known hover thrust around `57%`
   - use pitch trim around `1.8`
   - verify whether mocap `z` rises cleanly without large `x/y` jumps

4. Repeat the orientation check on a flat surface if possible:
   - keep the drone level
   - record four orientations in 90 degree steps
   - confirm position stays nearly fixed while the quaternion changes

5. Inspect and correct the mocap pose mapping before further autonomous tests.

6. After frame alignment is trustworthy, retry a minimal autonomous action:
   - takeoff and land only
   - no trajectory upload
   - no figure-8

7. Longer term:
   - update Crazyflie firmware to reduce protocol/deprecation mismatch risk

## Current Working Tree

Modified files:

- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-example.py`
- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-map-boundaries.py`
- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-boundary-aware.py`
- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-figure8.py`

Added file:

- `session.md`

## 2026-05-13 Update: Guarded Mocap Takeoff Script

User request:

- add the next-step script for a safe mocap-driven takeoff test
- update this session file so a future agent has context
- commit and push the change to GitHub

Reason for this step:

- Motive/VRPN pose is now confirmed to stream successfully
- high-level commander enablement made the drone respond to autonomous commands
- the autonomous response was not yet safe; the drone took off quickly and crashed
- therefore the next script should not run trajectories or horizontal paths

Added script:

- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-takeoff.py`

Purpose:

- connect to the Crazyflie over Crazyradio
- connect to Motive/VRPN using:
  - `host_name = '192.168.1.42:3883'`
  - `mocap_system_type = 'vrpn'`
  - `rigid_body_name = 'crazyflie_21'`
- stream full external pose into the Crazyflie with `cf.extpos.send_extpose(...)`
- require fresh mocap pose before arming
- require the pose to be stable for a short window before takeoff
- enable the Kalman estimator and high-level commander
- reset the estimator while external pose is flowing
- log `stateEstimate.x/y/z` and print it beside the mocap position
- require the operator to press ENTER before arming
- take off only to a low target:
  - floor baseline: `FLOOR_Z = 0.037`
  - height above floor: `TAKEOFF_HEIGHT_ABOVE_FLOOR = 0.15`
  - command target: `TAKEOFF_Z = 0.187`
- hover briefly
- land and disarm

Safety guards in the script:

- aborts if mocap pose is stale
- aborts if start pose is outside the configured cage bounds
- aborts if pose is not stable enough before takeoff
- aborts and lands if live pose leaves bounds during takeoff/hover
- aborts and lands if horizontal drift exceeds `MAX_HORIZONTAL_DRIFT = 0.35`
- does not upload trajectories
- does not command horizontal motion

Current default cage bounds in the script:

```python
CAGE_BOUNDS = {
    'x_min': -1.5,
    'x_max': 1.5,
    'y_min': -1.5,
    'y_max': 1.5,
    'z_min': 0.0,
    'z_max': 2.0,
}
SAFETY_MARGIN = 0.20
```

These are intentionally conservative placeholders. They should be updated with the measured cage bounds once frame alignment and low takeoff are trustworthy.

Recommended run command:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-takeoff.py
```

Recommended physical setup before running:

- Motive is running
- rigid body `crazyflie_21` is visible
- Crazyradio is not held by `cfclient` or another script
- drone is near cage center
- props on only when ready for the low takeoff test
- operator has a physical emergency stop / power-off option ready

How to interpret the output:

- mocap and `stateEstimate` positions should be close after estimator reset
- during takeoff, `z` should rise clearly
- `x/y` should not jump or drift significantly
- if the script lands due to stale pose, boundary violation, or drift, do not proceed to trajectory scripts

Next step after this script succeeds:

1. repeat the guarded takeoff a few times from cage center
2. reduce or explain any mismatch between mocap position and `stateEstimate`
3. add a guarded small horizontal move script:
   - take off low
   - move only `10 cm` along one axis
   - return to start
   - land
4. only after that, revisit boundary mapping or figure-8 trajectories

## 2026-05-13 Update: Guarded Raw-Thrust Test Script

User asked whether thrust could be controlled directly while keeping the mocap
guards and estimator setup the same.

Added script:

- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-thrust-test.py`

Purpose:

- keep the same Motive/VRPN pose streaming path as `mocap-guarded-takeoff.py`
- keep the Kalman estimator reset and `stateEstimate.x/y/z` comparison logging
- keep the fresh-pose, stable-pose, cage-boundary, stale-pose, and horizontal
  drift guards
- replace high-level `takeoff(...)` with low-level
  `cf.commander.send_setpoint(roll, pitch, yawrate, thrust)`
- command zero roll, zero pitch, and zero yaw rate while ramping raw thrust

Default behavior:

- target height is intentionally lower than the high-level takeoff script:
  - `TARGET_HEIGHT_ABOVE_FLOOR = 0.12`
  - `TARGET_Z = 0.157`
- raw thrust ramp starts at `START_THRUST = 20000`
- ramp ceiling defaults to `MAX_THRUST = 34000`
- thrust increments by `THRUST_STEP = 400` every `RAMP_INTERVAL = 0.08s`
- the script cuts thrust if the target height is reached, if any guard trips,
  or if the operator interrupts it

Recommended run command:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-thrust-test.py
```

Important safety note:

- this is not altitude hold; it is a raw thrust ramp with mocap guardrails
- if it does not lift by `MAX_THRUST`, the script aborts instead of continuing
  into the user's observed hover/liftoff range
- tune `MAX_THRUST` upward only after confirming the ramp behavior is stable

Review / verification before commit:

- `mocap-guarded-thrust-test.py` was reviewed as an uncommitted change
- no actionable review findings were found
- syntax check passed with `python3 -m py_compile`
- whitespace check passed with `git diff --check`

## 2026-05-14 Update: Motor Lockout Diagnosis

Problem observed:

- `mocap-guarded-thrust-test.py` connected to Crazyflie and OptiTrack/VRPN
- mocap pose was fresh and stable
- the script armed, counted down, and ramped raw thrust up to `39000`
- mocap `z` stayed at the floor baseline around `0.037m`
- motors did not spin

Diagnostic changes made to the guarded thrust script:

- changed the default URI to match the known-working controller path:
  - `radio://0/80/2M`
- added a 3 second command-line preflight countdown
- added pitch trim from manual testing:
  - `PITCH_DEG = 1.8`
- raised the raw thrust test cap to the manually observed low-liftoff range:
  - `MAX_THRUST = 39000`
- added a `manual_percent` control mode for comparing against GUI-style
  percentage thrust
- temporarily disabled mocap feeding and Kalman setup:
  - `FEED_MOCAP_TO_CRAZYFLIE = False`
  - `USE_KALMAN_ESTIMATOR = False`
- kept mocap active as an external safety monitor for pose, bounds, stale data,
  and drift checks

Root cause found:

- the Crazyflie was locked out
- `cfclient` showed the locked state
- rebooting the Crazyflie cleared the lockout
- after reboot, the drone/motors worked again

Current conclusion:

- the repeated "motors did not move" result was most likely caused by the
  Crazyflie lockout state, not by the low-level `send_setpoint(...)` command
  path itself
- before interpreting script failures, verify in `cfclient` that the Crazyflie
  is not locked and that motors respond to manual thrust

Recommended next test:

1. close `cfclient` so the Python script has exclusive Crazyradio access
2. reboot the Crazyflie
3. place the drone at cage center with OptiTrack tracking `crazyflie_21`
4. run:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-thrust-test.py
```

Expected behavior:

- motors should begin responding during the thrust ramp
- mocap `z` should rise from around `0.037m`
- the script should cut thrust once `TARGET_Z = 0.157m` is reached
- press `Ctrl+C` immediately if the drone moves laterally, rises too fast, or
  looks unstable

## 2026-05-14 Update: Manual Flight Logging Plan

User asked if a logging script could record a GUI-assisted Logitech controller
test flight so the results can be interpreted later and used to improve the
autonomous scripts.

Important constraint:

- when `cfclient` is connected and controlling the drone through Crazyradio, a
  second Python process should not also try to own the Crazyradio link
- therefore the logger should not command the drone or connect to Crazyflie by
  default during GUI-assisted flight

Added script, later renamed for clarity:

- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guided-manual-flight-logger.py`

Purpose:

- read Logitech F310 joystick events from `/dev/input/js1` by default
- connect to Motive/VRPN at `192.168.1.42:3883`
- track rigid body `crazyflie_21`
- write a CSV log under `flight_logs/`
- record controller command values alongside mocap position, quaternion, derived
  height above floor, derived mocap velocity, and horizontal distance from the
  start position
- label each CSV row with a guided test phase:
  `floor_baseline`, `gentle_takeoff`, `low_hover`, `pitch_forward_back`,
  `roll_right_left`, `yaw_right_left`, `final_hover`, or `landing`
- keep a `--freeform` mode available for one continuous unlabeled flight

Recommended workflow:

1. start Motive and confirm rigid body `crazyflie_21` is visible
2. start `cfclient` and connect/control the drone with the Logitech controller
3. in a second terminal, run:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guided-manual-flight-logger.py
```

4. follow the terminal prompts and press Enter to advance between phases:
   - floor baseline, props idle
   - gentle vertical takeoff
   - low hover
   - small pitch forward/back
   - small roll right/left
   - small yaw right/left
   - final hover
   - landing and floor-still logging
5. after landing, press Enter at the final prompt to stop logging cleanly
6. provide the generated CSV file for analysis

What the CSV can help estimate:

- actual liftoff thrust range
- approximate hover thrust range
- vertical response delay from thrust changes
- horizontal drift during nominal hover
- whether pitch/roll commands correlate with the expected mocap x/y motion
- whether yaw inputs create unexpected translation or frame-alignment symptoms

## 2026-05-14 Update: Configurable Guarded Thrust Test

User asked to make the guarded thrust script more customizable for thrust and
orientation variables.

Updated script:

- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-thrust-test.py`

Changes:

- kept the test configuration as top-of-file constants so the operator can edit
  the script directly between runs
- grouped the editable thrust settings:
  - `CONTROL_MODE`
  - `START_THRUST`
  - `MAX_THRUST`
  - `THRUST_STEP`
  - `MANUAL_THRUST_PERCENT`
- grouped the editable orientation settings:
  - `ROLL_DEG`
  - `PITCH_DEG`
  - `YAWRATE_DEG_PER_S`
- changed raw-thrust defaults back into the valid Crazyflie raw thrust range:
  - `START_THRUST = 30000`
  - `MAX_THRUST = 39000`
  - raw thrust is validated against `0..65535`
- fixed `manual_percent` mode so zero-thrust priming sends `0%` instead of the
  configured manual thrust percentage
- startup output now prints the effective thrust range, control mode, manual
  percent, roll, pitch, and yaw-rate values for the run

Run command:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-thrust-test.py
```

## 2026-05-19 Update: Mocap Vertical Thrust Mapper

Built and tuned a root-level manual thrust mapper:

- `mocap_vertical_thrust_mapper.py`

Purpose:

- keep thrust under manual keyboard control
- read OptiTrack/VRPN mocap from `crazyflie_21@192.168.1.42:3883`
- log thrust, mocap pose, battery, drift, velocity, yaw, and correction terms to
  `flight_logs/mocap-vertical-thrust-map-*.csv`
- optionally run a conservative mocap-based horizontal hold loop using roll and
  pitch while leaving thrust manual

Important tuning result:

- `hold-xy` with default pitch sign moved backward too aggressively
- flipping pitch sign with `--pitch-sign -1` produced near-correct liftoff,
  hover, and landing
- the mapper defaults were updated to the successful tuning values:
  - `kp_xy = 5.0`
  - `kd_xy = 2.0`
  - `max_angle_deg = 5.0`
  - `roll_sign = 1.0`
  - `pitch_sign = -1.0`

Most useful run command now:

```bash
python3 mocap_vertical_thrust_mapper.py --mode hold-xy
```

Latest useful log:

- `flight_logs/mocap-vertical-thrust-map-20260519-104706.csv`
- reached `z=0.196m` at `35000` raw thrust
- drift at max height was about `0.065m`
- drift guard later stopped the run near `0.199m`, which is close to the
  configured `0.20m` safety limit

## 2026-05-19 Update: Hold-XY and Figure-8 Development

The working focus moved from high-level autonomous takeoff to low-level,
manual-thrust flight with mocap-assisted horizontal correction.

Current active script:

- `mocap_vertical_thrust_mapper.py`

Current design:

- keyboard controls raw thrust only
- OptiTrack/VRPN supplies pose for logging and safety guards
- optional `hold-xy` mode uses mocap position, yaw, and velocity to command
  roll/pitch corrections
- optional `figure8` mode moves the horizontal target after the drone is already
  airborne
- all runs write detailed CSV logs under `flight_logs/`

Current controls:

- Up / Down: small thrust step
- PageUp / PageDown: large thrust step
- Space: immediate thrust cut to zero
- `q` / Esc: immediate cut, disarm, and exit
- normal landing should use PageDown, not `q`

Important script defaults / behavior:

- URI: `radio://0/80/2M`
- VRPN host: `192.168.1.42:3883`
- rigid body: `crazyflie_21`
- default mode remains `guard-only`
- useful test mode is `hold-xy`
- default XY tuning:
  - `kp_xy = 5.0`
  - `kd_xy = 2.0`
  - `max_angle_deg = 5.0`
  - `roll_sign = 1.0`
  - `pitch_sign = -1.0`
- `--max-commanded-thrust` caps keyboard thrust commands
- `--max-height-above-start` provides a mocap-based altitude ceiling
- `--control-activation-height` delays XY roll/pitch correction until the drone
  is actually airborne
- when XY control activates, the target is reset to the current airborne
  position instead of the floor-start position
- drift guard remains active before XY control activation, so low-altitude
  sliding or mocap jumps still abort the run

CSV logging now includes:

- raw thrust and thrust percent
- commanded roll/pitch/yawrate
- mocap position, quaternion, yaw, pose age, and frame count
- target position and target error
- XY-control active flag
- figure-8 active flag
- drift from flight-start position
- estimated horizontal velocity
- body-frame error and body-frame velocity used by the controller
- battery voltage
- Crazyflie `stateEstimate.z`

Important debugging results:

- The earlier "motors do not move" issue was not the script command path; the
  Crazyflie had been locked in the GUI and needed a reboot.
- A later no-lift issue was caused by props installed incorrectly. After fixing
  the props, the drone generated thrust and flew.
- Battery sag matters. Runs starting around `4.0V` sagged into the `3.65V`
  range, reducing thrust authority.
- User observed that above about `60%` thrust the drone climbs aggressively.
- Practical liftoff/hover region from logs and manual testing is roughly
  `33000..36000` raw thrust, but it varies with battery state.

Representative log analysis:

- `flight_logs/mocap-vertical-thrust-map-20260519-121256.csv`
  - best larger manual run
  - reached `z=1.489m`
  - returned close to the start in horizontal position
  - max thrust around `39000`
  - battery dipped to about `3.50V`
- `flight_logs/mocap-vertical-thrust-map-20260519-123210.csv`
  - first real figure-8 attempt
  - figure-8 activated and logged
  - max height around `0.31m`
  - failed on horizontal drift / target error near `0.40m`
  - conclusion: path was too aggressive for current controller tuning
- `flight_logs/mocap-vertical-thrust-map-20260519-123812.csv`
  - figure-8 tracking was acceptable horizontally
  - failed because height exceeded `0.80m`
  - conclusion: vertical thrust needed a lower cap / smaller steps
- `flight_logs/mocap-vertical-thrust-map-20260519-124418.csv`
  - command cap limited thrust too much
  - never reached figure-8 trigger height
  - failed on target error before becoming useful as a figure-8 test
- `flight_logs/mocap-vertical-thrust-map-20260519-125645.csv`
  - `pitch_sign=-1` looked better than `pitch_sign=+1`
  - still mostly low-altitude motion and floor-contact/sliding
  - motivated the airborne activation gate
- `flight_logs/mocap-vertical-thrust-map-20260519-130745.csv`
  - XY activation never occurred because height only rose about `0.026m`
  - drift reached over `2m` because the first activation patch also delayed the
    drift guard
  - fixed by keeping drift guard active before XY activation
- `flight_logs/mocap-vertical-thrust-map-20260519-131035.csv`
  - latest analyzed run
  - XY control activated correctly at `14.67s`
  - max height was `0.123m`, about `0.086m` above start
  - max/final drift reached `0.598m` against a `0.600m` guard
  - final thrust was capped at `35000`
  - battery sagged to about `3.65V`
  - conclusion: structurally correct, but still underpowered / too low for
    stable hold

Latest recommended hold-XY command:

```bash
python3 mocap_vertical_thrust_mapper.py \
  --mode hold-xy \
  --kp-xy 12.0 \
  --kd-xy 6.0 \
  --max-angle-deg 10.0 \
  --pitch-sign -1.0 \
  --roll-sign 1.0 \
  --control-activation-height 0.03 \
  --max-horizontal-drift 0.60 \
  --max-target-error 0.60 \
  --max-height-above-start 0.35 \
  --max-commanded-thrust 36000 \
  --step 250 \
  --big-step 500
```

How to fly the current test:

1. Start with a fresh battery if possible.
2. Close `cfclient`.
3. Confirm Motive tracks `crazyflie_21`.
4. Run the command above.
5. Use PageUp only until the drone lifts cleanly.
6. Stop increasing thrust once it is airborne.
7. Use PageDown to descend.
8. Use `q` only as an immediate cut/disarm path, not as normal landing.

Current success criterion before returning to figure-8:

- one clean `hold-xy` run
- height stays below about `0.35m` above start
- drift stays under roughly `0.25m` for at least `10..15s`
- battery remains healthy enough that commanded thrust still has authority

Recommended next implementation if hold-XY remains inconsistent:

- add a manual `h` key to activate XY hold after the user visually confirms the
  drone is airborne
- optionally add a manual `f` key to start figure-8 after a stable hold
- keep automatic height-based activation as a fallback

## 2026-05-21 Stop Point: Mocap-Assisted Low-Level Hold Not Working

The recent work focused on manual-thrust flight with mocap-assisted X/Y hold,
using `mocap_vertical_thrust_mapper.py` as the active low-level control script.
The user ultimately reported that this approach is not working and asked to stop
and update the notes/handoff.

### What Was Tried

- Continued using low-level `cf.commander.send_setpoint(roll, pitch, yawrate, thrust)`
  instead of high-level commander, because high-level takeoff had previously been
  unstable/crashy on this setup.
- Added/used detailed CSV logging for every run under `flight_logs/`.
- Added slow PageDown descent behavior so PageDown ramps thrust down instead of
  cutting immediately.
- Added immediate X/Y hold from the flight-start mocap position.
- Added low-altitude roll/pitch angle caps to avoid skating hard while the drone
  is still on or near the floor.
- Added aggressive and recovery gain tiers for larger X/Y error.
- Added `--body-yaw-offset-deg` and then `--fixed-body-yaw-deg` after logs showed
  mocap yaw/rigid-body yaw could jump or disagree with the physical nose direction.
- Tried using known cage/world mapping from no-flight calibration:
  - physical front = mocap `-Y`
  - physical back = mocap `+Y`
  - physical left = mocap `+X`
  - physical right = mocap `-X`
  - height = mocap `+Z`

### Important Logs / Observations

Recent logs repeatedly showed that the drone often did not become cleanly airborne
before drifting/skidding enough to trigger guards or require stopping:

- `flight_logs/mocap-vertical-thrust-map-20260521-115415.csv`
  - no clean liftoff; max height above start about `0.016 m`
  - X/Y control was delayed by height in that run, so roll/pitch stayed zero
  - drift reached the guard while near the floor
- `flight_logs/mocap-vertical-thrust-map-20260521-115703.csv`
  - no clean liftoff; max height above start about `0.005 m`
  - X/Y hold was active and commanding roll/pitch
  - target error reached about `0.182 m`
- `flight_logs/mocap-vertical-thrust-map-20260521-133221.csv`
  - no clean liftoff; max height above start about `0.003 m`
  - drift reached about `0.191 m`, mostly mocap `+Y`
  - mocap yaw/rigid-body yaw jumped near the end, suggesting orientation from the
    marker solve is not reliable enough to drive correction directly during takeoff

### Mocap Coverage Finding

No-flight coverage logging showed real tracking problems on the physical left side
of the cage. VRPN can keep returning stale/old pose values while `mocap_age_s`
climbs, so a pose may look numerically valid while no fresh tracking is arriving.
The physical left side / mocap `+X` region should not be used for flight until
coverage is fixed.

The user added more markers to the Crazyflie. After marker changes, the rigid body
must be rebuilt/redefined in Motive before trusting orientation or coverage logs.

### Current Conclusion

The current mocap-assisted low-level hold approach is not producing reliable
hover. More gain, stronger recovery tiers, and yaw offsets have not solved the
basic issue. The likely blockers are a combination of:

- poor or inconsistent mocap coverage in parts of the cage
- rigid-body orientation/yaw instability from marker geometry or Motive solve
- ground-effect / floor-skid behavior before the vehicle has real control authority
- possible remaining body-frame sign/orientation mismatch
- trying to correct X/Y before the system has a trustworthy pose/orientation frame

Do not continue escalating gains or angle limits as the main strategy. It risks
turning uncertainty into harder crashes.

### Recommended Next Direction

Pause flight attempts and return to no-flight validation:

1. Rebuild the Crazyflie rigid body in Motive after the marker changes.
2. Re-run coverage check in the smaller intended flight volume only.
3. Re-run guided world-frame/orientation calibration with the nose physically
   pointed toward cage front.
4. Verify mocap yaw stability by hand: keep the drone on the ground, nose front,
   then move it through the intended flight volume and confirm yaw does not jump.
5. Only after fresh pose and yaw are stable, run a very small manual hover test.

If software work continues, prefer making a diagnostic script that only logs and
prints live pose/yaw/coverage quality in the intended flight box. Avoid further
autonomous or assisted roll/pitch flight tuning until the mocap pose quality is
proven stable.

## 2026-05-21 Update: Manual-Thrust Assisted Figure-8 Script

After the no-flight coverage discussion and marker updates, the working direction
shifted to a simpler root-level script where the pilot owns vertical thrust and
the script assists only roll, pitch, yaw, safety checks, logging, and the eventual
tiny figure-8.

Active script:

- `mocap_manual_thrust_assisted_figure8.py`

Design intent:

- manual raw thrust only; no high-level commander takeoff
- mocap-assisted X/Y hold using low-level `send_setpoint(...)`
- yaw hold based on the start heading
- optional tiny figure-8 after stable hover
- editable top-of-file constants instead of CLI-heavy tuning
- detailed CSV logging for every run under `flight_logs/`

Important current constants:

- URI: `radio://0/80/2M`
- VRPN: `crazyflie_21@192.168.1.42:3883`
- `MAX_MANUAL_THRUST = 39000`
- `TAKEOFF_READY_THRUST = 33000`
- `SMALL_THRUST_STEP = 150`
- `BIG_THRUST_STEP = 1500`
- `DESCENT_RAMP_RAW_PER_S = 700.0`
- `MAX_XY_DRIFT_M = 0.28`
- `MAX_TARGET_ERROR_M = 0.22`
- `MAX_HEIGHT_ABOVE_START_M = 0.35`
- `MOCAP_STALE_TIMEOUT_S = 0.30`
- `MOCAP_STALE_GRACE_S = 1.50`
- figure-8 is intentionally tiny: `0.04m x 0.03m`, `32s` period

Keyboard controls:

- `R`: jump to ready thrust near liftoff
- Up / Down: fine thrust changes
- PageUp: larger thrust increase
- PageDown: slow descent ramp, not immediate cut
- `A` / `D`: roll trim down/up by `0.5 deg`
- `W` / `S`: pitch trim up/down by `0.5 deg`
- `J` / `L`: yaw target offset left/right by `5 deg`
- `C`: clear manual roll/pitch/yaw trims
- `H`: lock current X/Y as hold target
- `F`: toggle the tiny figure-8, only after stable hover
- Space: emergency thrust cut
- `Q` / Esc: cut, disarm, and exit

Stale mocap handling:

- if mocap age exceeds `0.30s`, the script enters `mocap-stale` mode
- in stale mode it stops figure-8, clears velocity/integral state, and commands
  neutral roll/pitch/yaw while preserving manual thrust control
- PageDown, thrust keys, Space, and Q still work while stale
- stale rows are still written to CSV with `mocap_status = stale`
- if mocap stays stale for more than `1.50s`, the script raises an error and the
  cleanup path cuts thrust and disarms
- if mocap reacquires after a longer stale gap, the script re-locks current X/Y
  instead of snapping back to an old target

New logging fields added with the trim controls:

- `mocap_status`
- `manual_roll_trim_deg`
- `manual_pitch_trim_deg`
- `manual_yaw_offset_deg`

The script was syntax-checked with:

```bash
python3 -m py_compile mocap_manual_thrust_assisted_figure8.py
```

Recommended next run:

```bash
python3 mocap_manual_thrust_assisted_figure8.py
```

Suggested first test behavior:

1. Close `cfclient`.
2. Confirm Motive tracks `crazyflie_21`.
3. Start with a fresh battery and a physical power-off option ready.
4. Press `R`, then use small Up taps into a very low hover.
5. Use `A/D/W/S/J/L` only as small trims while learning response direction.
6. Do not press `F` until X/Y hold is boringly stable.
7. Use PageDown for normal descent; use Space/Q only as emergency cut paths.

## 2026-06-08 Guarded Autonomy and Repository Update

Powered HLC hover remains blocked pending physical rigid-body-frame calibration.
`mocap_autonomy_ladder.py` now requires `--body-to-cf-quat X Y Z W`, applies the
calibrated transform before extpose transmission, and uses the accepted
Crazyflie-frame orientation for all yaw, roll, and pitch checks.

Additional safety changes:

- validated yaw is converted to radians once and preserved through takeoff,
  `go_to`, and landing
- full orientation-frame validation runs before arming and during flight
- filtered orientation age, stream errors, rejection rate, and consecutive
  rejection bursts are guarded
- the default maximum orientation rejection ratio is `1%`
- landing and controlled landing use a `0.05m` lateral limit
- controlled landing remains continuously monitored
- `land-only` was renamed to `takeoff-land-test`

The focused unit suite contains 18 tests and passes with:

```bash
python3 -m unittest test_mocap_autonomy_ladder.py
```

The root-level diagnostic/calibration scripts are being added to Git:

- `mocap_command_diagnostics.py`
- `mocap_controller_telemetry_logger.py`
- `mocap_estimator_world_frame_calibrator.py`
- `mocap_high_level_point_test.py`
- `mocap_manual_thrust_assisted_figure8.py`

Generated `flight_logs/*.csv` files remain local and are ignored by Git.

## 2026-07-08 Manual-Thrust Mocap Hold Success

After attitude-response probing, the manual-thrust assisted script was updated
to the first directly verified body-frame setup:

- script: `mocap_manual_thrust_assisted_figure8.py`
- mocap position mapping: `local +X <- raw -Y`, `local +Y <- raw +X`,
  `local +Z <- raw +Z`
- `ROLL_SIGN = -1.0`
- `PITCH_SIGN = 1.0`
- `BODY_YAW_OFFSET_DEG = 0.0`
- `YAW_COMMAND_SIGN = -1.0`
- `KP_XY = 14.0`, `KD_XY = 7.0`, `KI_XY = 1.0`
- `MAX_XY_DRIFT_M = 0.60`
- `MAX_TARGET_ERROR_M = 0.55`
- `TAKEOFF_READY_THRUST = 38000`
- `TAKEOFF_HOLD_FREEZE_THRUST_RAW = 33000`
- X/Y assist blends in from `0.005 m` to `0.04 m` height above start, or from
  `24000` to `32000` raw thrust

The attitude response test that supported this was
`flight_logs/mocap-attitude-response-20260708-112640.csv`. The auto `P` probe
completed and showed that removing the extra yaw offset made command axes line
up: pitch affects body X and roll affects body Y, with roll sign inverted.

The first successful powered hold with this setup was:

- log: `flight_logs/mocap-assisted-figure8-20260708-113913.csv`
- user report: hover worked perfectly
- duration: `64.0 s`
- mocap status: fresh for the whole log
- safety stops: none
- final stop: operator cut
- max thrust: `32500`
- max height above start: `0.073 m`
- max horizontal drift: `0.106 m`
- max target error: `0.108 m`

Figure-8 did not activate in that run even though the user pressed `F`.
`figure8_active` stayed `0` because the hover never reached the current
`FIGURE8_MIN_HEIGHT_M = 0.12`; max height was only `0.073 m`. The known-good
next step is to repeat low X/Y hold first, then either climb above `0.12 m`
before pressing `F` or intentionally lower the figure-8 height gate after a
separate safety decision.
