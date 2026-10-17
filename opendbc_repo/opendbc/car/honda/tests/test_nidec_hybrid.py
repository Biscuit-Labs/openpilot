"""NRDR: Nidec hybrids (Clarity) brake on COMPUTER_BRAKE_HYBRID and may report brake hold on BRAKE_HOLD_HYBRID_ALT."""
import pytest

from opendbc.can import CANPacker
from opendbc.car import Bus, gen_empty_fingerprint
from opendbc.car.honda import hondacan
from opendbc.car.honda.hondacan import CanBus
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.values import CAR, DBC, HondaFlags


def _brake_fields(dat):
  standard = (dat[0] << 2) | (dat[1] >> 6)
  hybrid = (dat[6] << 2) | (dat[7] >> 6)
  return standard, hybrid


@pytest.mark.parametrize("hybrid", [False, True])
def test_brake_command_uses_the_hybrid_field_on_a_hybrid(hybrid):
  CP = CarInterface.get_non_essential_params(CAR.HONDA_CLARITY)
  packer = CANPacker(DBC[CAR.HONDA_CLARITY][Bus.pt])
  stock_brake = {"CHIME": 0}
  _, dat, _ = hondacan.create_brake_command(packer, CanBus(CP), 200, True, True, False, False, stock_brake, hybrid=hybrid)
  assert _brake_fields(dat) == ((0, 200) if hybrid else (200, 0))


def _clarity_params(extra_addrs):
  fingerprint = gen_empty_fingerprint()
  initial = CarInterface.get_params(CAR.HONDA_CLARITY, fingerprint, [], False, False, False)
  for addr in (0x184, *extra_addrs):   # 0x184 marks a hybrid
    fingerprint[CanBus(initial).pt][addr] = 8
  return CarInterface.get_params(CAR.HONDA_CLARITY, fingerprint, [], False, False, False)


def test_alt_brake_hold_message_sets_its_flag():
  assert _clarity_params([0x223]).flags & HondaFlags.HYBRID_ALT_BRAKEHOLD
  assert not _clarity_params([]).flags & HondaFlags.HYBRID_ALT_BRAKEHOLD
