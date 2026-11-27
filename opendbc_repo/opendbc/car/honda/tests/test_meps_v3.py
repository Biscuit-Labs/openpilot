"""Protocol v3 on the openpilot side (meps/protocol.py; spec rwd-xray lab/PROTOCOL_V3_20261125.md): a build in V3_BUILDS
(0x0E, 0x0F, 0x10) gets angle frames marked in byte 2 (bits 3:2 = 3, request bit 0, bit 6 DRIVE / YIELD), byte 3 0, and STANDBY
(0x0D, target 0) while not steering. v3 is the only protocol: the v2 builds 0x0B-0x0D fault "unknown_build" and get
only STANDBY frames, which they ignore (request 0)."""
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


def start_v3(build=0x0E, **kw):
  from opendbc.car.honda.tests.test_linear_angle import lin_frame
  ci, f = start([v4(build=build, steering=True, counter=k % 4) for k in range(8)], **kw)
  for k in range(4):
    ci.update([(f.t + (k + 1) * 10_000_000, [(0x6A2, lin_frame(0.0, 0.0, k), 0)])])
  assert ci.CS.linear_angle.steer_ok and ci.CS.eps_cal_status.protocol == 3
  return ci, f


def target(fr):
  return int.from_bytes(fr[0:2], "big", signed=True)


def test_codec():
  assert P.v3_byte2(True) == 0x4C and P.v3_byte2(False) == 0x0C and P.V3_STANDBY == 0x0D
  assert P.is_v3_angle(0x4C) and P.is_v3_angle(0x0C)
  assert not any(P.is_v3_angle(b) for b in (0x0D, 0x4D, 0x8C, 0xCC, 0x1C, 0x2C, 0x0E, 0x08, 0x48, 0xC8, 0x00))
  assert P.protocol_of(0x0E) == 3 and P.protocol_of(0x0F) == 3 and P.protocol_of(0x10) == 3 and all(P.protocol_of(b) is None for b in (0x0B, 0x0C, 0x0D, 0x11))
  assert P.KNOWN_BUILDS == P.V3_BUILDS == {0x0E, 0x0F, 0x10} == P.LINEAR_ANGLE_BUILDS
  assert P.YIELD_TRACKS_WHEEL_BUILDS == {0x0F, 0x10} and P.yield_tracks_wheel(0x0F) and P.yield_tracks_wheel(0x10) and not P.yield_tracks_wheel(0x0E)
  assert not P.yield_tracks_wheel(-1)
  assert not hasattr(P, "byte3_v2") and not hasattr(P, "V2_BUILDS")


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
  ci, _ = start_v3(0x0E)
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


def test_v3_0x0E_yield_past_the_limit_waits_at_the_limit_and_keeps_yielding():
  # panda's 3.6 m/s^2 angle is absolute: a press that takes the wheel past it at speed leaves the YIELD target at the
  # limit, and the release keeps yielding until the wheel is back inside (DRIVE never pulls the wheel in to the clamp)
  from opendbc.car.honda import clarity_angle_mode as cam
  ci, _ = start_v3(0x0E)
  lim = cam.std_angle_limit(20.0, True)
  for _ in range(100):
    T.e4(ci, True, 5.0, 0.0, v=20.0)
  wheel, frames = 0.0, []
  for _ in range(200):
    wheel = min(wheel + 1.0, lim + 30.0)
    frames.append(T.e4(ci, True, 5.0, wheel, v=20.0, pressed=True)[1])
  assert all(f[2] == 0x0C for f in frames)
  assert all(abs(target(f)) <= 10 * lim + 1 for f in frames) and abs(target(frames[-1])) >= 10 * lim - 1
  rel = [T.e4(ci, True, 5.0, lim + 30.0, v=20.0)[1] for _ in range(50)]   # released, wheel still past the limit
  assert all(f[2] == 0x0C for f in rel)
  back = [T.e4(ci, True, 5.0, lim - 5.0, v=20.0)[1] for _ in range(5)]     # wheel back inside: DRIVE
  assert back[-1][2] == 0x4C


