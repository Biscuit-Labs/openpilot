"""The selfdrived path from modeld's blindspot-abort status on laneChangeAssistWire to the Take Control alert."""
import unittest
from unittest.mock import patch

from openpilot.selfdrive.selfdrived.tests.test_force_stop_alert import NOW, fixture
from openpilot.starpilot.lateral.lane_change_status_wire import Direction, LaneChangeStatus, Phase, encode

WIRE = 'laneChangeAssistWire'


def status(phase, valid_until=NOW + 1_000_000_000):
  return LaneChangeStatus("abort-test", 1, 1, NOW - 50_000_000, NOW - 10_000_000, valid_until, phase, Direction.NONE,
                          False, True)


class TestLaneChangeAbortAlert(unittest.TestCase):
  def setUp(self):
    self.drive, self.cs = fixture()
    self.cs.standstill = False
    self.drive.sm['starpilotLongitudinalPlan'].forceStopHolding = False  # keep the fixture's Force Stop alert out of the way
    self.drive.sm['longitudinalPlan'].shouldStop = False

  def update(self, raw=None, seen=True):
    sm = self.drive.sm
    if raw is not None:
      sm.data[WIRE] = raw
      sm.seen[WIRE] = seen  # seen, valid and alive are one dict in the fixture
    with patch('openpilot.selfdrive.selfdrived.selfdrived.time.monotonic_ns', return_value=NOW):
      self.drive.update_alerts(self.cs)
    alert = self.drive.AM.current_alert
    return (alert.alert_text_1, alert.alert_text_2)

  def test_aborted_status_shows_take_control(self):
    self.assertEqual(self.update(encode(status(Phase.ABORTED_BLINDSPOT))),
                     ("Take Control", "Lane Change Aborted: Vehicle in Blind Spot"))

  def test_expired_status_shows_nothing(self):
    self.assertNotEqual(self.update(encode(status(Phase.ABORTED_BLINDSPOT, valid_until=NOW - 1)))[0], "Take Control")

  def test_other_phases_show_nothing(self):
    for phase in (Phase.MANUAL_REQUIRED, Phase.WAITING_FOR_DELAY, Phase.LANE_UNAVAILABLE, Phase.BLINDSPOT_BLOCKED):
      with self.subTest(phase=phase):
        self.setUp()
        self.assertNotEqual(self.update(encode(status(phase)))[0], "Take Control")

  def test_unseen_or_garbled_wire_shows_nothing(self):
    self.assertNotEqual(self.update(encode(status(Phase.ABORTED_BLINDSPOT)), seen=False)[0], "Take Control")
    self.setUp()
    self.assertNotEqual(self.update(b'\x00garbage')[0], "Take Control")

  def test_stand_in_without_the_service_does_not_crash(self):
    sm = self.drive.sm
    for table in (sm.data, sm.seen, sm.logMonoTime, sm.recv_time):
      table.pop(WIRE, None)
    self.assertNotEqual(self.update()[0], "Take Control")


if __name__ == "__main__":
  unittest.main()
