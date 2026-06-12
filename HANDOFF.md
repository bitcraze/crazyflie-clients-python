# Crazyflie Mocap Flight Handoff

Date: 2026-06-08
Repo: `/home/alwin-raj/Desktop/drone/crazyflie-clients-python`
Branch: `aimslab/work`

## Current Status

Do not run a powered HLC hover yet. `mocap_autonomy_ladder.py` now requires an
explicit calibrated `--body-to-cf-quat X Y Z W`, applies it before extpose
transmission, and validates the resulting Crazyflie-frame roll, pitch, and yaw.
Props-off validation must pass before arming.

The ladder also converts preserved yaw to radians once for all HLC commands,
monitors landing continuously, limits landing lateral error to `0.05m`, and
trips on stale accepted orientation, stream errors, excessive rejection rate,
or consecutive orientation rejections. The old `land-only` mode is named
`takeoff-land-test`.

There are now two active root-level paths:

- `mocap_high_level_point_test.py`: current high-level-commander viability verifier.
- `mocap_manual_thrust_assisted_figure8.py`: manual-thrust assisted-flight path.

For HLC work, validate first with props off, then run hover-only at 10 cm, then
try a tiny 4 cm point move. HLC figure-8 is disabled in code until point mode is
proven stable.

The manual-thrust script assists roll, pitch, yaw, safety checks, logging, and
eventually a very small figure-8. It is not using high-level commander for
takeoff.

The latest manual-thrust change added keyboard attitude trims:

- `A` / `D`: roll trim down/up
- `W` / `S`: pitch trim up/down
- `J` / `L`: yaw target offset left/right
- `C`: clear all manual trims

All runs should continue writing logs under `flight_logs/`.

## Hardware / Environment

- Crazyflie 2.1 Brushless.
- No positioning deck.
- Crazyradio URI: `radio://0/80/2M`.
- OptiTrack/VRPN host: `192.168.1.42:3883`.
- Rigid body: `crazyflie_21`.
- Current center measurement: `Position: 0.000 0.009 0.038` with the drone facing physical front.
- Floor/cage-center mocap baseline has been around `z = 0.037..0.045`.
- Close `cfclient` before running scripts; only one process can own Crazyradio.
- Software stop paths are not physical e-stops. Keep physical power-off ready.

## World Frame / Cage Mapping

From no-flight calibration and user observations:

- physical front = mocap `-Y`
- physical back = mocap `+Y`
- physical left = mocap `+X`
- physical right = mocap `-X`
- height = mocap `+Z`

The physical left side of the cage has had poor mocap coverage. Prefer the
smaller reliable flight area until coverage is improved.

The no-flight calibrator streams position only. It captures a center/mid-height
origin while the drone is physically level and nose-front, then maps raw mocap
displacement into local Crazyflie coordinates using an explicit right-handed
signed axis permutation. Reflected mappings are rejected. Its defaults match
the measured cage:

```text
local +X <- mocap -Y  (physical front)
local +Y <- mocap +X  (physical left)
local +Z <- mocap +Z  (physical up)
```

It streams only `extpos`, resets the Kalman estimator, and captures a
post-reset `stateEstimate.yaw` baseline while the drone remains level and
nose-front. Because nose-front defines local `+X`, the baseline must be within
5 degrees of `0 deg` by default; every later hold requires roll/pitch within 5
degrees of level, yaw within 5 degrees of that baseline, and estimator position
within 5 cm of transformed mocap for two continuous seconds. It guides
left/right, front/back, and up/down hand movements with a return to origin after
each move. Direction, minimum displacement, cross-axis movement, freshness,
robust estimator agreement, yaw alignment, and yaw stability are checked and
logged.

The script no longer computes or verifies a body-to-Crazyflie quaternion. The
post-reset yaw baseline verifies onboard yaw alignment to the operator-defined
local `+X` and detects rotation, but it is not mocap quaternion calibration.
The old candidate quaternion remains unapproved and the validator cannot clear
the autonomy ladder's orientation requirement.

