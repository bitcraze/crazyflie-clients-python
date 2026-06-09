# AIMSLab Crazyflie Mocap Autonomy Runbook

## Goal

Get to repeatable autonomous indoor figure-8 flight by using the standard Crazyflie
mocap stack:

```text
OptiTrack/Motive -> VRPN -> laptop Python script -> cf.extpos -> Kalman estimator -> high-level position commands
```

The immediate goal is not figure-8. The immediate goal is repeatable mocap-backed
hover. Figure-8 should only happen after validate, hover, steps, and circle all
pass.

## Main Script

### Current Safety Hold

Do not run a powered hover yet. The current guarded path is
`mocap_autonomy_ladder.py`, but every validation and flight mode now requires a
physically calibrated rigid-body-to-Crazyflie quaternion:

```bash
--body-to-cf-quat X Y Z W
```

The transform is applied before `send_extpose(...)`. Props-off validation must
pass estimator position, yaw, roll/pitch frame, stream-error, orientation-age,
rejection-rate, and consecutive-rejection guards before arming. HLC yaw is
preserved from the validated pose, converted to radians once, and used for
takeoff, `go_to`, and landing.

Use `validate-extpose` and `validate-yaw-rotation` first. Do not substitute an
identity transform unless physical calibration proves that the rigid body and
Crazyflie body frames are actually aligned.

Compute and verify the transform with props off:

```bash
python3 mocap_estimator_world_frame_calibrator.py
```

For calibration, place the Crazyflie physically level with its nose pointing
toward cage front. In the measured cage frame, front is mocap `-Y`, so the
default expected Crazyflie yaw is `-90deg`. Use `--nose-front-yaw-deg` only if
the physical cage/world convention is different. The calibrator averages fresh
quaternion samples, rejects excessive held-pose spread, applies the candidate
transform, and resets the estimator. It then verifies corrected mocap and
estimator attitude at nose-front, 90 degrees left, and 90 degrees right. After
the operator confirms each intentional orientation, the calibrator resets the
jump-filter baseline, accepts the first valid quaternion as the new baseline,
and waits for estimator yaw convergence before recording verification samples.
Implausible yaw jumps and full-quaternion angular jumps use position-only
`extpos` fallback. The full-orientation limit defaults to 8 degrees and each
stationary phase fails above a 1% rejection rate. Every logged pose includes its
accepted/rejected decision, stream counters, and corrected mocap roll, pitch,
and yaw; rejected quaternion rows are excluded from calibration and
verification. Verification also requires estimator/mocap position error below
5 cm continuously for two seconds and uses robust quaternion centers plus p90
orientation errors instead of maxima. The unverified transform is not printed.
Copy the final `--body-to-cf-quat ...` argument only after all three
orientations pass.

The June 9, 2026 `130036` run passed nose-front, left 90-degree, and right
90-degree verification and produced the verified candidate
`--body-to-cf-quat -0.037816872 0.001109926 -0.718284935 0.694719659`.
The following front translation phase was incorrectly compared with the stale
right-facing filter baseline, causing 100% fallback even though corrected yaw
was approximately -91.9 degrees. The calibrator now resets the orientation
baseline after every guided reposition and reconfirms estimator position and
the original nose-front yaw before recording each translation phase. Because
the `130036` run predates that fix and did not complete the full no-flight
workflow, rerun the calibrator and do not use this quaternion for powered flight
yet.

The June 9, 2026 `122456` CSV contained a 12.09-degree frame-to-frame raw
quaternion jump during stationary nose-front verification while raw yaw stayed
between -0.06 and 0.30 degrees. The change was dominated by roll/pitch, which is
why yaw-only filtering was insufficient. Do not use the transform from that run
for flight.

`motioncapture 1.0a4` has no Python close API and its VRPN backend wraps an
auto-referenced connection in a default-deleting `shared_ptr`, producing the
remaining-reference destructor warning. The calibrator copies all VRPN-owned
pose values, requests reader shutdown, joins the reader thread, and uses normal
Python process cleanup. The upstream reference warning remains unresolved; do
not mask it with leaked references or forced process exit.

Retain `mocap_high_level_point_test.py` as an earlier high-level-commander
viability reference. Its props-off validation mode remains useful, but do not
run its powered point mode while orientation calibration is unresolved:

