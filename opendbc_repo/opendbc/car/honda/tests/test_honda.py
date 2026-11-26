import unittest

from opendbc.car import gen_empty_fingerprint
from opendbc.car.honda.hondacan import CanBus
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.values import CAR, HondaFlags


class TestHondaFingerprint(unittest.TestCase):
  def test_tja_bosch_only(self):
    for car_model in CAR:
      if car_model.config.flags & HondaFlags.BOSCH_TJA_CONTROL:
        assert car_model.config.flags & HondaFlags.BOSCH, "Nidec car found with TJA control"

  def test_bsm_fingerprint_sets_enable_bsm(self):
    # The interface builds CanBus after the platform config flags are on ret, so its radar bus is the Bosch one.
    probe = CarInterface.get_params(CAR.HONDA_CRV_5G, gen_empty_fingerprint(), [], False, False, False)
    fingerprint = gen_empty_fingerprint()
    fingerprint[CanBus(probe, fingerprint).radar][0x12f8bfa7] = 8
    cp = CarInterface.get_params(CAR.HONDA_CRV_5G, fingerprint, [], False, False, False)
    assert cp.flags & HondaFlags.HAS_BSM
    assert cp.deprecated.enableBsm
    plain = CarInterface.get_params(CAR.HONDA_CRV_5G, gen_empty_fingerprint(), [], False, False, False)
    assert not plain.flags & HondaFlags.HAS_BSM
    assert not plain.deprecated.enableBsm