The installed `motioncapture 1.0a4` binding has a VRPN connection-destruction
bug and no Python close API. The reader copies binding-owned values, requests
shutdown, joins its thread, and leaves normal Python cleanup intact. The
upstream remaining-reference warning is still unresolved; it is not hidden by
leaking the connection or bypassing interpreter finalization.

## Mocap Marker / Coverage Notes

The user now has four mocap markers on the drone. The front/nose is the white
protrusion at the top-center in the overhead photo. After any marker movement or
addition, rebuild/redefine the rigid body in Motive before trusting pose or yaw.

No-flight coverage logs showed stale-pose/dropout behavior, especially on the
physical left side of the cage. VRPN may keep returning old pose values while
`mocap_age_s` grows, so stale-pose checks are mandatory.


## HLC Verifier Path

`mocap_high_level_point_test.py` uses raw OptiTrack coordinates directly:

- script `x` = first mocap position value = physical left/right; left is positive
- script `y` = second mocap position value = physical front/back; front is negative
- script `z` = height; floor/base is about `0.03m..0.04m`

Current allowed HLC work is props-off validation only:

```bash
python3 mocap_autonomy_ladder.py validate-extpose \
  --body-to-cf-quat X Y Z W
python3 mocap_autonomy_ladder.py validate-yaw-rotation \
  --body-to-cf-quat X Y Z W
```

The quaternion values must come from physical calibration. Powered `hover`,
`takeoff-land-test`, point moves, and trajectories remain blocked.

Position-frame validation command:

```bash
python3 mocap_estimator_world_frame_calibrator.py
```

Start at cage center while holding the drone at a comfortable mid-height so
there is room to move both up and down. The validator captures that local
origin, streams transformed `extpos`, resets the estimator, and then prompts for
left, right, front, back, up, down, and center-return holds. Do not rotate the
drone as part of these tests. A successful run ends with
`[VALIDATION] PASS: all position axes/directions verified with stable
level/nose-front yaw`.

That mid-height origin makes local `Z=0` suitable only for this hand validator.
Do not copy it into flight code; autonomous takeoff and landing need a separate
floor/start-referenced Z origin.

`--mode validate` streams `cf.extpos.send_extpos(...)`, resets the Kalman
estimator, logs mocap versus `stateEstimate`, and never arms. The hover-only
point command takes off to about 10 cm above measured start `z`, holds over
start, and lands back to measured start `z`.

Do not use HLC figure-8 yet. The script raises an error for `--mode figure8`
until hover and tiny point mode are repeatable.

## Active Script Details

`mocap_manual_thrust_assisted_figure8.py` is intentionally tuned through
constants near the top of the file rather than lots of CLI flags.

Important current constants:

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
- `MOCAP_RELOCK_AFTER_STALE_S = 0.45`
- `ROLL_SIGN = -1.0`
- `PITCH_SIGN = -1.0`
- `KP_XY = 14.0`
- `KD_XY = 7.0`
- `KI_XY = 1.0`
- `GROUND_MAX_ANGLE_DEG = 1.5`
- `MAX_ANGLE_DEG = 12.0`
- figure-8: `0.04m x 0.03m`, `32s` period, min start height `0.12m`

Keyboard controls:

- `R`: jump to ready thrust near liftoff
- Up / Down: fine thrust changes
- PageUp: larger thrust increase
- PageDown: slow descent ramp, not immediate cut
- `A` / `D`: roll trim down/up by `0.5 deg`
- `W` / `S`: pitch trim up/down by `0.5 deg`
- `J` / `L`: yaw target offset left/right by `5 deg`
- `C`: clear manual attitude trims
- `H`: lock current X/Y as the hold target
- `F`: toggle tiny figure-8 after stable hover
- Space: emergency thrust cut
- `Q` / Esc: cut, disarm, and exit

