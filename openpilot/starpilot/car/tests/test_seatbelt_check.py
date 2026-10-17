import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from openpilot.common.params import Params
from openpilot.starpilot.car.seatbelt_check import REFRESH_NS, SeatbeltCheck
from openpilot.starpilot.honda_eps_settings import HONDA_EPS_PRESERVED_KEYS


class TestSeatbeltCheck(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.params = Params(str(Path(self.temporary.name) / 'params'))

  def test_the_check_stays_on_by_default(self):
    CS = SimpleNamespace(seatbeltUnlatched=True)
    SeatbeltCheck(self.params).apply(CS)
    self.assertTrue(CS.seatbeltUnlatched)

  def test_disabling_clears_unlatched_after_the_next_refresh(self):
    now = [0]
    check = SeatbeltCheck(self.params, clock=lambda: now[0])
    self.params.put_bool("DisableSeatbeltCheck", True, block=True)
    CS = SimpleNamespace(seatbeltUnlatched=True)
    now[0] = REFRESH_NS - 1
    check.apply(CS)
    self.assertTrue(CS.seatbeltUnlatched)
    now[0] = REFRESH_NS
    check.apply(CS)
    self.assertFalse(CS.seatbeltUnlatched)

  def test_the_choice_survives_the_first_start(self):
    self.assertIn("DisableSeatbeltCheck", HONDA_EPS_PRESERVED_KEYS)


if __name__ == "__main__":
  unittest.main()
