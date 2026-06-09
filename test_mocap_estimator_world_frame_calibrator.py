import math
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mocap_estimator_world_frame_calibrator import (
    DEFAULT_PHASES,
    FilteredExtposeSender,
    MocapReader,
    MocapState,
    Quat,
    angle_error_deg,
    calibration_quaternions,
    compute_body_to_cf_quat,
    conjugate_quat,
    euler_from_quat_deg,
    multiply_quat,
    make_row,
    normalized_quat,
    parse_args,
    require_estimator_yaw_convergence,
    require_position_convergence,
    run_translation_phases,
    send_extpose_or_extpos,
    shutdown_mocap_reader,
    validate_orientation_rejection_rate,
    verify_calibration,
    verify_rotation_calibration,
    wait_for_orientation_baseline,
    yaw_quat,
)


def roll_quat(degrees):
    half = math.radians(degrees) / 2.0
    return Quat(math.sin(half), 0.0, 0.0, math.cos(half))


def row(
    quat, roll=0.0, pitch=0.0, yaw=-90.0, age=0.01,
    attitude_age=0.01, status='accepted',
):
    return {
        'mocap_qx': quat.x,
        'mocap_qy': quat.y,
        'mocap_qz': quat.z,
        'mocap_qw': quat.w,
        'mocap_age_s': age,
        'estimate_roll_deg': roll,
        'estimate_pitch_deg': pitch,
        'estimate_yaw_deg': yaw,
        'estimate_attitude_age_s': attitude_age,
        'orientation_packet_status': status,
    }


class FakeExtpos:
    def __init__(self):
        self.extposes = []
        self.extpositions = []

    def send_extpose(self, *values):
        self.extposes.append(values)

    def send_extpos(self, *values):
        self.extpositions.append(values)


class BlockingCapture:
    def __init__(self):
        self.closed = threading.Event()
        self.rigidBodies = {}
        self.release_calls = []

    def waitForNextFrame(self):
        self.closed.wait()
        raise RuntimeError('capture closed')

    def close(self):
        self.release_calls.append('close')
        self.closed.set()

    def disconnect(self):
        self.release_calls.append('disconnect')

    def shutdown(self):
        self.release_calls.append('shutdown')


class PollingCapture:
    def __init__(self):
        self.rigidBodies = {}

    def waitForNextFrame(self):
        threading.Event().wait(0.001)


class PollingMotionCapture:
    def __init__(self):
        self.capture = PollingCapture()
        self.connected = threading.Event()

    def connect(self, backend, options):
        self.connected.set()
        return self.capture


class FakeMotionCapture:
    def __init__(self):
        self.capture = BlockingCapture()
        self.connected = threading.Event()

    def connect(self, backend, options):
        self.connected.set()
        return self.capture


