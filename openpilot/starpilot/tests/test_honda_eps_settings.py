import tempfile
import unittest
from pathlib import Path

from openpilot.common.params import Params
from openpilot.starpilot.honda_eps_settings import (HONDA_EPS_KEY_RENAMES, HONDA_EPS_PRESERVED_KEYS, ANGLE_DEFAULTS_RESET_KEY,
                                                      migrate_honda_eps_param_names, reset_angle_defaults_once)
from openpilot.starpilot.state_migration import OPERATIONAL_KEYS, prepare_manager_start


class TestHondaEpsSettings(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.params = Params(str(self.root / 'params'))
    self.storage = self.root / 'recovery'

  def write_raw(self, key, raw):
    path = Path(self.params.get_param_path(key))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)

  def test_registry_covers_the_renames(self):
    known = {k.decode() for k in self.params.all_keys()}
    self.assertTrue(HONDA_EPS_PRESERVED_KEYS <= known)
    self.assertTrue(set(HONDA_EPS_KEY_RENAMES.values()) <= HONDA_EPS_PRESERVED_KEYS)
    self.assertFalse(set(HONDA_EPS_KEY_RENAMES) & known)
    self.assertTrue(HONDA_EPS_PRESERVED_KEYS <= OPERATIONAL_KEYS)

  def test_old_names_move_to_the_current_ones(self):
    # the Clarity's values on route 0000038c, saved under vfn's pre-10-10 names
    self.write_raw("NrdrLatAngleRateLimit", b"219")
    self.write_raw("NrdrLatUseFirmwareVgr", b"1")
    self.write_raw("HondaLpfTauLowSpeed", b"0.07")
    # a current name already set wins over its old one
    self.params.put("HondaMinSteerSpeed", 6, block=True)
    self.write_raw("NrdrMinSteerSpeed", b"3")

    renamed = migrate_honda_eps_param_names(self.params)

    self.assertEqual(self.params.get("HondaEpsAngleRateLimit"), 219)
    self.assertEqual(self.params.get("HondaMinSteerSpeed"), 6)
    self.assertNotIn("NrdrMinSteerSpeed->HondaMinSteerSpeed", renamed)
    for old_key in HONDA_EPS_KEY_RENAMES:
      self.assertFalse(Path(self.params.get_param_path(old_key)).exists(), old_key)
    # retired settings: their files go, under vfn's old names and their later names alike
    for key in ("NrdrLatUseFirmwareVgr", "HondaLpfTauLowSpeed"):
      self.assertFalse(Path(self.params.get_param_path(key)).exists(), key)
    self.assertEqual(migrate_honda_eps_param_names(self.params), [])   # idempotent

  def test_retired_settings_are_deleted(self):
    from openpilot.starpilot.honda_eps_settings import RETIRED_HONDA_EPS_KEYS
    for key in ("HondaSteerDeltaLimiter", "LatPScaleHighway", "HondaTorqueOutputLowPassFilter", "HondaEpsFirmwareVgr"):
      self.assertIn(key, RETIRED_HONDA_EPS_KEYS)
      self.write_raw(key, b"1")
    migrate_honda_eps_param_names(self.params)
    for key in RETIRED_HONDA_EPS_KEYS:
      self.assertFalse(Path(self.params.get_param_path(key)).exists(), key)

  def test_honda_eps_tuning_survives_7_0s_first_start(self):
    self.write_raw("NrdrLatAngleRateLimit", b"219")
    self.params.put("HondaOverrideTorqueScale", 25, block=True)
    self.params.put_bool("AlwaysOnLateral", True, block=True)   # a StarPilot preference: 7.0 starts it fresh

    migrate_honda_eps_param_names(self.params)
    prepare_manager_start(self.params, self.storage, auto_migrate=True)

    self.assertEqual(self.params.get("HondaEpsAngleRateLimit"), 219)
    self.assertEqual(self.params.get("HondaOverrideTorqueScale"), 25)
    self.assertFalse(self.params.get_bool("AlwaysOnLateral"))


if __name__ == "__main__":
  unittest.main()

  def test_angle_defaults_reset_clears_saved_values_once(self):
    self.params.put('HondaOverrideFadeUpSecs', 0.5, block=True)
    self.params.put('HondaOverrideFadeDownSecs', 0.3, block=True)
    self.params.put('HondaDriverOverrideThreshold', 1600, block=True)
    self.assertEqual(sorted(reset_angle_defaults_once(self.params)),
                     ['HondaDriverOverrideThreshold', 'HondaOverrideFadeDownSecs', 'HondaOverrideFadeUpSecs'])
    self.assertAlmostEqual(self.params.get('HondaOverrideFadeUpSecs', return_default=True), 1.25)
    self.assertAlmostEqual(self.params.get('HondaOverrideFadeDownSecs', return_default=True), 0.0)
    self.assertEqual(self.params.get('HondaDriverOverrideThreshold', return_default=True), 2000)
    self.params.put('HondaOverrideFadeUpSecs', 0.8, block=True)            # set after the reset: kept
    self.assertEqual(reset_angle_defaults_once(self.params), [])
    self.assertAlmostEqual(self.params.get('HondaOverrideFadeUpSecs'), 0.8)
    self.assertIn(ANGLE_DEFAULTS_RESET_KEY, HONDA_EPS_PRESERVED_KEYS)