## Stale Mocap Behavior

If mocap age exceeds `0.30s`, the script enters `mocap-stale` mode:

- stops figure-8
- clears velocity, yaw-rate, and integral state
- commands neutral roll/pitch/yaw while preserving manual thrust
- keeps PageDown, thrust keys, Space, and Q working
- logs stale rows with `mocap_status = stale`

If mocap stays stale longer than `1.50s`, the script raises an error and the
cleanup path cuts thrust and disarms. If mocap reacquires after at least `0.45s`,
it re-locks the current X/Y position instead of snapping back to an old target.

Important clarification: this is not true hover without mocap. The Crazyflie IMU
can keep attitude level, but it cannot know X/Y position without external pose.
The stale mode is a short neutral/level grace period so brief dropouts are less
violent.

## Logging

Current assisted script logs to:

- `flight_logs/mocap-assisted-figure8-YYYYMMDD-HHMMSS.csv`

CSV includes:

- mocap position, quaternion, age, and frame count
- `mocap_status` as `fresh` or `stale`
- thrust raw and percent
- roll, pitch, and yaw-rate commands
- manual trim fields: `manual_roll_trim_deg`, `manual_pitch_trim_deg`,
  `manual_yaw_offset_deg`
- target X/Y, target error, figure-8 active flag
- drift, height above start, velocity, body-frame error/velocity
- yaw, target yaw, yaw error, measured yaw-rate
- battery voltage and `stateEstimate.z`
- stop reason when available

When reviewing a new run, start with the latest
`flight_logs/mocap-assisted-figure8-*.csv`.

## Important Recent Observations

The most recent analyzed `mocap-assisted-figure8` runs before the latest trim
change did not get airborne; max thrust was still far below the known liftoff
range. That led to the `R` ready-thrust key and larger PageUp step.

Earlier `mocap_vertical_thrust_mapper.py` runs showed that simply increasing
X/Y gains did not solve drift. Likely blockers included mocap coverage gaps,
rigid-body yaw instability, body-frame sign uncertainty, and floor-skid near
liftoff.

The user reported practical hover/liftoff around roughly `57%` raw thrust, with
quick climb above about `60%`. Battery state matters.

## Recommended Next Test

Run props-off calibration and diagnostics only:

```bash
python3 mocap_estimator_world_frame_calibrator.py
python3 mocap_command_diagnostics.py validate
```

This validates position only. A separate trustworthy orientation-frame method
is still required before running either ladder validation mode. Do not arm or
run a powered hover as the next test.

## Log Analysis Checklist

For new flight or coverage logs, summarize:

- row count and duration
- max/final thrust and thrust percent
- max/final height above start
- max/final horizontal drift
- max/final target error
- max roll/pitch/yaw-rate command
- manual trim values used during the run
- count and duration of stale mocap spans
- max `mocap_age_s`
- whether figure-8 was activated
- final battery voltage
- whether the run ended from stale mocap, drift, target error, height, battery,
  or user stop

If it drifts while manual trims are used, compare `manual_*_trim` fields with
mocap X/Y movement to infer whether roll/pitch signs or yaw frame need changing.
Adjust one sign or offset at a time.

## Files To Know

- `mocap_autonomy_ladder.py`
  - current guarded position-only HLC ladder using transformed extpos
- `test_mocap_estimator_world_frame_calibrator.py`
  - pure-Python axis-transform, extpos, convergence, movement, and shutdown tests
- `test_mocap_autonomy_ladder.py`
  - pure-Python regression tests for filtering, frame guards, yaw units, and landing
- `mocap_command_diagnostics.py`
  - diagnostic-only controller/mocap/radio logger with guarded manual mode
- `mocap_controller_telemetry_logger.py`
  - Logitech manual commander and telemetry/mocap observer logger
- `mocap_estimator_world_frame_calibrator.py`
  - props-off extpos-only local-frame and estimator position validator
