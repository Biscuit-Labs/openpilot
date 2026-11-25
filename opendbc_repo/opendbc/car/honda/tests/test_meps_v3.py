"""Protocol v3 on the openpilot side (meps/protocol.py; spec rwd-xray lab/PROTOCOL_V3_20261125.md): a build in V3_BUILDS
(0x0E) gets angle frames marked in byte 2 (bits 3:2 = 3, request bit 0, bit 6 DRIVE / YIELD), byte 3 0, and STANDBY
(0x0D, target 0) while not steering. Builds 0x0B-0x0D keep the v2 frames."""
import pytest

from opendbc.car.honda.meps import protocol as P
from opendbc.car.honda.tests import test_clarity_angle_mode as T
from opendbc.car.honda.tests.test_eps_cal_status import v4
from opendbc.car.honda.tests.test_meps_v2 import angle_on, start  # noqa: F401  (fixture)

assert angle_on


def start_v3(**kw):
  from opendbc.car.honda.tests.test_linear_angle import lin_frame
  ci, f = start([v4(build=0x0E, steering=True, counter=k % 4) for k in range(8)], **kw)
  for k in range(4):
    ci.update([(f.t + (k + 1) * 10_000_000, [(0x6A2, lin_frame(0.0, 0.0, k), 0)])])
  assert ci.CS.linear_angle.latched and ci.CS.eps_cal_status.protocol == 3
  return ci, f


def target(fr):
  return int.from_bytes(fr[0:2], "big", signed=True)


def test_codec():
  assert P.v3_byte2(True) == 0x4C and P.v3_byte2(False) == 0x0C and P.V3_STANDBY == 0x0D
  assert P.is_v3_angle(0x4C) and P.is_v3_angle(0x0C)
  assert not any(P.is_v3_angle(b) for b in (0x0D, 0x4D, 0x8C, 0xCC, 0x1C, 0x2C, 0x0E, 0x08, 0x48, 0xC8, 0x00))
  assert P.protocol_of(0x0E) == 3 and P.protocol_of(0x0D) == 2 and P.protocol_of(0x0F) is None
  assert 0x0E in P.LINEAR_ANGLE_BUILDS and 0x0E in P.KNOWN_BUILDS


def test_v3_idle_is_standby():
  ci, _ = start_v3()
  _, idle = T.e4(ci, False, 0.0, 0.0, v=20.0)
  assert idle[0:2] == bytes(2) and idle[2] == P.V3_STANDBY and idle[3] == 0


def test_v3_engage_drive_frames():
  ci, _ = start_v3()
  eng = [T.e4(ci, True, 5.0, 0.0, v=20.0)[1] for _ in range(200)]
  assert all(f[2] == 0x4C and f[3] == 0 for f in eng)                    # DRIVE marker, request 0, byte 3 0, every frame
  tg = [target(f) for f in eng]
  assert abs(tg[0]) <= 2 and tg[-1] == -50                             # from the wheel to the plan (raw = -10 x deg)


def test_v3_press_yields_and_follows_the_wheel_then_resumes_with_the_fade():
  ci, _ = start_v3()
  for _ in range(200):
    T.e4(ci, True, 5.0, 0.0, v=20.0)
  press = [T.e4(ci, True, 5.0, -8.0, v=20.0, pressed=True)[1] for _ in range(80)]
  assert all(f[2] == 0x0C and f[3] == 0 for f in press)                  # YIELD marker
  assert target(press[-1]) == 80                                         # the sent target reached the wheel (-8 deg)
  steps = [abs(target(b) - target(a)) for a, b in zip(press, press[1:], strict=False)]
  assert max(steps) <= 20                                                # step-limited (EPS jump limit / panda step at 20 m/s)
  rel = [T.e4(ci, True, 5.0, -8.0, v=20.0)[1] for _ in range(300)]
  assert all(f[2] == 0x4C for f in rel)                                  # DRIVE again at once
  tr = [target(f) for f in rel]
  assert abs(tr[0] - 80) <= 2                                            # resumes from the wheel, no jump
  assert tr[-1] == -50                                                   # and walks to the plan (effort fade)
  assert abs(tr[10] - 80) < abs(tr[60] - 80)                             # gently first


def test_v3_hold_off_drops_to_standby_during_a_press():
  ci, _ = start_v3(angle_hold_override=False)
  for _ in range(100):
    T.e4(ci, True, 5.0, 0.0, v=20.0)
  fr = [T.e4(ci, True, 5.0, -8.0, v=20.0, pressed=True)[1] for _ in range(80)][-1]
  assert fr[2] == P.V3_STANDBY and fr[0:2] == bytes(2)


def test_v3_frames_never_carry_the_request_or_byte3():
  ci, _ = start_v3()
  frames = [T.e4(ci, False, 0.0, 0.0)[1]] + [T.e4(ci, True, 5.0, 0.0)[1] for _ in range(50)] + \
           [T.e4(ci, True, 5.0, -3.0, pressed=True)[1] for _ in range(20)]
  for f in frames:
    assert not f[2] & 0x80 and f[3] == 0 and f[2] & 0x0C == 0x0C
    assert P.is_v3_angle(f[2]) or (f[2] == P.V3_STANDBY and f[0:2] == bytes(2))


@pytest.mark.parametrize("build", (0x0B, 0x0C, 0x0D))
def test_v2_builds_keep_v2_frames(build):
  ci, _ = start([v4(build=build, steering=True, counter=k % 4) for k in range(8)])
  assert ci.CS.eps_cal_status.protocol == 2
  _, idle = T.e4(ci, False, 0.0, 0.0)
  assert idle[3] == 0xF1 and idle[2] == 0


@pytest.mark.parametrize("dbc", ("honda_clarity_hybrid_2018_can_generated",))   # angle mode is Clarity-only on this branch
def test_v3_packer_byte2_on_bosch_and_nidec(dbc):
  from opendbc.can import CANPacker
  from opendbc.car.honda import hondacan
  can = type("C", (), {"lkas": 0})()
  pk = CANPacker(dbc)
  for b2, tg in ((0x4C, -1234), (0x0C, 4321), (0x0D, 0)):
    _, dat, _ = hondacan.create_steering_control(pk, can, tg, True, False, eps_mode=0xF1, angle_payload=0x20, arm_bits=0x48,
                                                 v3_byte2=b2)
    assert dat[2] == b2 and dat[3] == 0 and int.from_bytes(dat[0:2], "big", signed=True) == tg
