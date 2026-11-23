"""Protocol v2 on the openpilot side (meps/protocol.py; spec rwd-xray lab/audit_fable_20261121/v2/PROTOCOL_V2.md): the EPS
reports 0x6A4 layout 4 (build 0x0B), openpilot sends 0xE4 byte 3 = MODE 1 | AUTH (15 = full), keeps the payload rule,
and runs the interlock on the STEERING bit with the EPS's REASON. v2 is the only protocol (v1 removed)."""
import dataclasses

import pytest

from opendbc.car.honda.meps import protocol as P
from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
from opendbc.car.honda.tests import test_clarity_angle_mode as T
from opendbc.car.honda.tests.test_eps_cal_status import Feed, v4


@pytest.fixture(autouse=True)
def angle_on():
  T.ANGLE[0] = True
  yield
  T.ANGLE[0] = False


def start(status=None, **settings):
  ci = T.clarity()
  if settings:
    ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, **settings)})()
  f = Feed(ci)
  f.run(status or [v4(counter=k % 4) for k in range(8)])
  return ci, f


def test_byte3_codec():
  assert not hasattr(P, "byte3_v1")
  assert P.byte3_v2(0) == 0xF1 and P.byte3_v2(15) == 0x01            # AUTH = 15 - CUT: CUT 0 (full) -> AUTH 15
  for cut in range(16):
    b3 = P.byte3_v2(cut)
    assert b3 & 0x3 == 1 and (b3 >> 2) & 0x3 == 0 and b3 >> 4 == 15 - cut


def test_layout4_is_detected_and_decoded():
  ci, _ = start([v4(steering=True, clamp=True, lkas=2, reason=7, counter=k % 4) for k in range(8)])
  s = ci.CS.eps_cal_status
  assert s.build_id == 0x0B and s.active_mode == 1 and s.clamp and s.reason == "AUTHORITY_ZERO"
  assert s.fault == "" and s.angle_ready and s.authority_ready


def test_v2_frames_engage_override_and_idle():
  ci, _ = start()
  _, idle = T.e4(ci, False, 0.0, 0.0, v=20.0)
  assert idle[0:3] == bytes(3) and idle[3] == 0xF1                       # idle: MODE 1 requested, AUTH 15, no payload
  eng = [T.e4(ci, True, 5.0, 0.0, v=20.0)[1] for _ in range(150)]
  assert all(f[2] == 0xA0 | 0x48 for f in eng)                           # request + payload + stock arm 2 (angle hold)
  assert all(f[3] & 0x0F == 0x01 for f in eng)                           # MODE 1, reserved 0, no control bit
  assert eng[0][3] >> 4 == 0 and eng[-1][3] >> 4 == 15                   # authority ramps up from 0 to full
  auths = [f[3] >> 4 for f in eng]
  assert all(b >= a for a, b in zip(auths, auths[1:], strict=False))
  press = [T.e4(ci, True, 5.0, -8.0, v=20.0, pressed=True)[1] for _ in range(60)]
  assert all(f[2] == 0xA0 | 0x44 for f in press) and press[-1][3] == 0x01  # override: request held + stock abort bits, AUTH 0
  plan = int.from_bytes(eng[-1][0:2], "big", signed=True)
  assert all(int.from_bytes(f[0:2], "big", signed=True) == plan for f in press)   # target stays on the plan


def test_v2_frames_are_read_as_intended_by_a_v2_receiver():
  # the spec's receiver rules: MODE 0/1 only, bits 3:2 zero, payload iff (MODE 1 and request)
  ci, _ = start()
  frames = [T.e4(ci, False, 0.0, 0.0)[1]] + [T.e4(ci, True, 5.0, 0.0)[1] for _ in range(50)]
  for f in frames:
    mode, reserved, request, payload = f[3] & 3, (f[3] >> 2) & 3, bool(f[2] & 0x80), bool(f[2] & 0x20)
    assert mode in (0, 1) and reserved == 0 and payload == (request and mode == 1)