def test_v3_0x0F_press_yields_with_the_target_at_the_wheel_every_frame():
  # builds >= 0x0F (the EPS skips the jump check on YIELD and pins its reference to the wheel): YIELD target = wheel
  ci, _ = start_v3(0x0F)
  for _ in range(200):
    T.e4(ci, True, 5.0, 0.0, v=20.0)
  press = [T.e4(ci, True, 5.0, w, v=20.0, pressed=True)[1] for w in [-0.2 * k for k in range(1, 101)]]   # fast: 20 deg/s
  assert all(f[2] == 0x0C and f[3] == 0 for f in press)
  assert [target(f) for f in press] == [2 * k for k in range(1, 101)]    # raw = -10 x deg: exactly the wheel, no step limit
  rel = [T.e4(ci, True, 5.0, -20.0, v=20.0)[1] for _ in range(300)]
  assert all(f[2] == 0x4C for f in rel)                                  # DRIVE again at once
  tr = [target(f) for f in rel]
  assert abs(tr[0] - 200) <= 2 and tr[-1] == -50                         # from the wheel, then to the plan
  assert abs(tr[10] - 200) < abs(tr[60] - 200)


def _e4_rate(ci, lat, angle_des, measured, rate, v, pressed=False, t=[5_000_000_000]):
  from opendbc.car import structs
  ci.CS.out = structs.CarState(vEgo=float(v), steeringAngleDeg=float(measured), steeringRateDeg=float(rate),
                               steeringPressed=bool(pressed)).as_reader()
  cc = structs.CarControl(latActive=lat)
  cc.actuators.steeringAngleDeg = float(angle_des)
  t[0] += 10_000_000
  _, frames = ci.apply(cc.as_reader(), t[0])
  return next(bytes(x[1]) for x in frames if x[0] == 0xE4)


def test_v3_0x0F_release_starts_at_rest_and_does_not_coast_past_the_plan():
  # route 00000129: the driver let go while unwinding at 100-200 deg/s; carrying that rate into the release trajectory
  # coasted the target 15-64 deg past the plan. The release now starts at rest: the target never runs on past the release
  # point away from the plan, and settles on it
  ci, _ = start_v3(0x0F)
  for _ in range(100):
    _e4_rate(ci, True, 0.0, 0.0, 0.0, 8.0)
  wheel = 0.0
  for _ in range(40):                                                    # unwind to +60 deg at 150 deg/s while pressed
    wheel += 1.5
    _e4_rate(ci, True, 0.0, wheel, 150.0, 8.0, pressed=True)
  rel = []
  for _ in range(250):                                                   # released (still turning); the wheel follows
    f = _e4_rate(ci, True, 0.0, wheel, 150.0 if not rel else 0.0, 8.0)
    rel.append(target(f) / -10.0)
    wheel += 0.3 * (rel[-1] - wheel)
  assert max(rel) <= 60.0 + 0.2, max(rel)                                # no coast past the release point
  assert abs(rel[-1]) < 1.0                                              # and back on the plan (0 deg)


def test_v3_0x0F_yield_past_the_limit_is_standby_until_the_wheel_is_back_inside():
  from opendbc.car.honda import clarity_angle_mode as cam
  ci, _ = start_v3(0x0F)
  lim = cam.std_angle_limit(20.0, True)
  for _ in range(100):
    T.e4(ci, True, 5.0, 0.0, v=20.0)
  inside = [T.e4(ci, True, 5.0, w, v=20.0, pressed=True)[1] for w in (lim - 6.0, lim - 4.0)]
  assert all(f[2] == 0x0C and abs(target(f)) == round(10 * (lim - d)) for f, d in zip(inside, (6.0, 4.0), strict=True))
  over = [T.e4(ci, True, 5.0, lim + 20.0, v=20.0, pressed=True)[1] for _ in range(20)]   # pressed, wheel past the limit
  assert all(f[2] == P.V3_STANDBY and f[0:2] == bytes(2) and f[3] == 0 for f in over)
  rel = [T.e4(ci, True, 5.0, lim + 20.0, v=20.0)[1] for _ in range(50)]  # released, still past: STANDBY, no held YIELD
  assert all(f[2] == P.V3_STANDBY and f[0:2] == bytes(2) for f in rel)
  back = [T.e4(ci, True, 5.0, lim - 5.0, v=20.0)[1] for _ in range(300)]  # back inside: engage from the wheel
  assert all(f[2] == 0x4C for f in back[2:]) and abs(target(back[2]) + round(10 * (lim - 5.0))) <= 40   # from the wheel (raw = -10 deg)
  assert target(back[-1]) == -50


