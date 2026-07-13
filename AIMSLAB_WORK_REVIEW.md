# AIMSLab Work Branch Review

> Historical review of earlier autonomy work. Its findings remain useful for
> the scripts it names, but it predates the manual-thrust figure-8 baseline in
> `MOCAP_MANUAL_FIGURE8.md`.

Date: 2026-05-14
Branch reviewed: `aimslab/work`
Commit reviewed: `965c8ec`

## Scope

This review covers the AIMSLab additions on top of the upstream Crazyflie client, with emphasis on the mocap/OptiTrack scripts, Logitech controller scripts, and the current progress documented in `session.md`.

No flight scripts were executed during this review. I inspected code and session history only. Python syntax parsing passed for the changed Python files, but `git diff --check d452de9..HEAD` currently fails due to trailing whitespace and blank-line-at-EOF issues across many added files.

## Executive Summary

The branch is moving in the right direction: the latest guarded scripts are much safer than the earlier autonomous trajectory scripts, and `session.md` preserves useful debugging context. The main remaining risk is that the code still allows autonomous or semi-autonomous motion before the mocap pose, estimator state, controller identity, and coordinate frame are proven trustworthy.

The safest next implementation pass should not add bigger maneuvers. It should harden preflight gates, fail closed on device/pose ambiguity, and mark older trajectory scripts as unsafe until the guarded takeoff and raw-thrust tests are repeatable.

## Highest Priority Problems

### P1: Guarded takeoff can fly with an untrusted estimator

File: `src/aimslab/crazyflie-clients-python/src/aimslab/examples/mocap-guarded-takeoff.py`

Relevant lines:

- `setup_estimate_logger(...)`: lines 232-254
- `print_estimate_comparison(...)`: lines 257-270
- estimator reset and arm path: lines 345-361

Problem:

`mocap-guarded-takeoff.py` streams external pose, resets the Kalman estimator, prints mocap vs `stateEstimate`, then arms and takes off. The printed comparison is informational only. If `stateEstimate` is missing, stale, offset, or diverging from mocap, the script still proceeds.

Why this matters:

`session.md` documents that after enabling the high-level commander, the drone took off quickly and crashed. The current best understanding says command delivery works, but mocap pose/orientation alignment is not yet trustworthy. A guarded takeoff script must treat estimator agreement as a hard safety requirement before arming.

Proposed solution:

1. Add an estimator agreement gate to `mocap-guarded-takeoff.py`, similar to the existing `require_estimate_agreement()` in `mocap-guarded-thrust-test.py`.
2. Gate arming on all of these checks:
   - fresh mocap pose age less than `POSE_STALE_TIMEOUT`
   - stable mocap pose over the stability window
   - initial position inside bounds
   - `stateEstimate.x/y/z` sample exists
   - `stateEstimate` age less than `ESTIMATE_MAX_AGE`
   - mocap vs estimate position error less than a small tolerance, for example `0.05m`
3. Fail before arming if any gate fails.
4. Print a short "preflight passed" block immediately before arming so operators know which assumptions were validated.
5. Until yaw/quaternion mapping is validated cleanly, consider a config flag that defaults to position-only extpose (`send_extpos`) for the first low takeoff tests. Full pose should be enabled only after level yaw tests confirm the quaternion frame.

### P1: The coordinate frame and floor baseline are not normalized consistently

Files:

- `mocap-guarded-takeoff.py`
- `mocap-guarded-thrust-test.py`
- older mocap examples under `src/aimslab/crazyflie-clients-python/src/aimslab/examples/`

Problem:

`session.md` says the rigid body reports the floor near `z = 0.037`, and height above floor should be interpreted as `reported_z - 0.037`. The guarded takeoff script uses this for `TAKEOFF_Z`, but still feeds raw mocap `z` into the estimator and lands to `LAND_Z = 0.0`.

Why this matters:

If the estimator world frame treats floor as `z = 0.037`, then landing to absolute `0.0` asks the high-level commander to descend below the observed floor baseline. That may only be a few centimeters, but at this scale it can produce ground contact, tilt, or supervisor lockout symptoms that confuse the diagnosis.

Proposed solution:

Choose one frame convention and apply it everywhere:

Option A, preferred for clarity:

