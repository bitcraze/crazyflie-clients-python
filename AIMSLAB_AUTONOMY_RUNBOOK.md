# AIMSLab Crazyflie Mocap Autonomy Runbook

> Historical high-level-commander and calibration runbook. For the current
> manually verified, low-level-commander figure-8 workflow, read
> [`MOCAP_MANUAL_FIGURE8.md`](MOCAP_MANUAL_FIGURE8.md). The flight constants
> and powered-flight status below are not the current manual-figure-8 baseline.

## 2026-07-13 Status

The verified powered-flight path is the low-level, manual-thrust workflow in
`mocap_manual_thrust_assisted_figure8.py`: establish a low hover with `R`, use
`T` to settle near 3 ft, press `F` for one figure-8, then press `F` again to
return to the figure-8 start and land. The current baseline completed one
48-second, cage-limited path at roughly `0.91 m` above start without a safety
descent.

This does **not** clear the high-level-commander (HLC) safety hold below. HLC
work still needs its independent orientation and estimator validation. Keep
`mocap-extpose-figure8.py` and other HLC trajectory scripts out of powered
testing until that work is complete.

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

Validate the mocap position frame with props off:

```bash
python3 mocap_estimator_world_frame_calibrator.py
```

The validator does not stream or calibrate mocap orientation. It captures a raw
mocap origin while the drone is held level, nose-front, at cage center and
mid-height, transforms raw displacement into a local frame, and streams only
`send_extpos(...)`. The default mapping is:

```text
local +X = physical front = mocap -Y
local +Y = physical left  = mocap +X
local +Z = physical up    = mocap +Z
```

The mapping is explicit through `--local-x-from`, `--local-y-from`, and
`--local-z-from`; reflected/left-handed mappings are rejected. After resetting
the Kalman estimator, the script captures `stateEstimate.yaw` while the drone is
still physically level and nose-front. Every phase requires that yaw to remain
within 5 degrees of the post-reset baseline, and the baseline itself must be
within 5 degrees of `0 deg` because physical nose-front defines local `+X`.
`--expected-nose-front-yaw-deg` exists only for a deliberately documented
alternative convention. Roll/pitch must remain within 5 degrees of level, and
`stateEstimate.x/y/z` must remain within 5 cm of transformed mocap for two
continuous seconds. Guided hand tests cover left, right, front, back, up, down,
and a return to the captured origin after every move. Each direction must move
at least 8 cm with no more than 5 cm cross-axis displacement. The CSV records
raw mocap, transformed local mocap, estimator position and attitude, yaw
baseline/alignment/drift, stream status, and per-axis errors.

This baseline check verifies onboard yaw alignment with the operator-defined
local `+X` and detects later heading changes; it is not mocap quaternion
calibration. The validator does not produce `--body-to-cf-quat`.
Passing it proves only the position-axis/sign convention, level/nose-front yaw
consistency, and Kalman position response. It does not clear the powered-flight
safety hold for `mocap_autonomy_ladder.py`.

The captured local `Z=0` is deliberately at mid-height so both up and down can
be tested by hand. It is validator-only and must never be copied into autonomous
flight. Takeoff and landing require a separately measured floor/start-referenced
Z origin.

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

2026-07-08 status for this manual-thrust path: low X/Y hold is now the
known-good powered setup with `ROLL_SIGN = -1.0`, `PITCH_SIGN = 1.0`, and
`BODY_YAW_OFFSET_DEG = 0.0`. The supporting logs are:

- `flight_logs/mocap-attitude-response-20260708-112640.csv`: auto `P` attitude
  probe showed the no-extra-yaw-offset body frame lined up with command axes.
- `flight_logs/mocap-assisted-figure8-20260708-113913.csv`: user-reported
  perfect hover, mocap fresh throughout, no safety stop, max drift `0.106 m`,
  max target error `0.108 m`, max height `0.073 m`.

