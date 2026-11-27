import dataclasses
import tempfile
import unittest
from pathlib import Path

from opendbc.car.honda.modified_eps import ANGLE_RATE_LIMIT_MAX_DEG_S, DEFAULT_SETTINGS
from openpilot.common.params import Params
from openpilot.starpilot.car.honda.modified_eps import REFRESH_NS, ModifiedEpsPreferences, read_settings


class TestModifiedEpsPreferences(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.params = Params(str(Path(self.temporary.name) / 'params'))

  def test_unset_reads_the_registry_defaults(self):
    # except the Steering Angle Rate Limit: its registry default (300) is above the 170 deg/s ceiling, so it reads clamped
    self.assertEqual(read_settings(self.params), dataclasses.replace(DEFAULT_SETTINGS, angle_rate_limit_deg_s=ANGLE_RATE_LIMIT_MAX_DEG_S))

  def test_saved_angle_rate_limit_is_clamped_to_the_eps_slew_limit(self):
    for saved, expected in ((1000, 170.0), (171, 170.0), (170, 170.0), (100, 100.0), (0, 0.0)):
      self.params.put("HondaEpsAngleRateLimit", saved, block=True)
      self.assertEqual(read_settings(self.params).angle_rate_limit_deg_s, expected, saved)

  def test_saved_values_are_read_and_clamped(self):
    self.params.put("HondaOverrideStartTorque", 1840, block=True)
    self.params.put("HondaOverrideEndTorque", 700, block=True)
    self.params.put("HondaMinSteerSpeed", 0, block=True)
    self.params.put("HondaOverrideFadeUpSecs", 0.8, block=True)
    self.params.put("HondaOverrideTorqueScale", 250, block=True)
    settings = read_settings(self.params)
    self.assertEqual((settings.override_start_torque, settings.override_end_torque), (1840, 700))
    self.assertEqual(settings.min_steer_speed_mph, 0)
    self.assertAlmostEqual(settings.fade_up_s, 0.8)
    self.assertEqual(settings.torque_scale, 1.0)

  def test_refreshes_once_a_second(self):
    now = [0]
    preferences = ModifiedEpsPreferences(self.params, clock=lambda: now[0])
    self.params.put("HondaOverrideStartTorque", 1840, block=True)
    now[0] = REFRESH_NS - 1
    self.assertEqual(preferences.current().override_start_torque, 1560)
    now[0] = REFRESH_NS
    self.assertEqual(preferences.current().override_start_torque, 1840)


if __name__ == "__main__":
  unittest.main()