- Normalize external pose before feeding it to Crazyflie:
  - `cf_z = mocap_z - FLOOR_Z`
  - floor becomes `z = 0.0`
  - takeoff target becomes `TAKEOFF_HEIGHT_ABOVE_FLOOR`
  - land target remains `0.0`

Option B:

- Keep raw mocap coordinates:
  - takeoff target remains `FLOOR_Z + height`
  - landing target should be `FLOOR_Z`, not `0.0`
  - all bounds, drift checks, and printed height labels must make the raw-frame assumption explicit

Do not mix these two approaches across scripts. The current branch partially uses Option B but still lands like Option A.

## Safety and Flight Behavior Problems

### P2: Manual controller script arms before confirming safe low-thrust input

File: `test_flight_with_controller.py`

Relevant lines:

- arming: lines 341-345
- low-thrust wait loop: lines 236-239

Problem:

The script arms the Crazyflie before `controller_flight()` waits for the right stick to be down. If the thrust axis is not detected, mapped incorrectly, or never emits an event, the script can sit in the wait loop while the Crazyflie is armed.

Why this matters:

This exact class of controller-mapping issue happened during the session: `/dev/input/js0` was a touch controller, not the Logitech F310. The script should not arm until the correct controller is confirmed and the thrust axis has produced a low-thrust reading.

Proposed solution:

1. Move the low-thrust gate before `send_arming_request(True)`.
2. Add a timeout to the low-thrust wait, for example 10 seconds.
3. Require a fresh thrust-axis event before arming, not just a default value.
4. If the timeout expires, send stop setpoint, disarm if needed, and exit.
5. Keep the final cleanup disarm, but do not rely on cleanup as the primary safety boundary.

### P2: Joystick autodiscovery can select the wrong device

Files:

- `test_flight_with_controller.py`
- `demo_controller_live.py`
- `mocap-guided-manual-flight-logger.py`

Relevant lines:

- `test_flight_with_controller.py`: `find_controller_device(...)`, lines 196-206
- `demo_controller_live.py`: `find_controller_device(...)`, lines 214-224
- `mocap-guided-manual-flight-logger.py`: `find_controller_device(...)`, lines 298-309

Problem:

The scripts prefer `/dev/input/js1`, but if that path does not exist they fall back to the first `/dev/input/js*`. This can select an unrelated joystick-class device. The session already found `/dev/input/js0` was `Melfas LGD AIT Touch Controller Mouse`.

Why this matters:

A wrong joystick device can leave thrust unavailable, invert controls, or produce garbage inputs. For a flight script, "some joystick exists" is not enough.

Proposed solution:

1. Read the device name with `JSIOCGNAME`.
2. Require the name to contain an expected token such as `Logitech`, `F310`, or `Gamepad`, unless the operator explicitly passes `--allow-any-controller`.
3. Require enough axes/buttons for the configured mapping.
4. Print the selected device name and axis mapping before any flight action.
5. For scripts that can command flight, fail closed if the preferred controller is missing instead of silently falling back.

### P2: Raw-thrust `manual_percent` mode is not actually a ramp

File: `mocap-guarded-thrust-test.py`

Relevant lines:

- config: lines 61-67
- `send_low_level_setpoint(...)`: lines 394-410
- `cut_thrust(...)`: lines 413-420

Problem:

In `manual_percent` mode, any nonzero thrust value sends exactly `MANUAL_THRUST_PERCENT`. With the default `57.0`, the script jumps from 0 percent during priming to 57 percent on the first ramp step. The status output still prints raw thrust values, which makes the run look like a gradual raw ramp even though the sent command is a fixed percentage.

`cut_thrust(...)` also bypasses `send_low_level_setpoint(...)` and always calls raw `send_setpoint(...)`, so command mode is inconsistent during shutdown.

Why this matters:

The purpose of this script is to make low-altitude thrust tests predictable. A hidden jump to 57 percent can be more aggressive than intended and makes logs harder to interpret.

Proposed solution:

Choose one of these designs:

1. Rename the mode to `fixed_manual_percent` and document that it sends a single percentage after priming.
2. Or make `manual_percent` truly ramp:
   - map `current_thrust` linearly from `START_THRUST..MAX_THRUST` to a configured percent range
   - for example `START_PERCENT = 45.0`, `MAX_PERCENT = 60.0`