- `--mode validate`: streams mocap into `cf.extpos.send_extpos(...)`, resets the
  Kalman estimator, logs mocap versus `stateEstimate`, and never arms.
- `--mode point` is a powered historical verifier and is currently blocked.
- `--mode figure8` is hard-disabled until point mode is proven stable.

Use `mocap_manual_thrust_assisted_figure8.py` as the separate manual-thrust
assisted-flight path. It does not use HLC for takeoff; the pilot owns vertical
thrust while the script assists horizontal hold and later a tiny figure-8.

Keep these older scripts in their current roles:

- `mocap_autonomy_ladder.py`: current guarded autonomy ladder; powered modes are
  blocked until the body-frame transform is calibrated and props-off checks pass.
- `mocap_vertical_thrust_mapper.py`: historical low-level thrust, XY hold, and tiny figure-8 path.
- `mocap-guarded-takeoff.py`: historical reference for extpose/HLC setup.
- `mocap-guarded-thrust-test.py`: historical reference for estimator-vs-mocap gates.
- `mocap-extpose-figure8.py`: do not use for flight yet. It jumps too far ahead.

Additional root-level tools now tracked in Git:

- `mocap_command_diagnostics.py`: controller, radio, telemetry, and mocap
  diagnostics with props-off and guarded manual modes.
- `mocap_controller_telemetry_logger.py`: Logitech manual commander plus
  telemetry/mocap observer logger.
- `mocap_estimator_world_frame_calibrator.py`: no-flight guided world-frame and
  estimator calibration logger.
- `mocap_high_level_point_test.py`: earlier position-oriented HLC viability
  verifier; keep powered use deferred while orientation calibration is unresolved.
- `mocap_manual_thrust_assisted_figure8.py`: experimental pilot-owned-thrust
  assisted-flight path; not a substitute for frame validation.

## Preflight Checklist

Before every powered run:

- Crazyflie battery is above `3.75V`.
- Battery is secured and not sagging under the mocap deck or marker mount.
- Props are correct and fully seated.
- Guards are installed and not touching props.
- Cage is clear.
- Motive is tracking rigid body `crazyflie_21`.
- VRPN stream is reachable at `192.168.1.42:3883`.
- Crazyradio is connected.
- `cfclient` or any other competing Crazyradio process is closed.
- You have a physical power cutoff plan.
- First run of the day is `validate`, not `hover`.

If the script fails the cage-bounds gate, update the measured bounds with
`--x-min`, `--x-max`, `--y-min`, and `--y-max`. Do not bypass the bounds check
just to make a run start.

## Current OptiTrack Frame

Measured near cage center with the drone facing physical front:

```text
Position: 0.000 0.009 0.038
Quaternion: -0.997 0.006 -0.004 -0.074
```

For the root-level HLC verifier, raw mocap coordinates are used directly:

- script `x` = first mocap position value = physical left/right; left is positive, right is negative
- script `y` = second mocap position value = physical front/back; front is negative, back is positive
- script `z` = height; floor/base is about `0.03m..0.04m`

A `--height 0.10` hover from this start commands absolute HLC height near
`z = 0.138`, then lands back to the measured start `z`, not to zero.

## Command Ladder

Run commands on the Linux ThinkPad, from the machine that has `cflib`,
`motioncapture`, Crazyradio access, and VRPN access.

### 1. Validate Estimator With Props Off

No autonomous flight. The script streams mocap into the Crazyflie estimator,
resets Kalman, then logs estimator-vs-mocap agreement while the drone is moved
by hand. It does not arm.

```bash
python3 mocap_high_level_point_test.py --mode validate --validate-duration 20
```

During validation, move the drone slowly by hand:

- physical left: script/mocap `x` should increase
- physical right: script/mocap `x` should decrease
- physical front: script/mocap `y` should decrease
- physical back: script/mocap `y` should increase
- up: script/mocap `z` should increase from about `0.038`

Pass criteria:

- Rigid body is found.
- Mocap pose stays fresh.
- Kalman estimator follows mocap in the same direction on all axes.
- `estimate_error_m` is usually below `0.05m`, with brief values up to about `0.08m` acceptable.
- No stale-pose or estimator-stale failures.

Do not fly if validate fails.

### 2. HLC Hover-Only Verifier (Blocked)

