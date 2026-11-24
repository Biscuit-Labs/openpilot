"""Linear-angle EPS (build 0x0C on, meps/linear_angle.py): 0x6A2 EPS_LINEAR_ANGLE latches linear mode (as panda does),
carState.steeringAngleDeg becomes the rack-linear angle, the sender's limits switch to linear units, a stale 0x6A2 is a
temporary fault, and a 0x0C that never sends 0x6A2 never steers. 0x0B and torque mode are unchanged."""
import pytest

from opendbc.car.honda.meps.linear_angle import STALE_FRAMES
from opendbc.car.honda.tests import test_clarity_angle_mode as T
from opendbc.car.honda.tests.test_eps_cal_status import honda_checksum, v4

LIN = 0x6A2


def lin_frame(lin_deg, pub_deg, counter):
  b = bytearray(8)
  b[0:2] = (int(round(-10 * lin_deg)) & 0xFFFF).to_bytes(2, "big")   # 0.1 deg, STEER_ANGLE sign (raw = -10 x deg)
  b[2:4] = (int(round(-10 * pub_deg)) & 0xFFFF).to_bytes(2, "big")
  b[7] = (counter & 3) << 4
  b[7] |= honda_checksum(bytes(b), LIN)
  return bytes(b)


@pytest.fixture
def angle_on():
  T.ANGLE[0] = True
  yield
  T.ANGLE[0] = False


def drive(ci, n, build=0x0C, lin=None, start=0, t0=1_000_000_000):
  """n carState updates at 100 Hz: 0x6A4 (build) every other one, 0x6A2 every one when lin is not None."""
  cs = None
  for k in range(start, start + n):
    frames = []
    if k % 2 == 0:
      frames.append((0x6A4, v4(build=build, counter=(k // 2) % 4), 0))
    if lin is not None:
      frames.append((LIN, lin_frame(lin, lin * 0.93, k % 4), 0))
    cs = ci.update([(t0 + k * 10_000_000, frames)])
  return cs


def test_0x0C_steers_in_the_linear_angle(angle_on):
  ci = T.clarity()
  cs = drive(ci, 20, lin=120.0)
  assert ci.CS.linear_angle.latched and not cs.steerFaultTemporary
  assert cs.steeringAngleDeg == pytest.approx(120.0, abs=0.05)          # the rack-linear angle, not 0x14A
  assert ci.CS.linear_angle.published_deg == pytest.approx(111.6, abs=0.05)


def test_0x0B_is_unchanged(angle_on):
  ci = T.clarity()
  cs = drive(ci, 20, build=0x0B, lin=None)
  assert not ci.CS.linear_angle.latched and not cs.steerFaultTemporary
  assert cs.steeringAngleDeg == ci.CS.published_angle_deg                 # the 0x14A angle, as before


def test_0x0C_without_0x6A2_never_steers(angle_on):
  ci = T.clarity()
  cs = drive(ci, 20, build=0x0C, lin=None)
  assert cs.steerFaultTemporary and not ci.CS.linear_angle.latched


def test_stale_linear_angle_is_a_fault_not_a_switch(angle_on):
  ci = T.clarity()
  drive(ci, 20, lin=50.0)
  cs = drive(ci, STALE_FRAMES, lin=None, start=20)
  assert not cs.steerFaultTemporary and ci.CS.linear_angle.latched       # 50 ms: still fresh enough
  cs = drive(ci, 2, lin=None, start=20 + STALE_FRAMES)
  assert cs.steerFaultTemporary and ci.CS.linear_angle.latched           # stale: fault, still linear (no switch back)
  assert cs.steeringAngleDeg == pytest.approx(50.0, abs=0.05)


def test_torque_mode_ignores_0x6A2():
  ci = T.clarity()                                                        # angle mode off
  cs = drive(ci, 20, lin=80.0)
  assert not ci.CS.linear_angle.enabled and not ci.CS.linear_angle.latched
  assert cs.steeringAngleDeg != pytest.approx(80.0, abs=1.0)


def test_sender_uses_linear_limits_when_latched(angle_on):
  from opendbc.car.honda import clarity_angle_mode as cam
  ci = T.clarity()
  drive(ci, 20, lin=0.0)
  T.e4(ci, True, 0.0, 0.0)
  assert ci.CC.angle_sender.linear
  # at 6 m/s the linear limit (rack units) is wider than the published one, as panda's linear rule
  assert cam.std_angle_limit(6.0, True) > cam.std_angle_limit(6.0)