Also route shutdown through the same abstraction:

- `cut_thrust(...)` should call `send_low_level_setpoint(...)`, or there should be separate raw and percent shutdown implementations.

### P2: Figure-8 script takes off before reaching the computed safe takeoff point

File: `mocap-extpose-figure8.py`

Relevant lines:

- safe takeoff calculation: lines 559-562
- takeoff sequence: lines 461-465
- safety check after takeoff: lines 480-494

Problem:

The script calculates a safe takeoff position, passes it into `run_sequence(...)`, prints it, but no longer moves there before takeoff. It takes off from the current position, then checks whether the current position is safe after the takeoff.

Why this matters:

If the drone starts near the cage edge or in a bad part of the tracking volume, the first unsafe autonomous action has already happened before the safety check runs.

Proposed solution:

Do not run this script until the guarded takeoff and a 10 cm guarded horizontal move are repeatable.

When this script is revisited:

1. Require the initial position to be inside bounds before arming.
2. Either require the operator to manually place the drone at a verified safe launch point, or move to a safe point only after takeoff and only if the current takeoff location is already safe.
3. Do not send horizontal `go_to(...)` while on the floor.
4. Add stale-pose checks before every high-level command and inside every wait period.
5. Re-enable trajectory validation before upload.

### P2: Figure-8 trajectory speed is documented backwards

File: `mocap-extpose-figure8.py`

Relevant lines:

- `trajectory_timescale = 0.7`: line 502
- duration adjustment: lines 508-510

Problem:

The comment says lower `trajectory_timescale` is slower and more relaxed. Bitcraze high-level commander semantics are the opposite: `time_scale > 1.0` is slower, and `< 1.0` is faster.

Why this matters:

The script currently uses `0.7` while intending to slow down the trajectory. That makes the path faster and more aggressive than intended.

Proposed solution:

1. Change the comment to match the high-level commander API.
2. Use a value greater than `1.0` for slower tests, for example `1.5` or `2.0`.
3. Keep `adjusted_duration = duration * trajectory_timescale`, not `duration / trajectory_timescale`, if using Bitcraze's documented semantics.

Reference: https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/api/cflib/crazyflie/high_level_commander/

### P2: Older autonomous scripts lack the new guarded preflight model

Files:

- `mocap-extpose-example.py`
- `mocap-extpose-boundary-aware.py`
- `mocap-map-boundaries.py`
- `mocap-extpose-figure8.py`
- `src/aimslab/crazyflie-clients-python/src/aimslab/extpose-flight.py`

Problem:

These scripts can arm and execute high-level motion after simple sleeps and basic setup. They do not consistently require fresh pose, stable pose, estimator agreement, controller/operator confirmation, or live stale-pose guards during waits.

Why this matters:

`session.md` explicitly recommends not running autonomous trajectory scripts yet. The repository should make that hard to miss. Right now a user can still run these scripts directly and get autonomous motion with fewer safeguards than the newer guarded scripts.

Proposed solution:

1. Add a clear top-of-file warning to each older script saying it is experimental and should not be used until guarded takeoff passes.
2. Optionally add a `REQUIRE_EXPLICIT_UNSAFE_CONFIRMATION = True` gate that requires typing a phrase before arming.
3. Better long term: refactor shared mocap, estimator, and guard logic into one utility module and have every flight script use the same preflight gates.

## Reliability and Maintainability Problems

### P3: Motion-capture reader errors are stored but not checked everywhere

Files:

- `mocap-guarded-takeoff.py`
- `mocap-guarded-thrust-test.py`
- `mocap-guided-manual-flight-logger.py`

Problem:

The guarded scripts store `MocapWrapper.error`, but the takeoff and thrust scripts mostly rely on pose age timeouts rather than checking the thread error directly. If the mocap connection fails after startup, the operator sees a stale-pose failure but not the actual exception.

Proposed solution:

1. Add a helper like `raise_if_mocap_failed(wrapper)`.
2. Call it inside wait loops and before arming.
3. Include the underlying exception in the error message.

### P3: Dependency specifications can still resolve to latest packages

Files:

- `pyproject.toml`
- `src/aimslab/crazyflie-clients-python/requirements.txt`

Problem:

