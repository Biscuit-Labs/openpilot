import tempfile
import unittest
from pathlib import Path

from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
from openpilot.common.params import Params
from openpilot.starpilot.car.honda.modified_eps import REFRESH_NS, ModifiedEpsPreferences, read_settings


class TestModifiedEpsPreferences(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.params = Params(str(Path(self.temporary.name) / 'params'))

  def test_unset_reads_the_registry_defaults(self):
    self.assertEqual(read_settings(self.params), DEFAULT_SETTINGS)

  def test_saved_values_are_read_and_clamped(self):
    self.params.put("HondaDriverOverrideThreshold", 1840, block=True)
    self.params.put("HondaMinSteerSpeed", 0, block=True)
    self.params.put("HondaOverrideFadeUpSecs", 0.8, block=True)
    self.params.put("HondaOverrideTorqueScale", 250, block=True)
    self.params.put_bool("HondaSteerDeltaLimiter", True, block=True)
    settings = read_settings(self.params)
    self.assertEqual(settings.override_threshold, 1840)
    self.assertEqual(settings.min_steer_speed_mph, 0)
    self.assertAlmostEqual(settings.fade_up_s, 0.8)
    self.assertEqual(settings.torque_scale, 1.0)
    self.assertTrue(settings.delta_limiter)

  def test_refreshes_once_a_second(self):
    now = [0]
    preferences = ModifiedEpsPreferences(self.params, clock=lambda: now[0])
    self.params.put("HondaDriverOverrideThreshold", 1840, block=True)
    now[0] = REFRESH_NS - 1
    self.assertEqual(preferences.current().override_threshold, 2000)
    now[0] = REFRESH_NS
    self.assertEqual(preferences.current().override_threshold, 1840)


if __name__ == "__main__":
  unittest.main()
