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

The no-flight calibrator resets its orientation jump-filter baseline after the
operator confirms each level/nose-front or intentional 90-degree pose. It waits
for the first valid post-reset quaternion and for estimator yaw convergence
before recording verification samples. It rejects full-quaternion jumps above
8 degrees, fails stationary phases above a 1% rejection rate, and logs corrected
mocap roll/pitch/yaw. The June 9, 2026 `122456` run had a 12.09-degree raw
quaternion jump with almost no yaw change, so its transform must not be used.

The June 9, 2026 `130036` run subsequently passed all three orientation
checks and yielded the candidate
`--body-to-cf-quat -0.037816872 0.001109926 -0.718284935 0.694719659`. Its
first translation phase then hit a stale right-facing jump-filter baseline and
failed at 100% rejection. The calibrator now resets the baseline and requires
position plus nose-front yaw convergence after every guided reposition. Treat
the candidate as unapproved until a clean rerun completes the full no-flight
workflow.

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

Automatic calibration command:

```bash
python3 mocap_estimator_world_frame_calibrator.py
```

Hold the drone level and nose-front for calibration and the first verification,
then follow the physically level 90-degree-left and 90-degree-right prompts. The
calibrator defaults nose-front to `-90deg` because physical front is mocap
`-Y`. It filters implausible quaternion jumps with position-only fallback,
logs accepted/rejected packet decisions and per-phase counts, excludes rejected
quaternions, and uses robust orientation statistics. Before each orientation
verification it requires estimator/mocap position error below 5 cm continuously
for two seconds. It prints the exact `--body-to-cf-quat X Y Z W`, switches the
estimator to the transformed extpose stream, resets it, and verifies corrected
mocap and estimator attitude in all three orientations. Do not use the result
unless the run ends with `[CALIBRATION] PASS`.

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

Then derive and verify `--body-to-cf-quat X Y Z W` through physical orientation
checks before running either ladder validation mode. Do not arm or run a powered
hover as the next test.

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
  - current guarded HLC ladder; requires calibrated body-to-Crazyflie quaternion
- `test_mocap_estimator_world_frame_calibrator.py`
  - pure-Python calibration, quaternion filtering, convergence, phase-transition, and shutdown tests
- `test_mocap_autonomy_ladder.py`
  - pure-Python regression tests for filtering, frame guards, yaw units, and landing
- `mocap_command_diagnostics.py`
  - diagnostic-only controller/mocap/radio logger with guarded manual mode
- `mocap_controller_telemetry_logger.py`
  - Logitech manual commander and telemetry/mocap observer logger
- `mocap_estimator_world_frame_calibrator.py`
  - props-off guided estimator/world-frame calibration logger
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