Figure-8 did not activate in that run because `FIGURE8_MIN_HEIGHT_M = 0.12`
and the low hover only reached `0.073 m`.

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
- `mocap_estimator_world_frame_calibrator.py`: no-flight extpos-only local-frame
  and estimator position validator.
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

## Guarded Position-Only Hover Stage (2026-06-11)

This section supersedes the earlier quaternion/extpose instructions for the
current first powered test. The successful no-flight validator established the
fixed right-handed position mapping `local X=-raw Y`, `local Y=+raw X`, and
`local Z=+raw Z`. `mocap_autonomy_ladder.py` now ignores mocap quaternions and
streams transformed positions with `send_extpos()` only.

The ladder captures the floor/takeoff pose as local `(0, 0, 0)`, starts extpos,
then resets the Kalman estimator. HLC takeoff and landing heights are absolute
estimator-Z values, so the guarded test uses `takeoff(0.05, 5.0)` and
`land(0.0, 6.0)`. It never sends an X/Y movement command.

First remove all propellers and prove the active-link Ctrl+C emergency path:

```bash
python3 mocap_autonomy_ladder.py emergency-test
```

That test now activates an HLC command at absolute Z=0 with the propellers removed, requires Ctrl+C to reach the emergency handler, confirms all 40 zero-thrust and stop-setpoint packets were sent, and verifies `supervisor.is_armed == False` before writing the proof file. If arming confirmation is uncertain, the same emergency cleanup runs before the error is raised.

After it prints `[PROPS-OFF] PASS: active-HLC Ctrl+C stop and disarm verified`, reinstall and inspect the propellers, clear
the cage, keep physical power-off ready, and run:

```bash
python3 mocap_autonomy_ladder.py hover
```

The emergency proof is URI/body-specific, records the verified packet counts and disarmed supervisor state, and expires after 24 hours. Preflight retains the strict 3.75 V and 5 degree level limits. In flight, battery below 3.60 V or tilt above 10 degrees requests a controlled landing after a 1 second debounce; battery below 3.30 V or tilt above 20 degrees triggers emergency stop after a 0.25 second debounce. Stale data, yaw above 10 degrees, lateral guard violations, excessive estimator/mocap error, and excessive height remain immediate stops. `x-step`,
`y-step`, and `figure8` remain locked in code until this hover is explicitly
proven from its CSV log.

The emergency proof is generated at
`.cache/mocap-autonomy-emergency-stop-proof.json`. It is local,
hardware-specific runtime state and is intentionally ignored by Git. Every
operator or machine must run `emergency-test` to create a fresh proof; never
copy or commit another setup's proof file.

### Current HLC Powered-Test Hold

The props-off Ctrl+C emergency test passed, including confirmed disarm. The
subsequent powered hover attempts did not prove hover: one stopped at
approximately 2.3 cm after lateral displacement exceeded 3 cm, and another
stopped near the floor after yaw error exceeded 10 degrees. In the yaw-stop
log, commanded `motor.m2` rose to 56303 while M1 and M3 fell to 7000, but the
vehicle still failed to gain useful height. These values are commanded PWM,
not measured motor RPM.

Do not run another powered hover, loosen the yaw/lateral guards, or unlock any
movement mode until M2 and its propeller, connector, wiring, shaft friction,
and thrust response have been checked with all propellers removed. A successful
Logitech/manual-controller run does not clear this hold because its higher
motor command can mask a weak or intermittent low-throttle response.


## Guarded Figure-Eight Session Update (2026-06-23)

This note records the current state of
`src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-figure8.py`.
It does not clear the powered-flight safety hold elsewhere in this runbook.

### Current Script Behavior

- Connects directly to VRPN at `192.168.1.42:3883` and requires rigid body
  `crazyflie_21`.
- Streams position only with `cf.extpos.send_extpos(...)`; full-pose quaternion
  injection remains disabled because the rigid-body quaternion/body-frame mapping
  has not been validated.
- Rejects missing or stale mocap data before arming. Seeing `Found and tracking
  rigid body: crazyflie_21` confirms the name was discovered; a stationary drone
  can legitimately produce unchanged consecutive positions.