The local `AGENTS.md` instruction says package downloads should avoid latest packages and use packages at least two weeks old. The branch has open-ended dependency specs such as `setuptools`, `scipy>=1.11`, and compatible-release ranges. The nested `requirements.txt` also includes direct git dependencies.

Why this matters:

This weakens reproducibility and can violate the local package policy during future environment setup.

Proposed solution:

1. Prefer a lock file or constraints file for AIMSLab development.
2. Pin all runtime packages to known-good versions that are older than two weeks.
3. Avoid unpinned direct git dependencies unless the commit SHA is intentional and documented.
4. Document the exact environment used for successful hardware tests.

### P3: `git diff --check` fails on whitespace

Problem:

The current branch has extensive trailing whitespace and blank-line-at-EOF issues. This is not a flight-safety issue, but it makes reviews noisy and may fail basic CI checks if whitespace checks are enabled.

Proposed solution:

Run a formatting cleanup pass after the safety fixes are decided. Keep it as a separate commit from behavioral changes.

### P3: Script duplication makes safety fixes easy to miss

Problem:

Mocap connection, pose state, estimator logging, boundary checks, controller reading, and shutdown behavior are duplicated across scripts. This makes it likely that one script gets a safety fix while another remains unsafe.

Proposed solution:

After the next guarded test succeeds, extract a small shared module, for example:

- `aimslab/common/mocap.py`
- `aimslab/common/crazyflie_safety.py`
- `aimslab/common/controller.py`

Keep the first extraction small. The goal is not architecture polish; it is making preflight checks and shutdown behavior consistent.

## Recommended Fix Order

1. Stop using the older autonomous trajectory scripts for now.
2. Fix controller identity and pre-arm low-thrust gating.
3. Normalize mocap frame handling, especially `FLOOR_Z` and landing target behavior.
4. Add hard estimator agreement gates to `mocap-guarded-takeoff.py`.
5. Fix `manual_percent` mode semantics in `mocap-guarded-thrust-test.py`.
6. Add top-of-file unsafe warnings or confirmation gates to older autonomous scripts.
7. Clean whitespace separately.
8. Only after repeated guarded takeoff success, add a guarded 10 cm horizontal move script.
9. Only after that, revisit boundary mapping and figure-8 trajectories.

## Suggested Acceptance Criteria Before Next Autonomous Test

A low autonomous takeoff should not arm unless all of these are true:

- correct Crazyflie URI is printed and confirmed
- correct rigid body name is printed and tracked
- mocap pose age is fresh
- mocap pose is stable for at least 2 seconds
- start position is inside conservative bounds
- estimator position exists and is fresh
- estimator and mocap positions agree within tolerance
- operator explicitly confirms arming
- landing target uses the same frame convention as takeoff

For manual/controller tests:

- selected joystick device name matches Logitech/F310 or operator explicitly overrides
- thrust axis has emitted a fresh event
- thrust is low before arming
- timeout exits safely if any of the above fail

## Notes on What Looks Good

- `session.md` is useful and should be kept updated.
- The guarded takeoff and guarded thrust scripts are the right next-step shape.
- The branch correctly identified that high-level commander enablement is needed on this setup.
- The latest logger intentionally avoids opening the Crazyradio while `cfclient` owns it; that is the right constraint.
- The raw-thrust script's choice to keep mocap as an external safety monitor while disabling estimator writes for diagnosis is reasonable, as long as the mode is clearly documented and not confused with autonomous mocap flight.


## Session Update: 2026-06-23 Figure-Eight Script

The findings above remain the review baseline. The current experimental
`mocap-extpose-figure8.py` has since been changed to reduce some of the cited
risks: it uses position-only extpos by default, requires a received/fresh VRPN
pose before arming, waits for observed takeoff height, validates sampled
trajectory points, runs its generated path relative to the current position,
and monitors a measured cage polygon with an inward margin.

This is not a clearance for autonomous flight. The direct-VRPN and ROS2 frame
relationship is not yet independently proven, and the script still uses raw
mocap Z while commanding absolute takeoff/landing targets. The new 2 m cage
corner set is documented in `AIMSLAB_AUTONOMY_RUNBOOK.md`; it must be verified
against direct VRPN before any figure-eight run. `HOVER_ONLY_TEST = True`
remains the required configuration while verifying the frame and hover.
