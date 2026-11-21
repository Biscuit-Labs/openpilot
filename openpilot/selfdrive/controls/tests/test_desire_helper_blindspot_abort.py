"""Blindspot abort of a committed lane change: window, re-signal latch, and alert timer."""

from types import SimpleNamespace
import unittest

from openpilot.cereal import log
from openpilot.common.constants import CV
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper
from openpilot.starpilot.lateral.lane_change_preferences import LaneChangePolicy


def car(**changes):
  values = {"vEgo": 30 * CV.MPH_TO_MS, "leftBlinker": False, "rightBlinker": False,
            "steeringPressed": False, "steeringTorque": 0.0, "leftBlindspot": False, "rightBlindspot": False}
  values.update(changes)
  return SimpleNamespace(**values)


def starting(policy, side="left"):
  helper = DesireHelper(policy)
  blinker = {"leftBlinker": True} if side == "left" else {"rightBlinker": True}
  torque = 1 if side == "left" else -1
  helper.update(car(**blinker), True, 1.0)
  helper.update(car(**blinker, steeringPressed=True, steeringTorque=torque), True, 1.0)
  assert helper.lane_change_state == log.LaneChangeState.laneChangeStarting
  return helper


class DesireHelperBlindspotAbortTests(unittest.TestCase):
  def test_abort_inside_the_window_left_and_right(self):
    policy = LaneChangePolicy(abort_on_blindspot=True)
    for side, spot in (("left", "leftBlindspot"), ("right", "rightBlindspot")):
      with self.subTest(side=side):
        for frames in (10, 38, 50, 58):  # 0.5, 1.9, 2.5 and 2.9 s into the maneuver
          helper = starting(policy, side)
          for _ in range(frames - 1):
            helper.update(car(**{"leftBlinker": side == "left", "rightBlinker": side == "right"}), True, 1.0)
          helper.update(car(**{"leftBlinker": side == "left", "rightBlinker": side == "right", spot: True}), True, 1.0)
          self.assertAlmostEqual(helper.lane_change_timer, 0.0)
          self.assertEqual((helper.lane_change_state, helper.lane_change_direction, helper.desire),
                           (log.LaneChangeState.off, log.LaneChangeDirection.none, log.Desire.none))
          self.assertTrue(helper.abort_latched)
          self.assertTrue(helper.lane_change_performed)
          self.assertTrue(helper.aborted_alert_active)

  def test_blindspot_past_the_abort_window_is_ignored(self):
    helper = starting(LaneChangePolicy(abort_on_blindspot=True))
    for _ in range(64):  # 3.2 s
      helper.update(car(leftBlinker=True), True, 1.0)
    helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)  # 3.25 s: past the abort window
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.laneChangeStarting)
    self.assertFalse(helper.abort_latched)
    helper.update(car(leftBlinker=True, leftBlindspot=True), True, 0.01)  # normal completion
    self.assertEqual((helper.lane_change_state, helper.lane_change_direction),
                     (log.LaneChangeState.off, log.LaneChangeDirection.none))

  def test_opposite_side_blindspot_is_ignored(self):
    helper = starting(LaneChangePolicy(abort_on_blindspot=True), "left")
    for _ in range(9):
      helper.update(car(leftBlinker=True), True, 1.0)
    helper.update(car(leftBlinker=True, rightBlindspot=True), True, 1.0)
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.laneChangeStarting)
    self.assertFalse(helper.abort_latched)

  def test_toggle_off_keeps_today_behavior(self):
    helper = starting(LaneChangePolicy())
    for _ in range(9):
      helper.update(car(leftBlinker=True), True, 1.0)
    helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.laneChangeStarting)
    self.assertFalse(helper.abort_latched)
    self.assertFalse(helper.aborted_alert_active)

  def test_held_signal_stays_off_until_released_then_re_signaled(self):
    helper = starting(LaneChangePolicy(abort_on_blindspot=True))
    for _ in range(9):
      helper.update(car(leftBlinker=True), True, 1.0)
    helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)
    for _ in range(5):
      helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)
      self.assertEqual(helper.lane_change_state, log.LaneChangeState.off)
    helper.update(car(), True, 1.0)
    self.assertFalse(helper.abort_latched)
    helper.update(car(leftBlinker=True), True, 1.0)
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.preLaneChange)

  def test_one_per_signal_false_still_requires_re_signal(self):
    policy = LaneChangePolicy(abort_on_blindspot=True, one_per_signal=False)
    helper = starting(policy)
    for _ in range(9):
      helper.update(car(leftBlinker=True), True, 1.0)
    helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)
    helper.update(car(leftBlinker=True, rightBlinker=True), True, 1.0)  # hazards are not a release
    helper.update(car(leftBlinker=True), True, 1.0)
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.off)  # the latch, not performed, blocks re-entry
    helper.update(car(), True, 1.0)
    helper.update(car(leftBlinker=True), True, 1.0)
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.preLaneChange)

  def test_auto_lane_change_is_aborted(self):
    policy = LaneChangePolicy(abort_on_blindspot=True, auto_lane_change=True, auto_delay_s=0.0, minimum_speed_mps=0.0)
    helper = DesireHelper(policy)
    helper.update(car(leftBlinker=True), True, 1.0, auto_evidence=True, engaged=True)
    helper.update(car(leftBlinker=True), True, 1.0, auto_evidence=True, engaged=True)
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.laneChangeStarting)
    for _ in range(9):
      helper.update(car(leftBlinker=True), True, 1.0, auto_evidence=True, engaged=True)
    helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0, auto_evidence=True, engaged=True)
    self.assertEqual((helper.lane_change_state, helper.lane_change_direction, helper.desire),
                     (log.LaneChangeState.off, log.LaneChangeDirection.none, log.Desire.none))
    self.assertTrue(helper.abort_latched)
    self.assertTrue(helper.aborted_alert_active)

  def test_preexisting_blindspot_still_blocks_start(self):
    helper = DesireHelper(LaneChangePolicy(abort_on_blindspot=True))
    helper.update(car(leftBlinker=True), True, 1.0)
    helper.update(car(leftBlinker=True, steeringPressed=True, steeringTorque=1, leftBlindspot=True), True, 1.0)
    self.assertEqual(helper.lane_change_state, log.LaneChangeState.preLaneChange)
    self.assertFalse(helper.abort_latched)
    self.assertFalse(helper.aborted_alert_active)

  def test_abort_alert_lastes_about_three_seconds(self):
    helper = starting(LaneChangePolicy(abort_on_blindspot=True))
    for _ in range(9):
      helper.update(car(leftBlinker=True), True, 1.0)
    helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)
    for _ in range(50):  # 2.5 s after the abort
      helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)
    self.assertTrue(helper.aborted_alert_active)
    for _ in range(12):  # 3.1 s after the abort
      helper.update(car(leftBlinker=True, leftBlindspot=True), True, 1.0)
    self.assertFalse(helper.aborted_alert_active)
    self.assertEqual(helper.abort_alert_timer, 0.0)


if __name__ == "__main__":
  unittest.main()
