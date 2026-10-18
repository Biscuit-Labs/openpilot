import tempfile
import unittest
from pathlib import Path

from openpilot.common.params import Params
from openpilot.starpilot.honda_eps_settings import HONDA_EPS_KEY_RENAMES, HONDA_EPS_PRESERVED_KEYS, migrate_honda_eps_param_names
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
    self.assertTrue(self.params.get_bool("HondaEpsFirmwareVgr"))
    self.assertAlmostEqual(self.params.get("HondaTorqueOutputLpfTauLowSpeed"), 0.07)
    self.assertEqual(self.params.get("HondaMinSteerSpeed"), 6)
    self.assertNotIn("NrdrMinSteerSpeed->HondaMinSteerSpeed", renamed)
    for old_key in HONDA_EPS_KEY_RENAMES:
      self.assertFalse(Path(self.params.get_param_path(old_key)).exists(), old_key)
    self.assertEqual(migrate_honda_eps_param_names(self.params), [])   # idempotent

  def test_honda_eps_tuning_survives_7_0s_first_start(self):
    self.write_raw("NrdrLatAngleRateLimit", b"219")
    self.params.put("HondaTorqueOutputLpfTauLowSpeed", 0.07, block=True)
    self.params.put("LatPScaleHighway", 125, block=True)
    self.params.put_bool("AlwaysOnLateral", True, block=True)   # a StarPilot preference: 7.0 starts it fresh

    migrate_honda_eps_param_names(self.params)
    prepare_manager_start(self.params, self.storage, auto_migrate=True)

    self.assertEqual(self.params.get("HondaEpsAngleRateLimit"), 219)
    self.assertAlmostEqual(self.params.get("HondaTorqueOutputLpfTauLowSpeed"), 0.07)
    self.assertEqual(self.params.get("LatPScaleHighway"), 125)
    self.assertFalse(self.params.get_bool("AlwaysOnLateral"))


if __name__ == "__main__":
  unittest.main()