@pytest.mark.parametrize("build", (0x0C, 0x0D))
def test_build_0c_is_accepted_like_0b(build):
  # 0x0C = 0x0B + EPS-side integrator + 100 Hz linear angle on 0x6A2; 0x0D = 0x0C + the EPS-internal lock taper. Same
  # wire protocol (0x6A4 layout 4, 0xE4 v2)
  ci, _ = start([v4(build=build, steering=True, counter=k % 4) for k in range(8)])
  s = ci.CS.eps_cal_status
  assert s.build_id == build and s.fault == "" and s.angle_ready
  _, f = T.e4(ci, True, 5.0, 0.0)
  assert f[2] & 0x80 and f[3] & 0x0F == 0x01


def test_unknown_v2_build_never_steers():
  ci, _ = start([v4(build=0x0E, counter=k % 4) for k in range(8)])
  assert ci.CS.eps_cal_status.fault == "unknown_build"
  _, f = T.e4(ci, True, 5.0, 0.0)
  assert f[0:3] == bytes(3)


def test_v2_eps_not_in_angle_mode_waits():
  ci, f = start([v4(mode=0, steering=False, reason=2, counter=k % 4) for k in range(8)])
  assert ci.CS.eps_cal_status.fault == "inactive_mode"
  _, e = T.e4(ci, True, 5.0, 0.0)
  assert e[0:3] == bytes(3) and e[3] == 0xF1                             # asks for MODE 1 at idle, sends no payload
  f.run([v4(counter=k % 4) for k in range(4)])
  assert ci.CS.eps_cal_status.fault == ""


def test_v2_interlock_on_the_steering_bit_with_reason():
  ci, f = start()
  T.e4(ci, False, 0.0, 0.0)
  T.e4(ci, True, 0.0, 0.0)
  f.run([v4(steering=False, reason=8, lkas=3, counter=k % 4) for k in range(8, 13)])   # 10 carState updates
  assert ci.CS.eps_cal_status.fault == ""
  f.run([v4(steering=False, reason=8, lkas=3, counter=1)])
  assert ci.CS.eps_cal_status.fault == "loop_not_running (STOCK_LKAS_NOT_ENGAGED)"
  _, e = T.e4(ci, True, 0.0, 0.0)
  assert e[0:3] == bytes(3)                                              # the request drops, which clears it
  f.run([v4(counter=k % 4) for k in range(2, 4)])
  assert ci.CS.eps_cal_status.fault == ""


def test_v2_authority_zero_does_not_trip_the_interlock():
  ci, f = start()
  T.e4(ci, False, 0.0, 0.0)
  for k in range(40):
    T.e4(ci, True, 0.0, 0.0, pressed=True)
    f.run([v4(steering=True, reason=7, gain=0, counter=k % 4)])
  assert ci.CS.eps_cal_status.fault == ""


def test_v2_fault_bit_reports_its_reason():
  ci, f = start()
  f.run([v4(steering=False, fault=True, reason=4, counter=k % 4) for k in range(2)])
  assert ci.CS.eps_cal_status.fault == "angle_fault (JUMP)" and not ci.CS.eps_cal_status.angle_ready


def test_one_profile_the_3_6_limit():
  ci, f = start()
  T.e4(ci, False, 0.0, 0.0, v=15.0)
  frames = [T.e4(ci, True, 80.0, 0.0, v=15.0)[1] for _ in range(300)]
  assert all(f[3] & 0x0F == 0x01 for f in frames)
  from opendbc.car.honda import clarity_angle_mode as cam
  peak = max(abs(int.from_bytes(f[0:2], "big", signed=True)) for f in frames) / 10
  assert peak == pytest.approx(cam.angle_limit(15.0), abs=0.06) == pytest.approx(cam.std_angle_limit(15.0), abs=0.06)


def test_layout3_after_v2_never_steers():
  ci, f = start()
  T.e4(ci, False, 0.0, 0.0)
  f.run([T.v1(3, 3, 0x0A, counter=k % 4, b0_extra=8) for k in range(4)])
  assert ci.CS.eps_cal_status.fault == "unsupported_build"
  _, e = T.e4(ci, True, 5.0, 0.0)
  assert e[0:3] == bytes(3) and e[3] == 0xF1                             # still v2 byte 3, no payload