class CalibratorTest(unittest.TestCase):
    def verify_args(self, **overrides):
        values = {
            'nose_front_yaw_deg': -90.0,
            'max_level_error_deg': 5.0,
            'max_yaw_error_deg': 5.0,
            'max_sample_spread_deg': 3.0,
            'pose_stale_timeout': 0.30,
            'min_orientation_samples': 5,
            'position_convergence_error_m': 0.05,
            'position_convergence_duration': 2.0,
            'position_convergence_timeout': 3.0,
            'yaw_convergence_error_deg': 5.0,
            'yaw_convergence_duration': 1.0,
            'yaw_convergence_timeout': 3.0,
            'max_orientation_rejection_ratio': 0.01,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def assert_quat_equivalent(self, actual, expected, places=7):
        dot = abs(sum(a * b for a, b in zip(
            (actual.x, actual.y, actual.z, actual.w),
            (expected.x, expected.y, expected.z, expected.w),
        )))
        self.assertAlmostEqual(dot, 1.0, places=places)

    def test_compute_recovers_known_body_to_cf_transform(self):
        expected_cf = yaw_quat(-90.0)
        known_transform = normalized_quat(Quat(-0.70, 0.02, -0.05, 0.71))
        raw_body = multiply_quat(expected_cf, conjugate_quat(known_transform))
        rows = [row(raw_body) for _ in range(20)]

        computed, average, spread = compute_body_to_cf_quat(rows, -90.0)

        self.assert_quat_equivalent(average, raw_body)
        self.assert_quat_equivalent(computed, known_transform)
        self.assertAlmostEqual(spread, 0.0, places=6)
        corrected = multiply_quat(raw_body, computed)
        roll, pitch, yaw = euler_from_quat_deg(corrected)
        self.assertAlmostEqual(roll, 0.0, places=6)
        self.assertAlmostEqual(pitch, 0.0, places=6)
        self.assertAlmostEqual(angle_error_deg(yaw, -90.0), 0.0, places=6)

    def test_average_handles_quaternion_sign_flips_and_ignores_stale_rows(self):
        quat = normalized_quat(Quat(-0.997, 0.006, -0.004, -0.074))
        opposite = Quat(-quat.x, -quat.y, -quat.z, -quat.w)
        stale_outlier = yaw_quat(45.0)
        rows = [row(quat), row(opposite), row(stale_outlier, age=1.0)]

        _, average, spread = compute_body_to_cf_quat(rows, -90.0)

        self.assert_quat_equivalent(average, quat)
        self.assertAlmostEqual(spread, 0.0, places=6)

    def test_extpose_transmission_applies_computed_transform(self):
        extpos = FakeExtpos()
        cf = SimpleNamespace(extpos=extpos)
        raw = yaw_quat(10.0)
        transform = yaw_quat(-100.0)

        send_extpose_or_extpos(cf, 'extpose', 1.0, 2.0, 3.0, raw, transform)

        sent = extpos.extposes[0]
        corrected = normalized_quat(Quat(*sent[3:7]))
        _, _, yaw = euler_from_quat_deg(corrected)
        self.assertAlmostEqual(angle_error_deg(yaw, -90.0), 0.0, places=6)

    def test_quaternion_jump_falls_back_to_extpos(self):
        extpos = FakeExtpos()
        sender = FilteredExtposeSender(
            SimpleNamespace(extpos=extpos), yaw_jump_deg=45.0, jump_move_m=0.03
        )

        self.assertTrue(sender.send(1.0, 2.0, 0.03, yaw_quat(0.0)))
        self.assertFalse(sender.send(1.001, 2.0, 0.03, yaw_quat(90.0)))

        self.assertEqual(len(extpos.extposes), 1)
        self.assertEqual(len(extpos.extpositions), 1)
        self.assertEqual(sender.accepted, 1)
        self.assertEqual(sender.fallback, 1)
        self.assertAlmostEqual(sender.last_yaw, 0.0)

    def test_gradual_rotation_is_transmitted_as_extpose(self):
        extpos = FakeExtpos()
        sender = FilteredExtposeSender(
            SimpleNamespace(extpos=extpos), orientation_jump_deg=45.0
        )
        for yaw in (0.0, 30.0, 60.0, 90.0):
            self.assertTrue(sender.send(0.0, 0.0, 0.03, yaw_quat(yaw)))
        self.assertEqual(len(extpos.extposes), 4)
        self.assertEqual(extpos.extpositions, [])

    def test_roll_only_quaternion_jump_falls_back_to_extpos(self):
        extpos = FakeExtpos()
        sender = FilteredExtposeSender(
            SimpleNamespace(extpos=extpos), orientation_jump_deg=8.0
        )

        self.assertTrue(sender.send(0.0, 0.0, 0.03, roll_quat(0.0)))
        self.assertFalse(sender.send(0.0, 0.0, 0.03, roll_quat(15.0)))

        self.assertEqual(len(extpos.extposes), 1)
        self.assertEqual(len(extpos.extpositions), 1)
        self.assertIn('quaternion jump', sender.last_rejection_reason)
        self.assertAlmostEqual(sender.last_yaw, 0.0)

    def test_reset_orientation_baseline_accepts_first_valid_quaternion(self):
        extpos = FakeExtpos()
        sender = FilteredExtposeSender(
            SimpleNamespace(extpos=extpos), yaw_jump_deg=45.0
        )
        self.assertTrue(sender.send(0.0, 0.0, 0.03, yaw_quat(0.0)))
        self.assertFalse(sender.send(0.0, 0.0, 0.03, yaw_quat(90.0)))

        sender.reset_orientation_baseline()

        self.assertTrue(sender.send(0.0, 0.0, 0.03, yaw_quat(90.0)))
        self.assertAlmostEqual(sender.last_yaw, 90.0)
        self.assertEqual(len(extpos.extposes), 2)

    def test_translation_phases_reset_baseline_and_reconfirm_front_yaw(self):
        args = SimpleNamespace(nose_front_yaw_deg=-90.0)
        dependencies = [object() for _ in range(6)]

        with patch(
            'mocap_estimator_world_frame_calibrator.run_phase'
        ) as run_phase_mock:
            run_translation_phases(args, *dependencies)

        self.assertEqual(run_phase_mock.call_count, len(DEFAULT_PHASES))
        for call, (phase, description) in zip(
            run_phase_mock.call_args_list, DEFAULT_PHASES
        ):
            self.assertEqual(call.args[3:5], (phase, description))
            self.assertTrue(call.kwargs['require_convergence'])
            self.assertTrue(call.kwargs['reset_orientation_baseline'])
            self.assertEqual(call.kwargs['expected_yaw_deg'], -90.0)

    def test_wait_for_orientation_baseline_ignores_rejection_then_accepts(self):
        extpos = FakeExtpos()
        sender = FilteredExtposeSender(SimpleNamespace(extpos=extpos))
        sender.send(0.0, 0.0, 0.03, Quat(float('nan'), 0.0, 0.0, 1.0))
        fake_time = {'value': 0.0}

        def clock():
            return fake_time['value']

        def sleep(duration):
            fake_time['value'] += duration
            if fake_time['value'] >= 0.02 and not sender.has_orientation_baseline():
                sender.send(0.0, 0.0, 0.03, yaw_quat(90.0))

        wait_for_orientation_baseline(
            sender, timeout=0.1, clock=clock, sleep=sleep
        )
        self.assertTrue(sender.has_orientation_baseline())
        self.assertEqual(sender.rejected, 1)
        self.assertEqual(sender.accepted, 1)

    def test_unstarted_mocap_reader_shutdown_is_safe(self):
        reader = MocapReader(FakeMotionCapture(), 'host', 'body', MocapState())
        shutdown_mocap_reader(reader, timeout=0.01)
        self.assertFalse(reader.is_alive())

    def test_mocap_reader_shutdown_unblocks_and_joins(self):
        motioncapture = FakeMotionCapture()
        reader = MocapReader(motioncapture, 'host', 'body', MocapState())
        reader.start()
        self.assertTrue(motioncapture.connected.wait(timeout=1.0))

        shutdown_mocap_reader(reader, timeout=1.0)

        self.assertFalse(reader.is_alive())
        self.assertIsNone(reader.error)
        self.assertTrue(motioncapture.capture.closed.is_set())
        self.assertEqual(
            motioncapture.capture.release_calls,
            ['close', 'disconnect', 'shutdown'],
        )

    def test_destructor_only_mocap_reader_stops_on_its_own_thread(self):
        motioncapture = PollingMotionCapture()
        reader = MocapReader(motioncapture, 'host', 'body', MocapState())
        reader.start()
        self.assertTrue(motioncapture.connected.wait(timeout=1.0))

        shutdown_mocap_reader(reader, timeout=1.0)

        self.assertFalse(reader.is_alive())
        self.assertIsNone(reader.error)

    def test_mocap_state_copies_vrpn_orientation_values(self):
        state = MocapState()
        rotation = SimpleNamespace(x=0.1, y=0.2, z=0.3, w=0.9)

        state.update((1.0, 2.0, 3.0), rotation)
        _, stored, _, _ = state.snapshot()

        self.assertIsInstance(stored, Quat)
        self.assertIsNot(stored, rotation)
        self.assertEqual(stored, Quat(0.1, 0.2, 0.3, 0.9))

    def test_logged_row_contains_latest_orientation_decision(self):
        extpos = FakeExtpos()
        sender = FilteredExtposeSender(SimpleNamespace(extpos=extpos))
        mocap = MocapState()
        estimate = SimpleNamespace(snapshot=lambda: (None, None, 0.0, 0.0, 0.0))
        sender.send(0.0, 0.0, 0.03, yaw_quat(0.0))
        mocap.update(
            (0.0, 0.0, 0.03), yaw_quat(0.0), sender.snapshot()
        )

        logged = make_row(0.0, 'phase', 0.0, 'hold', mocap, estimate, sender)

        self.assertEqual(logged['orientation_packet_status'], 'accepted')
        self.assertEqual(logged['orientation_accepted_count'], 1)
        self.assertEqual(logged['orientation_rejected_count'], 0)
        self.assertAlmostEqual(logged['corrected_mocap_roll_deg'], 0.0)
        self.assertAlmostEqual(logged['corrected_mocap_pitch_deg'], 0.0)
        self.assertAlmostEqual(logged['corrected_mocap_yaw_deg'], 0.0)

    def test_rejected_packet_logs_candidate_corrected_euler(self):
        extpos = FakeExtpos()
        sender = FilteredExtposeSender(
            SimpleNamespace(extpos=extpos), orientation_jump_deg=8.0
        )
        mocap = MocapState()
        estimate = SimpleNamespace(snapshot=lambda: (None, None, 0.0, 0.0, 0.0))
        sender.send(0.0, 0.0, 0.03, roll_quat(0.0))
        rejected = roll_quat(15.0)
        self.assertFalse(sender.send(0.0, 0.0, 0.03, rejected))
        mocap.update((0.0, 0.0, 0.03), rejected, sender.snapshot())

        logged = make_row(0.0, 'phase', 0.0, 'hold', mocap, estimate)

        self.assertEqual(logged['orientation_packet_status'], 'rejected')
        self.assertAlmostEqual(logged['corrected_mocap_roll_deg'], 15.0)
        self.assertAlmostEqual(logged['corrected_mocap_pitch_deg'], 0.0)
        self.assertAlmostEqual(logged['corrected_mocap_yaw_deg'], 0.0)

    def test_rejection_rate_above_limit_fails_phase(self):
        counts = {'accepted': 98, 'fallback': 2, 'rejected': 2}
        with self.assertRaisesRegex(RuntimeError, 'rejection rate'):
            validate_orientation_rejection_rate(self.verify_args(), counts)

    def test_rejection_rate_at_limit_passes_phase(self):
        counts = {'accepted': 99, 'fallback': 1, 'rejected': 1}
        validate_orientation_rejection_rate(self.verify_args(), counts)

    def test_position_convergence_requires_continuous_two_seconds(self):
        mocap = MocapState()
        estimate = SimpleNamespace()
        mocap.update((0.0, 0.0, 0.03), yaw_quat(0.0))
        estimate_state = __import__(
            'mocap_estimator_world_frame_calibrator'
        ).EstimateState()
        estimate_state.update_position(0.01, 0.0, 0.03, 4.0)
        fake_time = {'value': 0.0}

        def clock():
            return fake_time['value']

        def sleep(duration):
            fake_time['value'] += duration

        require_position_convergence(
            self.verify_args(), mocap, estimate_state,
            clock=clock, sleep=sleep,
        )
        self.assertGreaterEqual(fake_time['value'], 2.0)

    def test_yaw_convergence_requires_continuous_fresh_agreement(self):
        estimate_state = __import__(
            'mocap_estimator_world_frame_calibrator'
        ).EstimateState()
        estimate_state.update_attitude(0.0, 0.0, -89.0)
        fake_time = {'value': 0.0}

        def clock():
            return fake_time['value']

        def sleep(duration):
            fake_time['value'] += duration

        require_estimator_yaw_convergence(
            self.verify_args(), estimate_state, -90.0,
            clock=clock, sleep=sleep,
        )
        self.assertGreaterEqual(fake_time['value'], 1.0)

    def test_verification_accepts_level_nose_front_samples(self):
        transform = yaw_quat(-100.0)
        raw = yaw_quat(10.0)
        rows = [row(raw, roll=0.5, pitch=-0.5, yaw=-89.0) for _ in range(10)]
        verify_calibration(rows, transform, self.verify_args())

    def test_left_and_right_90_rotation_verification(self):
        transform = yaw_quat(-100.0)
        left_raw = yaw_quat(100.0)
        right_raw = yaw_quat(-80.0)
        left_rows = [row(left_raw, yaw=0.0) for _ in range(5)]
        right_rows = [row(right_raw, yaw=-180.0) for _ in range(5)]

        verify_rotation_calibration(
            left_rows, transform, self.verify_args(), 90.0
        )
        verify_rotation_calibration(
            right_rows, transform, self.verify_args(), -90.0
        )

    def test_rotation_verification_rejects_wrong_turn_direction(self):
        transform = yaw_quat(-100.0)
        rows = [row(yaw_quat(-80.0), yaw=-180.0) for _ in range(5)]
        with self.assertRaisesRegex(RuntimeError, 'mocap yaw'):
            verify_rotation_calibration(
                rows, transform, self.verify_args(), 90.0
            )

    def test_verification_rejects_wrong_physical_frame(self):
        transform = yaw_quat(-100.0)
        wrong_raw = yaw_quat(35.0)
        rows = [row(wrong_raw, yaw=-65.0) for _ in range(10)]
        with self.assertRaisesRegex(RuntimeError, 'mocap yaw'):
            verify_calibration(rows, transform, self.verify_args())

    def test_invalid_quaternions_do_not_count_as_fresh_samples(self):
        invalid = Quat(float('nan'), 0.0, 0.0, 1.0)
        rows = [row(invalid), row(yaw_quat(10.0))]
        with self.assertRaisesRegex(RuntimeError, 'fresh orientation samples'):
            compute_body_to_cf_quat(rows, -90.0, min_samples=2)

    def test_rejected_orientation_rows_are_excluded(self):
        accepted = yaw_quat(10.0)
        rejected = yaw_quat(120.0)
        rows = [
            row(accepted),
            row(rejected, status='rejected'),
            row(accepted),
        ]

        samples = calibration_quaternions(rows)
        computed, _, _ = compute_body_to_cf_quat(
            rows, -90.0, min_samples=2
        )

        self.assertEqual(len(samples), 2)
        self.assert_quat_equivalent(computed, yaw_quat(-100.0))

    def test_compute_requires_enough_fresh_samples(self):
        raw = yaw_quat(10.0)
        rows = [row(raw), row(raw, age=1.0)]
        with self.assertRaisesRegex(RuntimeError, 'fresh orientation samples'):
            compute_body_to_cf_quat(
                rows, -90.0, pose_stale_timeout=0.30, min_samples=2
            )

    def test_verification_ignores_one_isolated_orientation_outlier(self):
        transform = yaw_quat(-100.0)
        rows = [row(yaw_quat(10.0)) for _ in range(19)]
        rows.append(row(yaw_quat(80.0), yaw=-90.0))
        verify_calibration(rows, transform, self.verify_args())

    def test_verification_rejects_sustained_orientation_error(self):
        transform = yaw_quat(-100.0)
        rows = [row(yaw_quat(10.0)) for _ in range(5)]
        rows.extend(row(yaw_quat(25.0), yaw=-75.0) for _ in range(5))
        with self.assertRaisesRegex(RuntimeError, 'mocap yaw|spread'):
            verify_calibration(rows, transform, self.verify_args())

    def test_verification_rejects_stale_estimator_attitude(self):
        transform = yaw_quat(-100.0)
        rows = [
            row(yaw_quat(10.0), attitude_age=1.0)
            for _ in range(5)
        ]
        with self.assertRaisesRegex(RuntimeError, 'fresh estimator attitude'):
            verify_calibration(rows, transform, self.verify_args())

    def test_cli_defaults_match_cage_front_direction(self):
        args = parse_args([])
        self.assertEqual(args.pose_mode, 'extpose')
        self.assertEqual(args.nose_front_yaw_deg, -90.0)
        self.assertEqual(args.max_sample_spread_deg, 3.0)
        self.assertEqual(args.min_orientation_samples, 20)
        self.assertEqual(args.yaw_jump_deg, 45.0)
        self.assertEqual(args.yaw_jump_move_m, 0.03)
        self.assertEqual(args.orientation_jump_deg, 8.0)
        self.assertEqual(args.max_orientation_rejection_ratio, 0.01)
        self.assertEqual(args.position_convergence_error_m, 0.05)
        self.assertEqual(args.position_convergence_duration, 2.0)
        self.assertEqual(args.yaw_convergence_error_deg, 5.0)
        self.assertEqual(args.yaw_convergence_duration, 1.0)
        with self.assertRaisesRegex(ValueError, 'min-orientation-samples'):
            parse_args(['--min-orientation-samples', '0'])
        with self.assertRaisesRegex(ValueError, 'hold-duration'):
            parse_args([
                '--hold-duration', '0.5', '--rate-hz', '20',
                '--min-orientation-samples', '20',
            ])


if __name__ == '__main__':
    unittest.main()