After calibration and both props-off validations pass, the first powered HLC run would be hover-only: take off to 10 cm above the measured start
height, hold over start, and land slowly. No X/Y move is commanded.

```bash
python3 mocap_high_level_point_test.py \
  --mode point \
  --height 0.10 \
  --dx 0.00 \
  --dy 0.00 \
  --land-duration 5.0
```

Pass criteria:

- Takeoff is mostly vertical.
- No stale mocap.
- No estimator disagreement.
- Max `abs(mocap_x - start_x)` stays below `0.15m`.
- Max `abs(mocap_y - start_y)` stays below `0.15m`.
- Land is slow and controlled.

If hover is unstable, do not continue to point moves. Re-run validate, inspect
logs, and check marker tracking/orientation.

### 3. Tiny HLC Point Move (Blocked)

Only after calibration and a clean hover-only run, try a 4 cm move. In this cage frame,
positive `dx` moves physical left, negative `dx` moves physical right, negative
`dy` moves physical front, and positive `dy` moves physical back.

```bash
python3 mocap_high_level_point_test.py \
  --mode point \
  --height 0.12 \
  --dx 0.04 \
  --dy 0.00 \
  --land-duration 5.0
```

Pass criteria:

- Move is only `0.04m`.
- The drone returns to start before landing.
- Horizontal target error stays below `0.14m`.
- No growing estimator error.

### 4. Steps

Deferred. Do not use the older ladder steps until the root-level HLC verifier has
repeatable hover-only and 4 cm point-move logs. When re-enabled, steps should be
implemented through the same guarded `mocap_high_level_point_test.py` safety
model, not by jumping straight to older trajectory scripts.

Pass criteria:

- Each step is only `0.10m`.
- The drone returns to center.
- Max tracking error stays below `0.20m`.
- No growing estimator error.

### 5. Circle

Deferred until steps are repeatable under the guarded HLC verifier model.

Pass criteria:

- Radius is `0.05m`.
- Period is `24s`.
- No guard trips.
- Error does not grow over the path.

### 6. Figure-8

Deferred. `mocap_high_level_point_test.py --mode figure8` is intentionally
disabled in code until validate, hover-only, and tiny point moves are boringly
repeatable.

Initial pass criteria:

- Radius is tiny: `0.05m..0.08m`.
- Height is `0.35m`.
- Period is `24s`.
- One full period completes.
- Max tracking error stays below `0.20m`.

## Useful Options

Defaults are intentionally conservative. For the current HLC verifier, keep
position-only external position injection until quaternion/frame convention is
trusted:

```bash
python3 mocap_high_level_point_test.py --mode validate --pose-mode extpos
```

Use `--pose-mode extpose` only after level yaw/orientation behavior is validated.
The current first-flight path does not need quaternion injection.

## Logs

Each run writes a CSV under `flight_logs/`.

Review these columns first:

- `stop_reason`
- `mocap_age_s`
- `estimate_error_m`
- `battery_v`
- `height_above_start_m`
- `radius_from_start_m`
- `target_error_m`
- `guard_ok`

Every failed run should have a stop reason. If a run fails without a useful stop
reason, improve the script before doing more flight tests.

## What Not To Run Yet

Do not use `mocap-extpose-figure8.py` for flight yet.

Do not use HLC figure-8 until validate logs prove the estimator/mocap/HLC frame.

Do not continue to the next milestone after a guard trip. Treat guard trips as
data, inspect the CSV, and repeat the previous milestone.

Do not increase radius, height, or speed in the same run. Change one variable at
a time.

## Static Checks

Run these before committing changes:

```bash
PYTHONPYCACHEPREFIX=/tmp/crazyflie-pycache python3 -m py_compile \
  mocap_autonomy_ladder.py \
  mocap_estimator_world_frame_calibrator.py \
  keyboard_thrust_test.py \
  mocap_vertical_thrust_mapper.py \
  test_mocap_autonomy_ladder.py \
  test_mocap_estimator_world_frame_calibrator.py
```

```bash
PYTHONPYCACHEPREFIX=/tmp/crazyflie-pycache python3 -m unittest \
  test_mocap_autonomy_ladder.py \
  test_mocap_estimator_world_frame_calibrator.py
```

The unit tests are pure Python and do not need `cflib`, `motioncapture`, VRPN, or
Crazyradio hardware.
