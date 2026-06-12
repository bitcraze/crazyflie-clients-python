import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mocap_estimator_world_frame_calibrator import (
    AttitudeBaseline,
    ExtposSender,
    LocalFrameTransform,
    MOVEMENT_PHASES,
    MocapReader,
    MocapState,
    MovementPhase,
    capture_post_reset_attitude_baseline,
    make_row,
    parse_args,
    require_attitude_stability,
    require_position_convergence,
    run_movement_phases,
    shutdown_mocap_reader,
    validate_phase,
)


class FakeExtpos:
    def __init__(self):
        self.positions = []

    def send_extpos(self, *values):
        self.positions.append(values)


class BlockingCapture:
    def __init__(self):
        self.closed = threading.Event()
        self.rigidBodies = {}
        self.release_calls = []

    def waitForNextFrame(self):
        self.closed.wait()
        raise RuntimeError("capture closed")

    def close(self):
        self.release_calls.append("close")
        self.closed.set()

    def disconnect(self):
        self.release_calls.append("disconnect")

    def shutdown(self):
        self.release_calls.append("shutdown")


class FakeMotionCapture:
    def __init__(self):
        self.capture = BlockingCapture()
        self.connected = threading.Event()

    def connect(self, backend, options):
        del backend, options
        self.connected.set()
        return self.capture


class FakeEstimateState:
    def __init__(self, position=None, attitude=(0.0, 0.0, 0.0), battery=4.0):
        self.position = position
        self.attitude = attitude
        self.battery = battery

    def snapshot(self):
        now = time.time()
        return self.position, self.attitude, self.battery, now, now


