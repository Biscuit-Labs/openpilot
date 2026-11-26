"""The B-CAN blind spots fail closed: a body-harness dropout reports both sides occupied, never clear."""
import unittest

from opendbc.can import CANPacker
from opendbc.car import Bus, gen_empty_fingerprint
from opendbc.car.honda.hondacan import CanBus
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.values import CAR, DBC, HondaFlags

DT_NS = 10_000_000  # 100 Hz update steps
BSM_PERIOD = 10  # one BSM frame per side every 0.1 s


class TestBcanBsmDropout(unittest.TestCase):
  def setUp(self):
    probe = CarInterface.get_params(CAR.HONDA_ACCORD, gen_empty_fingerprint(), [], False, False, False)
    fingerprint = gen_empty_fingerprint()
    fingerprint[CanBus(probe, fingerprint).radar][0x12f8bfa7] = 8
    self.CP = CarInterface.get_params(CAR.HONDA_ACCORD, fingerprint, [], False, False, False)
    self.assertTrue(self.CP.flags & HondaFlags.HAS_BSM)
    self.CI = CarInterface(self.CP)
    self.packer = CANPacker(DBC[self.CP.carFingerprint][Bus.body])
    self.bus = CanBus(self.CP).radar
    self.t = 0

  def _run(self, seconds, bsm, left_alert=0, right_alert=0):
    cs = None
    for i in range(int(seconds * 1e9 / DT_NS)):
      self.t += DT_NS
      frames = []
      if bsm and i % BSM_PERIOD == 0:
        for name, alert in (("BSM_STATUS_LEFT", left_alert), ("BSM_STATUS_RIGHT", right_alert)):
          frames.append(self.packer.make_can_msg(name, self.bus, {"BSM_ALERT": alert}))
      cs = self.CI.update([(self.t, frames)])
    return cs

  def test_clear_while_valid_then_occupied_on_dropout(self):
    cs = self._run(3.0, bsm=True)
    self.assertTrue(self.CI.CS.body_valid)
    self.assertEqual((cs.leftBlindspot, cs.rightBlindspot), (False, False))

    cs = self._run(3.0, bsm=False)
    self.assertFalse(self.CI.CS.body_valid)
    self.assertEqual((cs.leftBlindspot, cs.rightBlindspot), (True, True))

  def test_real_alerts_pass_through_while_valid(self):
    cs = self._run(3.0, bsm=True, left_alert=1, right_alert=0)
    self.assertTrue(self.CI.CS.body_valid)
    self.assertEqual((cs.leftBlindspot, cs.rightBlindspot), (True, False))

  def test_recovers_when_the_harness_comes_back(self):
    self._run(3.0, bsm=True)
    self._run(3.0, bsm=False)
    cs = self._run(3.0, bsm=True)
    self.assertTrue(self.CI.CS.body_valid)
    self.assertEqual((cs.leftBlindspot, cs.rightBlindspot), (False, False))


class TestNoHarnessUnaffected(unittest.TestCase):
  def test_cars_without_the_harness_never_report_blind_spots(self):
    # no 0x12f8bfa7 at fingerprinting -> no HAS_BSM -> the body parser and the fail-closed branch never run
    for car in (CAR.HONDA_ACCORD, CAR.HONDA_CRV_5G, CAR.HONDA_CIVIC_BOSCH):
      with self.subTest(car=car):
        CP = CarInterface.get_params(car, gen_empty_fingerprint(), [], False, False, False)
        self.assertFalse(CP.flags & HondaFlags.HAS_BSM)
        CI = CarInterface(CP)
        cs = None
        for i in range(300):  # 3 s with no body messages at all
          cs = CI.update([((i + 1) * DT_NS, [])])
        self.assertEqual((cs.leftBlindspot, cs.rightBlindspot), (False, False))


if __name__ == "__main__":
  unittest.main()