- Generates a local figure-eight with `x = A sin(t)` and
  `y = A sin(t) cos(t)`, split into 16 cubic trajectory segments. With
  `START_FIGURE8_AT_CURRENT_POSITION = True`, the uploaded trajectory is run
  with `relative=True`, so its local `(0, 0)` is the takeoff position.
- Translates that local path into the mocap frame for a pre-arm cage check and
  monitors the measured position during flight. The trajectory is rejected when
  it or the measured drone leaves the safety margin.
- `HOVER_ONLY_TEST = True` is the current safe setting. It takes off to the
  configured absolute HLC Z target, waits for mocap height confirmation, hovers
  for five seconds, and lands. It does not execute the figure-eight.

To run this script from the repository root:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-extpose-figure8.py
```

Keep `HOVER_ONLY_TEST = True` until a hover is stable and repeatable. Setting it
false enables the autonomous trajectory and is not a substitute for frame
validation.

To inspect the direct, read-only VRPN stream without opening a Crazyradio or
commanding a Crazyflie, run:

```bash
python3 src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-vrpn-pose-monitor.py
```

It prints raw position and quaternion values for `crazyflie_21` five times per
second. Use it when recording cage corners or comparing direct VRPN against a
ROS2 pose topic.

### Measured 2 m Cage, Current Coordinate Assumption

The current four floor corners are ordered counterclockwise around the cage for the
script and are stored in `CORNER_POINTS`:

```text
bottom right: (-1.027,  1.015, 0.046)
top right:    (-1.020, -0.999, 0.046)
top left:     ( 1.035, -1.019, 0.033)
bottom left:  ( 1.037,  0.981, 0.038)
```

Their average center is approximately `(0.006, -0.006)`. The measured side
lengths are approximately 2.06 m, 2.01 m, 2.06 m, and 2.00 m.

These corner values were measured with `mocap-vrpn-pose-monitor.py` from the
direct VRPN stream used by the flight script. The earlier provisional ROS2 set
was replaced. The earlier saved corner set had center approximately `(0.995, -1.212)` while direct VRPN at the
physical cage center reported approximately `(0, 0)`; that mismatch caused
valid center placement to be rejected as a wall violation.

The script now uses the four edges as a polygon, not only X/Y min/max, and
requires each checked point to remain at least `SAFETY_MARGIN = 0.10 m` inside
every edge. For the current relative trajectory, the full path must fit inside
that shrunken polygon; “relative to the current position” does not permit a
path started near a wall.

### Figure-Eight Limits and Known Constraints

The current configured amplitude is `0.10 m`. Its maximum intended distance
from the pattern center is 0.10 m, so `MAX_CENTER_DRIFT` must be greater than
0.10 m. The current `0.14 m` threshold is deliberate. Do not set it to 0.08 m
without also shrinking the amplitude; a conservative paired setting is
`FIGURE8_AMPLITUDE = 0.06` and `MAX_CENTER_DRIFT = 0.08`.

`TRAJECTORY_TIME_SCALE = 3.0` makes the 20-second generated path take about 60
seconds. Larger time scales are slower. The old static example,
`mocap-extpose-example.py`, runs a much larger precomputed relative trajectory
with fewer guards and full-pose behavior; do not use it as a cage-flight test.

The current script sends raw direct-VRPN X/Y/Z values to the estimator. Its
absolute takeoff target is `FLIGHT_HEIGHT = 1.0`, while a floor pose has been
observed near `z = 0.03..0.05`. Thus the current target is about 0.95--0.97 m
above the observed floor and the `land(0.0, ...)` target is below that raw floor
baseline. This raw-Z convention remains a limitation to resolve before
unattended autonomous flight.

The VRPN minor-version message and the final
`vrpn_Connection::~vrpn_Connection` remaining-reference message have been
observed during shutdown. They do not establish that pose data is valid; use
fresh-pose and frame checks as the evidence.
