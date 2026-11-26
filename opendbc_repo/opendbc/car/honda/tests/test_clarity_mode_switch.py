"""0xE4 in torque mode: byte 3 always 0 and no angle marker (byte 2 bits 3:2 = 3 is protocol v3's angle frame, which a torque
frame never carries). The mode-switch builds (P1 byte-3 PTM flag, MM 0x02) are no longer supported. Angle mode's frames are
in test_clarity_angle_mode.py / test_meps_v3.py."""
import pytest

from opendbc.car import structs
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.tests.test_modified_eps import KNOWN_CASES, FLEET_CASES, eps, params
from opendbc.car.honda.values import CAR


def steering_frames(cp, ticks=60):
  ci = CarInterface(cp)
  ci.update([])
  ci.CS.out = structs.CarState(vEgo=15.0).as_reader()
  out = []
  for lat in (False, True):                       # idle frames first (the EPS latches only at LKAS idle), then engaged
    cc = structs.CarControl(latActive=lat)
    cc.actuators.torque = 0.3 if lat else 0.0
    for tick in range(ticks):
      _, frames = ci.apply(cc.as_reader(), 1_000_000_000 + (len(out) + tick) * 10_000_000)
      out += [bytes(f[1]) for f in frames if f[0] == 0xE4]
  return ci, out


def honda_checksum_ok(b, addr=0xE4):
  s = sum((x >> 4) + (x & 0xF) for x in b[:-1]) + (b[-1] >> 4) + sum((addr >> (4 * k)) & 0xF for k in range(3))
  return (b[-1] & 0xF) == ((8 - s) & 0xF)


def no_flag(f):
  return f[3] == 0 and (f[2] & 0x0C) != 0x0C and not f[2] & 0x20 and honda_checksum_ok(f)


def test_clarity_modified_eps_torque_mode_sends_no_flag():
  ci, frames = steering_frames(params(CAR.HONDA_CLARITY, [eps(b'39990-TRW,A020\x00\x00')]))
  assert ci.CC.angle_sender is None and frames
  assert all(len(f) == 5 and no_flag(f) for f in frames)


def test_clarity_stock_eps_sends_no_flag():
  ci, frames = steering_frames(params(CAR.HONDA_CLARITY, [eps(b'39990-TRW-A020\x00\x00')]))
  assert ci.CC.angle_sender is None and frames
  assert all(no_flag(f) for f in frames)


@pytest.mark.parametrize("identity,firmware", [c for c in KNOWN_CASES + FLEET_CASES if c[0] != CAR.HONDA_CLARITY])
def test_other_modified_eps_cars_send_no_flag(identity, firmware):
  ci, frames = steering_frames(params(identity, [eps(firmware)]))
  assert ci.CC.angle_sender is None and frames
  assert all(f[3] == 0 and (f[2] & 0x0C) != 0x0C and not f[2] & 0x20 for f in frames)