@pytest.mark.parametrize("build", [0x0E, 0x0F, 0x10])
def test_v3_release_goes_drive_at_once_on_a_fast_wheel(build):
  # no release hold or Start backstop in openpilot: build 0x10 removes the handback brake in the EPS (rwd-xray
  # clarity/CLARITY_HANDBACK_DAMPING_DESIGNS_20261127, design C); the press detector keeps one fixed Start level
  ci, _ = start_v3(build)
  for _ in range(100):
    _e4_rate(ci, True, 0.0, 0.0, 0.0, 8.0)
  for _ in range(20):
    _e4_rate(ci, True, 0.0, 40.0, 200.0, 8.0, pressed=True)
  frames = [_e4_rate(ci, True, 0.0, 40.0, 200.0, 8.0) for _ in range(10)]
  assert all(f[2] == 0x4C for f in frames)
  assert not hasattr(ci.CS, "press_start_scale") and not hasattr(ci.CC, "release_hold")


def test_v3_frames_never_carry_the_request_or_byte3():
  ci, _ = start_v3()
  frames = [T.e4(ci, False, 0.0, 0.0)[1]] + [T.e4(ci, True, 5.0, 0.0)[1] for _ in range(50)] + \
           [T.e4(ci, True, 5.0, -3.0, pressed=True)[1] for _ in range(20)]
  for f in frames:
    assert not f[2] & 0x80 and f[3] == 0 and f[2] & 0x0C == 0x0C
    assert P.is_v3_angle(f[2]) or (f[2] == P.V3_STANDBY and f[0:2] == bytes(2))


@pytest.mark.parametrize("build", (0x0B, 0x0C, 0x0D))
def test_v2_builds_get_only_standby(build):
  ci, _ = start([v4(build=build, steering=True, counter=k % 4) for k in range(8)])
  assert ci.CS.eps_cal_status.fault == "unknown_build" and ci.CS.eps_cal_status.protocol is None
  for lat in (False, True, True):
    _, fr = T.e4(ci, lat, 5.0, 0.0)
    assert fr[0:2] == bytes(2) and fr[2] == P.V3_STANDBY and fr[3] == 0


@pytest.mark.parametrize("dbc", ("acura_rdx_2020_can_generated", "honda_civic_hatchback_ex_2017_can_generated",
                                 "honda_clarity_hybrid_2018_can_generated"))
def test_v3_packer_byte2_on_bosch_and_nidec(dbc):
  from opendbc.can import CANPacker
  from opendbc.car.honda import hondacan
  can = type("C", (), {"lkas": 0})()
  pk = CANPacker(dbc)
  for b2, tg in ((0x4C, -1234), (0x0C, 4321), (0x0D, 0)):
    _, dat, _ = hondacan.create_steering_control(pk, can, tg, True, False, v3_byte2=b2)
    assert dat[2] == b2 and dat[3] == 0 and int.from_bytes(dat[0:2], "big", signed=True) == tg


def test_graded_authority_softens_between_soft_and_start():
  from opendbc.car.honda.clarity_angle_mode import GRADED_SOFT_FRACTION, GradedAuthority
  g = GradedAuthority()
  assert g.update(False, 1500.0, 1560.0) == 1.0                         # off: full
  for _ in range(200):
    w = g.update(True, 1000.0, 1560.0)                                  # below 0.8 x Start: full
  assert w == 1.0
  mid = (GRADED_SOFT_FRACTION + 1.0) / 2 * 1560.0
  ws = [g.update(True, mid, 1560.0) for _ in range(200)]
  assert ws[0] == 1.0 - 0.014 and abs(ws[-1] - 0.5) < 1e-6               # falls at most 0.014 per frame to the halfway w
  up = [g.update(True, 0.0, 1560.0) for _ in range(100)]
  assert abs(up[0] - 0.508) < 1e-6 and up[-1] == 1.0                     # recovers at 0.008 per frame


def test_graded_override_off_by_default_changes_nothing():
  # the setting off (default): frames are identical to the ungraded sender, whatever the driver's torque
  ci_a, _ = start_v3()
  ci_b, _ = start_v3(graded_override=False)
  for k in range(150):
    fa = T.e4(ci_a, True, 5.0, 0.0, v=20.0)[1]
    fb = T.e4(ci_b, True, 5.0, 0.0, v=20.0)[1]
    assert fa == fb, k
