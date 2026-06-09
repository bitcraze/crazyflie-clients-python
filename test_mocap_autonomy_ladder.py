import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mocap_autonomy_ladder import (
    FilteredExtposeSender,
    FilteredPoseState,
    GuardTrip,
    MocapState,
    PoseStreamStats,
    Quat,
    TelemetryState,
    angle_error_deg,
    check_guards,
    controlled_land,
    figure8_local_target,
    go_to,
    log_sample,
    parse_args,
    raw_target,
    takeoff_only,
    validate_args,
    validate_roll_pitch_frame,
    validate_stream_health,
)


def euler_quat(roll=0.0, pitch=0.0, yaw=0.0):
    roll, pitch, yaw = map(lambda value: math.radians(value) / 2.0, (roll, pitch, yaw))
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return Quat(
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def yaw_quat(degrees):
    return euler_quat(yaw=degrees)


class FakeExtpos:
    def __init__(self, fail=False):
        self.extposes = []
        self.extpositions = []
        self.fail = fail

    def send_extpose(self, *values):
        if self.fail:
            raise RuntimeError("radio send failed")
        self.extposes.append(values)

    def send_extpos(self, *values):
        if self.fail:
            raise RuntimeError("radio send failed")
        self.extpositions.append(values)


class FakeLogger:
    def __init__(self):
        self.rows = []

    def write(self, row):
        self.rows.append(row)


class FakeHlc:
    def __init__(self):
        self.go_to_calls = []
        self.takeoff_calls = []
        self.land_calls = []

    def go_to(self, *args, **kwargs):
        self.go_to_calls.append((args, kwargs))

    def takeoff(self, *args, **kwargs):
        self.takeoff_calls.append((args, kwargs))

    def land(self, *args, **kwargs):
        self.land_calls.append((args, kwargs))


class MocapAutonomyLadderTest(unittest.TestCase):
    def safety_args(self, **overrides):
        values = {
            "body_to_cf_quat": (0.0, 0.0, 0.0, 1.0),
            "max_orientation_rejection_ratio": 0.01,
            "orientation_rejection_min_samples": 20,
            "max_consecutive_orientation_rejections": 2,
            "max_filtered_orientation_age": 0.30,
            "max_landing_lateral_error": 0.05,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def make_sender(self, extpos=None, body_to_cf=None):
        extpos = extpos or FakeExtpos()
        filtered = FilteredPoseState()
        stats = PoseStreamStats()
        sender = FilteredExtposeSender(
            SimpleNamespace(extpos=extpos), stats, filtered, body_to_cf
        )
        return sender, extpos, stats, filtered

    def populated_states(self, raw_yaw=0.0, filtered_yaw=0.0, estimate_yaw=0.0):
        mocap, telemetry, filtered = MocapState(), TelemetryState(), FilteredPoseState()
        mocap.update((0.0, 0.0, 0.03), yaw_quat(raw_yaw))
        filtered.update((0.0, 0.0, 0.03), yaw_quat(filtered_yaw))
        telemetry.update("estimate", {
            "stateEstimate.x": 0.0,
            "stateEstimate.y": 0.0,
            "stateEstimate.z": 0.03,
            "stateEstimate.yaw": estimate_yaw,
            "stateEstimate.roll": 0.0,
            "stateEstimate.pitch": 0.0,
        })
        return mocap, telemetry, filtered

    def accepted_stats(self):
        stats = PoseStreamStats()
        stats.update("accepted")
        return stats

    def test_angle_error_wraps(self):
        self.assertAlmostEqual(angle_error_deg(-179.0, 179.0), 2.0)
        self.assertAlmostEqual(angle_error_deg(179.0, -179.0), -2.0)

    def test_raw_target_uses_start_as_origin(self):
        target = raw_target((1.0, -2.0, 0.03), (0.03, -0.02, 0.05))
        for actual, expected in zip(target, (1.03, -2.02, 0.08)):
            self.assertAlmostEqual(actual, expected)

    def test_figure8_returns_to_origin(self):
        start = figure8_local_target(0.03, 0.02, 35.0, 0.0, 0.06)
        end = figure8_local_target(0.03, 0.02, 35.0, 35.0, 0.06)
        self.assertEqual(start, (0.0, 0.0, 0.06))
        self.assertAlmostEqual(end[0], 0.0, places=9)
        self.assertAlmostEqual(end[1], 0.0, places=9)

    def test_rejected_yaw_retains_last_accepted_filtered_orientation(self):
        sender, extpos, stats, filtered = self.make_sender()
        self.assertTrue(sender.send(1.0, 2.0, 0.03, yaw_quat(5.0)))
        self.assertFalse(sender.send(1.001, 2.0, 0.03, yaw_quat(100.0)))
        position, quat, yaw, timestamp = filtered.snapshot()
        self.assertEqual(position, (1.0, 2.0, 0.03))
        self.assertIsNotNone(quat)
        self.assertAlmostEqual(yaw, 5.0)
        self.assertGreater(timestamp, 0.0)
        self.assertEqual(len(extpos.extpositions), 1)
        self.assertEqual(stats.snapshot()["orientation_rejected_count"], 1)
        self.assertEqual(stats.snapshot()["consecutive_orientation_rejection_count"], 1)

    def test_invalid_quaternion_is_not_transmitted_as_extpose(self):
        sender, extpos, stats, filtered = self.make_sender()
        invalid_quats = [Quat(float("nan"), 0.0, 0.0, 1.0), Quat(0.0, 0.0, 0.0, 0.2)]
        for quat in invalid_quats:
            self.assertFalse(sender.send(0.0, 0.0, 0.03, quat))
        self.assertEqual(extpos.extposes, [])
        self.assertEqual(len(extpos.extpositions), 2)
        self.assertIsNone(filtered.snapshot()[1])
        self.assertEqual(stats.snapshot()["orientation_rejected_count"], 2)

    def test_calibrated_body_transform_is_sent_and_stored(self):
        transform = yaw_quat(90.0)
        sender, extpos, _, filtered = self.make_sender(body_to_cf=transform)
        self.assertTrue(sender.send(0.0, 0.0, 0.03, yaw_quat(0.0)))
        sent = extpos.extposes[0]
        self.assertAlmostEqual(sent[5], transform.z)
        self.assertAlmostEqual(sent[6], transform.w)
        self.assertAlmostEqual(filtered.snapshot()[2], 90.0)

    def test_yaw_guard_and_log_use_filtered_yaw_not_raw_sample(self):
        mocap, telemetry, filtered = self.populated_states(raw_yaw=100.0, filtered_yaw=5.0, estimate_yaw=5.0)
        args = self.safety_args()
        check_guards(
            args, mocap, telemetry, self.accepted_stats(), filtered,
            (0.0, 0.0, 0.03), (0.0, 0.0, 0.05), "hover",
        )
        logger = FakeLogger()
        log_sample(logger, args, mocap, telemetry, PoseStreamStats(), filtered, (0.0, 0.0, 0.03), (0.0, 0.0, 0.05), "hover", "hold", "ok")
        self.assertAlmostEqual(logger.rows[-1]["mocap_yaw_deg"], 100.0)
        self.assertAlmostEqual(logger.rows[-1]["filtered_yaw_deg"], 5.0)
        self.assertAlmostEqual(logger.rows[-1]["yaw_error_deg"], 0.0)

    def test_props_off_roll_pitch_frame_validation(self):
        args = self.safety_args()
        filtered = FilteredPoseState()
        filtered.update((0.0, 0.0, 0.03), euler_quat(roll=8.0, pitch=-6.0, yaw=20.0))
        roll_error, pitch_error = validate_roll_pitch_frame(
            args, {"stateEstimate.roll": 8.5, "stateEstimate.pitch": -5.5}, filtered
        )
        self.assertLess(roll_error, 1.0)
        self.assertLess(pitch_error, 1.0)
        with self.assertRaisesRegex(GuardTrip, "roll/pitch frame error"):
            validate_roll_pitch_frame(
                args, {"stateEstimate.roll": -20.0, "stateEstimate.pitch": -5.5}, filtered
            )

    def test_controlled_landing_uses_live_monitor_and_preserved_yaw(self):
        hlc = FakeHlc()
        cf = SimpleNamespace(high_level_commander=hlc)
        args = SimpleNamespace(land_duration=6.0)
        with patch("mocap_autonomy_ladder.monitor") as monitor_mock, \
                patch("mocap_autonomy_ladder.emergency_stop") as stop_mock:
            controlled_land(
                cf, args, object(), object(), object(), object(), object(),
                (1.0, 2.0, 0.03), math.radians(37.0),
            )
        self.assertEqual(hlc.land_calls[0][0], (0.03, 6.0))
        self.assertAlmostEqual(hlc.land_calls[0][1]["yaw"], math.radians(37.0))
        monitor_mock.assert_called_once()
        stop_mock.assert_called_once_with(cf)

    def test_validation_fails_on_stream_errors_and_excessive_rejection(self):
        args = self.safety_args(max_orientation_rejection_ratio=0.01)
        errors = PoseStreamStats()
        errors.update("error")
        with self.assertRaisesRegex(GuardTrip, "transmission error"):
            validate_stream_health(args, errors)
        rejected = PoseStreamStats()
        for _ in range(19):
            rejected.update("accepted")
        rejected.update("fallback", "jump")
        with self.assertRaisesRegex(GuardTrip, "rejection ratio"):
            validate_stream_health(args, rejected)

    def test_stream_health_rejects_burst_and_stale_filtered_orientation(self):
        args = self.safety_args()
        burst = PoseStreamStats()
        for _ in range(3):
            burst.update("fallback", "jump")
        with self.assertRaisesRegex(GuardTrip, "consecutive orientation"):
            validate_stream_health(args, burst)

        filtered = FilteredPoseState()
        filtered.update((0.0, 0.0, 0.03), yaw_quat(0.0))
        filtered.timestamp -= 1.0
        with self.assertRaisesRegex(GuardTrip, "last accepted orientation age"):
            validate_stream_health(args, PoseStreamStats(), filtered)

    def test_go_to_preserves_initial_validated_yaw_in_radians(self):
        hlc = FakeHlc()
        cf = SimpleNamespace(high_level_commander=hlc)
        args = SimpleNamespace(step_duration=3.0)
        with patch("mocap_autonomy_ladder.monitor") as monitor_mock:
            go_to(
                cf, args, object(), object(), object(), object(), object(),
                object(), (1.0, 2.0, 0.03), (0.03, 0.0, 0.05),
                "x-step", math.radians(42.0),
            )
        self.assertAlmostEqual(hlc.go_to_calls[0][0][3], math.radians(42.0))
        monitor_mock.assert_called_once()

    def test_takeoff_uses_preserved_yaw_in_radians(self):
        hlc = FakeHlc()
        cf = SimpleNamespace(high_level_commander=hlc)
        args = SimpleNamespace(height=0.05, takeoff_duration=5.0)
        mocap = SimpleNamespace(
            snapshot=lambda: SimpleNamespace(position=(1.0, 2.0, 0.08))
        )
        with patch("mocap_autonomy_ladder.monitor") as monitor_mock:
            takeoff_only(
                cf, args, object(), object(), mocap, object(), object(), object(),
                (1.0, 2.0, 0.03), math.radians(90.0),
            )
        self.assertEqual(hlc.takeoff_calls[0][0], (0.08, 5.0))
        self.assertAlmostEqual(
            hlc.takeoff_calls[0][1]["yaw"], math.radians(90.0)
        )
        monitor_mock.assert_called_once()

    def test_landing_guard_limits_lateral_drift(self):
        args = self.safety_args()
        mocap, telemetry, filtered = self.populated_states()
        mocap.update((0.051, 0.0, 0.03), yaw_quat(0.0))
        telemetry.update("estimate", {
            "stateEstimate.x": 0.051, "stateEstimate.y": 0.0,
            "stateEstimate.z": 0.03, "stateEstimate.yaw": 0.0,
            "stateEstimate.roll": 0.0, "stateEstimate.pitch": 0.0,
        })
        with self.assertRaisesRegex(GuardTrip, "landing lateral error"):
            check_guards(
                args, mocap, telemetry, self.accepted_stats(), filtered,
                (0.0, 0.0, 0.03), (0.0, 0.0, 0.0), "land",
            )

    def test_takeoff_guard_tightens_above_two_centimeters(self):
        args = self.safety_args()
        stats = self.accepted_stats()
        mocap, telemetry, filtered = self.populated_states()
        start = (0.0, 0.0, 0.03)
        mocap.update((0.04, 0.0, 0.04), yaw_quat(0.0))
        telemetry.update("estimate", {"stateEstimate.x": 0.04, "stateEstimate.y": 0.0, "stateEstimate.z": 0.04, "stateEstimate.yaw": 0.0, "stateEstimate.roll": 0.0, "stateEstimate.pitch": 0.0})
        check_guards(args, mocap, telemetry, stats, filtered, start, (0.0, 0.0, 0.05), "takeoff")
        mocap.update((0.04, 0.0, 0.06), yaw_quat(0.0))
        telemetry.update("estimate", {"stateEstimate.x": 0.04, "stateEstimate.y": 0.0, "stateEstimate.z": 0.06, "stateEstimate.yaw": 0.0, "stateEstimate.roll": 0.0, "stateEstimate.pitch": 0.0})
        with self.assertRaisesRegex(GuardTrip, "takeoff lateral error"):
            check_guards(args, mocap, telemetry, stats, filtered, start, (0.0, 0.0, 0.05), "takeoff")

    def test_calibration_is_required_and_mode_is_renamed(self):
        with self.assertRaisesRegex(ValueError, "body-to-cf-quat"):
            validate_args(parse_args(["hover"]))
        args = parse_args([
            "takeoff-land-test", "--body-to-cf-quat", "0", "0", "0", "1",
        ])
        validate_args(args)
        self.assertEqual(args.mode, "takeoff-land-test")

    def test_cli_defaults_are_conservative(self):
        args = parse_args(["hover"])
        self.assertEqual((args.height, args.takeoff_duration, args.land_duration, args.step), (0.05, 5.0, 6.0, 0.03))
        self.assertEqual(args.max_orientation_rejection_ratio, 0.01)

    def test_figure8_requires_explicit_enable(self):
        with self.assertRaisesRegex(ValueError, "disabled"):
            validate_args(parse_args(["figure8"]))
        validate_args(parse_args([
            "figure8", "--enable-figure8", "--body-to-cf-quat", "0", "0", "0", "1",
        ]))


if __name__ == "__main__":
    unittest.main()