- `mocap_high_level_point_test.py`
  - earlier HLC point verifier; do not use for powered flight until frame validation is resolved
- `mocap_manual_thrust_assisted_figure8.py`
  - experimental pilot-owned-thrust assisted-flight path
- `mocap_vertical_thrust_mapper.py`
  - earlier experimental low-level mapper; useful history, not the current main path
- `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guided-manual-flight-logger.py`
  - passive mocap/controller logger and coverage helper
- `flight_logs/`
  - local generated CSV logs; new CSVs are intentionally ignored by Git
- `session.md`
  - longer chronological notes

## Git Notes

The root-level diagnostic and calibration tools, including
`test_mocap_estimator_world_frame_calibrator.py`, are tracked together with this
handoff. Generated `flight_logs/*.csv` files remain local and are ignored rather
than pushed with source changes.

## 2026-06-11 Guarded Hover Update

The no-flight position validator completed all 13 phases. The current
`mocap_autonomy_ladder.py` first-flight stage is therefore position-only:
transformed `send_extpos()` with local `X=-raw Y`, local `Y=+raw X`, and local
`Z=+raw Z`. It captures a new floor/takeoff origin as local zero and does not
reuse the hand-held validator origin or any mocap quaternion.

Run the props-off Ctrl+C emergency proof first:

```bash
python3 mocap_autonomy_ladder.py emergency-test
```

Only after `[PROPS-OFF] PASS`, run the guarded 5 cm hover:

```bash
python3 mocap_autonomy_ladder.py hover
```

HLC height arguments are absolute estimator-Z targets: takeoff is local
`Z=0.05`, landing is local `Z=0.0`. No X/Y command is issued. `x-step`, `y-step`,
and `figure8` remain locked.

## Guarded Hover Safety Update (2026-06-11)

The props-off proof now runs while HLC is confirmed active at absolute Z=0. It
writes a hover-unlock proof only after 40 zero-thrust packets, 40 stop setpoints,
a disarm request, and `supervisor.is_armed == False` are all confirmed. An arm
confirmation timeout is treated as uncertain arming and invokes emergency
cleanup before raising.

Preflight remains strict at battery >=3.75 V and roll/pitch <=5 degrees.
Airborne battery and tilt use separate debounced tiers: below 3.60 V or above
10 degrees requests controlled landing after 1 second; below 3.30 V or above
20 degrees triggers emergency stop after 0.25 seconds. Immediate stale-data,
yaw, lateral, estimator-error, and excessive-height guards are unchanged.

The URI/body-specific emergency proof at
`.cache/mocap-autonomy-emergency-stop-proof.json` is generated local state. It
is ignored by Git and must be recreated through `emergency-test` on each
operator setup instead of copied or committed.

## Powered Hover Status And Motor Hold (2026-06-11)

The props-off active-HLC Ctrl+C test passed with 40 zero-thrust packets, 40 stop
setpoints, a disarm request, and confirmed `supervisor.is_armed == False`.

The guarded hover is not yet proven. One attempt reached approximately 2.3 cm
and stopped when lateral displacement reached 3.4 cm. Another remained near
the floor and stopped when yaw error reached 12.7 degrees. In that yaw-stop
log, `motor.m2` was commanded up to 56303 while M1 and M3 were reduced to 7000.
The `motor.m*` fields are commanded PWM values, not RPM measurements, so this
shows controller compensation rather than verified M2 thrust.

Further powered attempts are on hold. With all propellers removed, inspect M2's
propeller pairing/orientation, connector, wiring, shaft friction, startup
response, and intermittency. Do not relax the yaw or lateral guards. A
successful CFclient/Logitech manual run does not by itself clear M2 because a
higher command can hide weak low-throttle startup behavior. Keep `hover`,
`x-step`, `y-step`, and `figure8` blocked until the propulsion issue is resolved
and the guarded hover completes cleanly.
