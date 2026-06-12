import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import mocap_autonomy_ladder as ladder


class LadderTests(unittest.TestCase):
    def args(self):
        return SimpleNamespace(
            min_battery_v=3.75,
            landing_battery_v=3.60,
            critical_battery_v=3.30,
            max_level_deg=5.0,
            landing_tilt_deg=10.0,
            critical_tilt_deg=20.0,
            landing_guard_debounce_s=1.0,
            critical_guard_debounce_s=0.25,
            max_preflight_yaw_error_deg=5.0,
            max_flight_yaw_error_deg=10.0,
            max_estimator_error_m=0.05,
            emergency_estimator_error_m=0.08,
            max_local_height_m=0.12,
        )

    def inputs(self, local=(0, 0, 0), estimate=None, yaw=1, battery=4.0,
               roll=1.0, pitch=-1.0, now=None):
        now = time.time() if now is None else now
        estimate = local if estimate is None else estimate
        sample = ladder.PositionSample((1, 2, 3), local, now, 1)
        values = {
            "stateEstimate.x": estimate[0],
            "stateEstimate.y": estimate[1],
            "stateEstimate.z": estimate[2],
            "stateEstimate.roll": roll,
            "stateEstimate.pitch": pitch,
            "stateEstimate.yaw": yaw,
            "pm.vbat": battery,
        }
        times = {group: now for group in ("position", "velocity", "attitude", "power")}
        return sample, values, times

    def test_coordinate_transform(self):
        self.assertEqual(
            ladder.transform_mocap_position((12, 17, 34), (10, 20, 30)),
            (3, 2, 4),
        )

    def test_floor_origin_target_and_takeoff_event(self):
        self.assertEqual(ladder.floor_origin_target(0.07), (0, 0, 0.07))
        self.assertEqual(ladder.takeoff_event(0.07), "takeoff absolute_z=0.070")

    def test_preflight_uses_strict_battery_and_level_limits(self):
        now = time.time()
        sample, values, times = self.inputs(battery=3.71, now=now)
        with self.assertRaisesRegex(ladder.GuardTrip, "preflight") as caught:
            ladder.evaluate_guards(self.args(), sample, values, times, ladder.YawBaseline(0), "preflight", now)
        self.assertFalse(caught.exception.immediate_stop)
        sample, values, times = self.inputs(roll=5.1, now=now)
        with self.assertRaisesRegex(ladder.GuardTrip, "preflight"):
            ladder.evaluate_guards(self.args(), sample, values, times, ladder.YawBaseline(0), "preflight", now)

    def test_flight_battery_sag_does_not_immediately_stop(self):
        now = time.time()
        sample, values, times = self.inputs(battery=3.71, now=now)
        result = ladder.evaluate_guards(
            self.args(), sample, values, times, ladder.YawBaseline(0), "hover", now,
            ladder.GuardDebouncer(),
        )
        self.assertEqual(result.height_m, 0)

    def test_airborne_landing_guard_is_debounced(self):
        args = self.args()
        now = time.time()
        sample, values, times = self.inputs(battery=3.55, now=now)
        debounce = ladder.GuardDebouncer()
        ladder.evaluate_guards(args, sample, values, times, ladder.YawBaseline(0), "hover", now, debounce)
        later = now + 1.01
        times = {group: later for group in times}
        sample = ladder.PositionSample(sample.raw, sample.local, later, sample.frame_count)
        with self.assertRaises(ladder.GuardTrip) as caught:
            ladder.evaluate_guards(args, sample, values, times, ladder.YawBaseline(0), "hover", later, debounce)
        self.assertFalse(caught.exception.immediate_stop)

    def test_airborne_critical_tilt_is_debounced_emergency(self):
        args = self.args()
        now = time.time()
        sample, values, times = self.inputs(roll=21, now=now)
        debounce = ladder.GuardDebouncer()
        ladder.evaluate_guards(args, sample, values, times, ladder.YawBaseline(0), "hover", now, debounce)
        later = now + 0.26
        times = {group: later for group in times}
        sample = ladder.PositionSample(sample.raw, sample.local, later, sample.frame_count)
        with self.assertRaises(ladder.GuardTrip) as caught:
            ladder.evaluate_guards(args, sample, values, times, ladder.YawBaseline(0), "hover", later, debounce)
        self.assertTrue(caught.exception.immediate_stop)

    def test_ground_and_airborne_lateral_thresholds(self):
        self.assertEqual(ladder.lateral_limit_for_phase("takeoff", 0.019), 0.05)
        self.assertEqual(ladder.lateral_limit_for_phase("takeoff", 0.02), 0.03)
        now = time.time()
        sample, values, times = self.inputs((0.031, 0, 0.02), now=now)
        with self.assertRaisesRegex(ladder.GuardTrip, "lateral"):
            ladder.evaluate_guards(self.args(), sample, values, times, ladder.YawBaseline(0), "takeoff", now)

    def test_stale_mocap_and_estimator_are_immediate(self):
        now = time.time()
        sample, values, times = self.inputs(now=now)
        stale = ladder.PositionSample(sample.raw, sample.local, now - 1, 1)
        with self.assertRaises(ladder.GuardTrip) as caught:
            ladder.evaluate_guards(self.args(), stale, values, times, ladder.YawBaseline(0), "hover", now)
        self.assertTrue(caught.exception.immediate_stop)
        times["position"] = now - ladder.ESTIMATOR_STALE_S - 0.1
        with self.assertRaises(ladder.GuardTrip) as caught:
            ladder.evaluate_guards(self.args(), sample, values, times, ladder.YawBaseline(0), "hover", now)
        self.assertTrue(caught.exception.immediate_stop)

    def test_yaw_guard_is_immediate(self):
        now = time.time()
        sample, values, times = self.inputs(yaw=20.1, now=now)
        with self.assertRaisesRegex(ladder.GuardTrip, "yaw") as caught:
            ladder.evaluate_guards(self.args(), sample, values, times, ladder.YawBaseline(10), "hover", now)
        self.assertTrue(caught.exception.immediate_stop)

    def test_failure_classification(self):
        self.assertEqual(ladder.classify_failure(KeyboardInterrupt()), "emergency")
        self.assertEqual(ladder.classify_failure(ladder.GuardTrip("x", False)), "controlled-land")
        self.assertEqual(ladder.classify_failure(ladder.GuardTrip("x", True)), "emergency")

    def test_arm_confirmation_timeout_runs_emergency_cleanup(self):
        cf = Mock()
        result = ladder.EmergencyStopResult(40, 40, True, True)
        with patch.object(ladder, "wait_supervisor_state", return_value=False), patch.object(ladder, "emergency_stop", return_value=result) as stop:
            with self.assertRaisesRegex(RuntimeError, "Arming state uncertain"):
                ladder.arm(cf)
        stop.assert_called_once_with(cf)

    def test_emergency_stop_counts_packets_and_confirms_disarm(self):
        cf = Mock()
        cf.supervisor.is_armed = False
        with patch.object(ladder.time, "sleep", return_value=None):
            result = ladder.emergency_stop(cf)
        self.assertEqual(result.zero_thrust_sent, 40)
        self.assertEqual(result.stop_setpoints_sent, 40)
        self.assertTrue(result.disarm_requested)
        self.assertTrue(result.confirmed_disarmed)
        self.assertEqual(cf.commander.send_setpoint.call_count, 40)
        self.assertEqual(cf.commander.send_stop_setpoint.call_count, 40)

    def test_incomplete_emergency_result_cannot_write_proof(self):
        args = ladder.parse_args(["emergency-test"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proof.json"
            with self.assertRaisesRegex(RuntimeError, "not fully verified"):
                ladder.write_proof(path, args, ladder.EmergencyStopResult(39, 40, True, True))
            self.assertFalse(path.exists())

    def test_verified_proof_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proof.json"
            args = ladder.parse_args(["hover", "--emergency-proof", str(path)])
            with self.assertRaisesRegex(ValueError, "locked"):
                ladder.validate_args(args)
            result = ladder.EmergencyStopResult(40, 40, True, True)
            ladder.write_proof(path, args, result)
            ladder.validate_args(args)
            payload = json.loads(path.read_text())
            self.assertEqual(payload["test"], "props-off-ctrl-c-active-hlc-emergency-stop")

    def test_props_off_test_interrupts_active_hlc_and_writes_proof(self):
        cf = Mock()
        args = ladder.parse_args(["emergency-test"])
        result = ladder.EmergencyStopResult(40, 40, True, True)
        with tempfile.TemporaryDirectory() as directory:
            args.emergency_proof = str(Path(directory) / "proof.json")
            with patch("builtins.input", side_effect=["PROPS OFF", ""]), patch.object(ladder, "arm"), patch.object(ladder, "wait_supervisor_state", return_value=True), patch.object(ladder.time, "sleep", side_effect=KeyboardInterrupt), patch.object(ladder, "emergency_stop", return_value=result):
                ladder.run_emergency_test(cf, args)
            cf.high_level_commander.takeoff.assert_called_once_with(0.0, 30.0, yaw=None)
            self.assertTrue(Path(args.emergency_proof).exists())

    def test_defaults_and_locked_modes(self):
        args = ladder.parse_args(["emergency-test"])
        self.assertEqual((args.height, args.takeoff_duration, args.hover_duration, args.land_duration), (0.05, 5, 2, 6))
        self.assertEqual((args.min_battery_v, args.landing_battery_v, args.critical_battery_v), (3.75, 3.60, 3.30))
        for mode in ("x-step", "y-step", "figure8"):
            with self.assertRaisesRegex(ValueError, "locked"):
                ladder.validate_args(ladder.parse_args([mode]))


if __name__ == "__main__":
    unittest.main()