class PositionValidatorTest(unittest.TestCase):
    def args(self, **overrides):
        values = {
            "pose_stale_timeout": 0.30,
            "max_estimator_error_m": 0.05,
            "convergence_duration": 2.0,
            "convergence_timeout": 3.0,
            "min_samples": 3,
            "min_movement_m": 0.08,
            "max_cross_axis_m": 0.05,
            "max_return_error_m": 0.05,
            "max_level_error_deg": 5.0,
            "max_yaw_drift_deg": 5.0,
            "attitude_stability_duration": 1.0,
            "attitude_stability_timeout": 2.0,
            "attitude_baseline_duration": 1.0,
            "rate_hz": 20.0,
            "expected_nose_front_yaw_deg": 0.0,
            "max_yaw_alignment_error_deg": 5.0,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def phase_rows(self, local, estimate=None, count=5):
        estimate = local if estimate is None else estimate
        rows = []
        for _ in range(count):
            error = sum(
                (estimate[index] - local[index]) ** 2 for index in range(3)
            ) ** 0.5
            rows.append({
                "mocap_age_s": 0.01,
                "estimate_age_s": 0.01,
                "estimate_attitude_age_s": 0.01,
                "local_mocap_x": local[0],
                "local_mocap_y": local[1],
                "local_mocap_z": local[2],
                "estimate_x": estimate[0],
                "estimate_y": estimate[1],
                "estimate_z": estimate[2],
                "estimate_roll_deg": 0.0,
                "estimate_pitch_deg": 0.0,
                "estimate_yaw_deg": -90.0,
                "yaw_drift_deg": 0.0,
                "estimate_error_m": error,
            })
        return rows

    def test_default_transform_matches_cage_physical_axes(self):
        transform = LocalFrameTransform(
            (10.0, 20.0, 30.0), ("neg-y", "pos-x", "pos-z")
        )
        self.assertEqual(transform.apply((11.0, 18.0, 33.0)), (2.0, 1.0, 3.0))

    def test_transform_rejects_duplicate_source_axis(self):
        with self.assertRaisesRegex(ValueError, "each raw axis exactly once"):
            LocalFrameTransform((0, 0, 0), ("pos-x", "neg-x", "pos-z"))

    def test_transform_rejects_left_handed_mapping(self):
        with self.assertRaisesRegex(ValueError, "left-handed"):
            LocalFrameTransform((0, 0, 0), ("pos-y", "pos-x", "pos-z"))

    def test_extpos_sender_streams_transformed_position_only(self):
        extpos = FakeExtpos()
        sender = ExtposSender(
            SimpleNamespace(extpos=extpos),
            LocalFrameTransform((1, 2, 3), ("neg-y", "pos-x", "pos-z")),
        )
        local = sender.send(1.5, 1.0, 3.25)
        self.assertEqual(local, (1.0, 0.5, 0.25))
        self.assertEqual(extpos.positions, [(1.0, 0.5, 0.25)])
        self.assertEqual(sender.snapshot()["extpos_sent_count"], 1)

    def test_position_convergence_uses_transformed_mocap(self):
        mocap = MocapState()
        mocap.update((1.0, 1.8, 3.0))
        estimate = FakeEstimateState((0.2, 0.0, 0.0))
        transform = LocalFrameTransform((1, 2, 3), ("neg-y", "pos-x", "pos-z"))
        fake_time = {"value": 0.0}

        def clock():
            return fake_time["value"]

        def sleep(duration):
            fake_time["value"] += duration
            mocap.last_update = time.time()

        require_position_convergence(
            self.args(), mocap, estimate, transform, clock=clock, sleep=sleep
        )
        self.assertGreaterEqual(fake_time["value"], 2.0)

    def test_attitude_stability_wraps_yaw_at_180_degrees(self):
        estimate = FakeEstimateState(
            (0.0, 0.0, 0.0), attitude=(1.0, -1.0, -179.0)
        )
        fake_time = {"value": 0.0}

        def clock():
            return fake_time["value"]

        def sleep(duration):
            fake_time["value"] += duration

        require_attitude_stability(
            self.args(), estimate, AttitudeBaseline(179.0),
            clock=clock, sleep=sleep,
        )
        self.assertGreaterEqual(fake_time["value"], 1.0)

    def test_post_reset_baseline_is_wrap_safe_and_requires_level(self):
        estimate = FakeEstimateState(
            (0.0, 0.0, 0.0), attitude=(1.0, -1.0, -179.0)
        )
        fake_time = {"value": 0.0}

        def clock():
            return fake_time["value"]

        def sleep(duration):
            fake_time["value"] += duration

        baseline = capture_post_reset_attitude_baseline(
            self.args(expected_nose_front_yaw_deg=-180.0),
            estimate, clock=clock, sleep=sleep,
        )
        self.assertAlmostEqual(baseline.yaw_deg, -179.0)

        estimate.attitude = (7.0, 0.0, -179.0)
        fake_time["value"] = 0.0
        with self.assertRaisesRegex(RuntimeError, "not level"):
            capture_post_reset_attitude_baseline(
                self.args(expected_nose_front_yaw_deg=-180.0),
                estimate, clock=clock, sleep=sleep,
            )

    def test_post_reset_baseline_rejects_nose_front_yaw_misalignment(self):
        estimate = FakeEstimateState(
            (0.0, 0.0, 0.0), attitude=(0.0, 0.0, 20.0)
        )
        fake_time = {"value": 0.0}

        def clock():
            return fake_time["value"]

        def sleep(duration):
            fake_time["value"] += duration

        with self.assertRaisesRegex(RuntimeError, "not aligned"):
            capture_post_reset_attitude_baseline(
                self.args(), estimate, clock=clock, sleep=sleep
            )

    def test_left_right_front_back_up_down_phases_have_expected_axes(self):
        expected = {
            "left": (1, 1),
            "right": (1, -1),
            "front": (0, 1),
            "back": (0, -1),
            "up": (2, 1),
            "down": (2, -1),
        }
        actual = {
            phase.name: (phase.axis, phase.sign)
            for phase in MOVEMENT_PHASES if phase.axis is not None
        }
        self.assertEqual(actual, expected)

    def test_directional_phase_accepts_correct_signed_movement(self):
        phase = MovementPhase("front", "front", 0, 1)
        validate_phase(self.phase_rows((0.10, 0.01, 0.0)), phase, self.args())

    def test_directional_phase_rejects_wrong_sign(self):
        phase = MovementPhase("front", "front", 0, 1)
        with self.assertRaisesRegex(RuntimeError, "wrong sign"):
            validate_phase(self.phase_rows((-0.10, 0.0, 0.0)), phase, self.args())

    def test_directional_phase_rejects_cross_axis_motion(self):
        phase = MovementPhase("up", "up", 2, 1)
        with self.assertRaisesRegex(RuntimeError, "cross-axis"):
            validate_phase(self.phase_rows((0.06, 0.0, 0.10)), phase, self.args())

    def test_return_phase_requires_origin(self):
        phase = MovementPhase("center", "center", None, 0)
        with self.assertRaisesRegex(RuntimeError, "return-to-origin"):
            validate_phase(self.phase_rows((0.06, 0.0, 0.0)), phase, self.args())

    def test_phase_rejects_estimator_disagreement(self):
        phase = MovementPhase("left", "left", 1, 1)
        with self.assertRaisesRegex(RuntimeError, "p90 error"):
            validate_phase(
                self.phase_rows((0.0, 0.10, 0.0), estimate=(0.0, 0.02, 0.0)),
                phase,
                self.args(),
            )

    def test_phase_rejects_yaw_drift(self):
        phase = MovementPhase("left", "left", 1, 1)
        rows = self.phase_rows((0.0, 0.10, 0.0))
        for row in rows:
            row["estimate_yaw_deg"] = -80.0
            row["yaw_drift_deg"] = 10.0
        with self.assertRaisesRegex(RuntimeError, "yaw drift"):
            validate_phase(rows, phase, self.args())

    def test_phase_rejects_non_level_attitude(self):
        phase = MovementPhase("left", "left", 1, 1)
        rows = self.phase_rows((0.0, 0.10, 0.0))
        for row in rows:
            row["estimate_roll_deg"] = 7.0
        with self.assertRaisesRegex(RuntimeError, "not level"):
            validate_phase(rows, phase, self.args())

    def test_movement_runner_executes_all_guided_phases(self):
        dependencies = [object() for _ in range(8)]
        with patch(
            "mocap_estimator_world_frame_calibrator.run_phase"
        ) as run_phase_mock:
            run_movement_phases(*dependencies)
        self.assertEqual(run_phase_mock.call_count, len(MOVEMENT_PHASES))
        self.assertEqual(
            [call.args[3].name for call in run_phase_mock.call_args_list],
            [phase.name for phase in MOVEMENT_PHASES],
        )

    def test_logged_row_contains_raw_local_and_estimate_positions(self):
        transform = LocalFrameTransform((1, 2, 3), ("neg-y", "pos-x", "pos-z"))
        mocap = MocapState()
        mocap.update((1.5, 1.0, 3.25), {
            "extpos_packet_sequence": 4,
            "extpos_sent_count": 4,
            "extpos_error_count": 0,
            "last_extpos_status": "sent",
            "last_extpos_error": "",
            "stream_local_x": 1.0,
            "stream_local_y": 0.5,
            "stream_local_z": 0.25,
        })
        estimate = FakeEstimateState((1.01, 0.49, 0.25))
        logged = make_row(
            time.time(), "left", time.time(), "hold", 1, 1,
            mocap, estimate, transform, AttitudeBaseline(-90.0),
        )
        self.assertEqual(logged["local_mocap_x"], 1.0)
        self.assertEqual(logged["local_mocap_y"], 0.5)
        self.assertEqual(logged["local_mocap_z"], 0.25)
        self.assertEqual(logged["last_extpos_status"], "sent")
        self.assertEqual(logged["estimate_yaw_deg"], 0.0)
        self.assertEqual(logged["yaw_baseline_deg"], -90.0)
        self.assertEqual(logged["yaw_drift_deg"], 90.0)
        self.assertEqual(logged["expected_nose_front_yaw_deg"], 0.0)
        self.assertEqual(logged["yaw_alignment_error_deg"], 90.0)
        self.assertLess(logged["estimate_error_m"], 0.02)

    def test_unstarted_reader_shutdown_is_safe(self):
        reader = MocapReader(FakeMotionCapture(), "host", "body", MocapState())
        shutdown_mocap_reader(reader, timeout=0.01)
        self.assertFalse(reader.is_alive())

    def test_reader_shutdown_releases_connection_and_joins(self):
        motioncapture = FakeMotionCapture()
        reader = MocapReader(motioncapture, "host", "body", MocapState())
        reader.start()
        self.assertTrue(motioncapture.connected.wait(timeout=1.0))
        shutdown_mocap_reader(reader, timeout=1.0)
        self.assertFalse(reader.is_alive())
        self.assertIsNone(reader.error)
        self.assertEqual(
            motioncapture.capture.release_calls,
            ["close", "disconnect", "shutdown"],
        )

    def test_cli_defaults_match_known_cage_mapping(self):
        args = parse_args([])
        self.assertEqual(
            (args.local_x_from, args.local_y_from, args.local_z_from),
            ("neg-y", "pos-x", "pos-z"),
        )
        self.assertEqual(args.min_movement_m, 0.08)
        self.assertEqual(args.max_estimator_error_m, 0.05)
        self.assertEqual(args.max_yaw_drift_deg, 5.0)
        self.assertEqual(args.expected_nose_front_yaw_deg, 0.0)

    def test_cli_rejects_duplicate_axis_mapping(self):
        with self.assertRaisesRegex(ValueError, "each raw axis exactly once"):
            parse_args([
                "--local-x-from", "pos-x",
                "--local-y-from", "neg-x",
                "--local-z-from", "pos-z",
            ])

    def test_cli_rejects_left_handed_axis_mapping(self):
        with self.assertRaisesRegex(ValueError, "left-handed"):
            parse_args([
                "--local-x-from", "pos-y",
                "--local-y-from", "pos-x",
                "--local-z-from", "pos-z",
            ])


if __name__ == "__main__":
    unittest.main()
