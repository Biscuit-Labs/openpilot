"""Clarity angle mode (clarity_angle_mode.py, eps_cal_status.py angle checks), protocol v3 only, with 0x6A4 layout-4 frames
an emulated EPS transmitted (clarity_v3_status_frames.json: the 0x0B emulator's frames from rwd-xray
CLARITY_ANGLE_MODE_0x0B_20261121/proof0B, relabelled build 0x0E (byte 1 + checksum) on 2026-11-26; the layout-4 format is
unchanged in v3). The v3 wire format itself is in test_meps_v3.py."""
import json
import os
import struct

import numpy as np
import pytest

from opendbc.can import CANParser
from opendbc.car import structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda.meps import protocol as meps_protocol
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.tests.test_clarity_mode_switch import honda_checksum_ok
from opendbc.car.honda.tests.test_eps_cal_status import Feed, v1, v4
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.values import CAR, HondaFlags

ADDR = 0x6A4
FRAMES = json.load(open(os.path.join(os.path.dirname(__file__), "clarity_v3_status_frames.json")))
MODIFIED = b'39990-TRW,A020\x00\x00'


def datas(name):
  return [bytes.fromhex(h) for _, h in FRAMES[name]["frames"]]


def run_status(ci, f, d, k):
  """One 0x6A4 status frame plus the two 0x6A2 linear-angle frames the EPS sends meanwhile (0x0E is a linear-angle build)."""
  from opendbc.car.honda.tests.test_linear_angle import lin_frame
  f.t += 10_000_000
  s = ci.update([(f.t, [(ADDR, d, 0), (0x6A2, lin_frame(0.0, 0.0, 2 * k), 0)])])
  f.t += 10_000_000
  ci.update([(f.t, [(0x6A2, lin_frame(0.0, 0.0, 2 * k + 1), 0)])])
  return s


ANGLE = [False]   # the HondaClarityAngleMode setting as card's startup hook would read it


@pytest.fixture
def angle_file():
  """Angle Mode setting on (name kept from the file era)."""
  ANGLE[0] = True
  yield
  ANGLE[0] = False


def clarity(fw=MODIFIED, candidate=CAR.HONDA_CLARITY):
  # card: CarParams from the interface, then the pre-create hook applies the setting, then the interface is built
  return CarInterface(cam.apply_angle_mode(params(candidate, [eps(fw)]), ANGLE[0]))


def ready(ci, n=8):
  """Feed 0x0E MODE 1 status frames and 0x6A2 linear-angle frames until the interlock reports angle_ready and the linear
  angle is fresh (CarController sends targets only then)."""
  from opendbc.car.honda.tests.test_linear_angle import lin_frame
  f = Feed(ci)
  f.run([v4(counter=k % 4) for k in range(n)])
  for k in range(4):
    f.t += 10_000_000
    ci.update([(f.t, [(0x6A2, lin_frame(0.0, 0.0, k), 0)])])
  assert ci.CS.eps_cal_status.angle_ready, ci.CS.eps_cal_status.fault
  assert ci.CS.linear_angle.steer_ok
  return f


def standby(f):
  """STANDBY (meps/protocol.py): angle marker with bits 1:0 = 01, no request, target 0, byte 3 0."""
  return f[0:2] == bytes(2) and f[2] == meps_protocol.V3_STANDBY and f[3] == 0


DRIVE, YIELD = meps_protocol.v3_byte2(True), meps_protocol.v3_byte2(False)


def e4(ci, lat, angle_des, measured, v=10.0, pressed=False, t=[2_000_000_000]):
  ci.CS.out = structs.CarState(vEgo=float(v), steeringAngleDeg=float(measured), steeringPressed=bool(pressed)).as_reader()
  cc = structs.CarControl(latActive=lat)
  cc.actuators.steeringAngleDeg = float(angle_des)
  t[0] += 10_000_000
  act, frames = ci.apply(cc.as_reader(), t[0])
  f = [bytes(x[1]) for x in frames if x[0] == 0xE4]
  assert len(f) == 1 and honda_checksum_ok(f[0])
  return act, f[0]


# --- 0x6A4 layout 4, on the emulator's frames ---

def test_dbc_and_protocol_decode_every_emulator_frame():
  for name in FRAMES:
    cp = CANParser("honda_clarity_hybrid_2018_can_generated", [("EPS_CAL_STATUS", float("nan"))], 0)
    t = 1_000_000_000
    for d in datas(name):
      t += 20_000_000
      assert ADDR in cp.update([(t, [(ADDR, d, 0)])]), (name, d.hex())   # checksum and counter valid
      vl = cp.vl["EPS_CAL_STATUS"]
      got = meps_protocol.decode_layout4(vl)
      assert meps_protocol.is_layout4(vl) and got["build"] == 0x0E
      assert (got["fault"], got["steering"], got["clamp"], got["lkas"], got["mode"], got["reason"]) == \
             (bool(d[0] & 0x40), bool(d[0] & 0x20), bool(d[0] & 0x10), (d[0] >> 2) & 3, d[0] & 3, d[2] & 0xF), (name, d.hex())
      assert vl["ANGLE_REF"] == pytest.approx(-0.1 * struct.unpack(">h", d[3:5])[0])
      assert vl["ANGLE_OUT"] == struct.unpack(">h", d[5:7])[0]


def test_emulator_runs_show_the_expected_reasons():
  R = meps_protocol.Reason
  reasons = lambda n: {d[2] & 0xF for d in datas(n)}
  assert {R.STEERING, R.NO_REQUEST, R.MODE_SWITCH_PENDING, R.PROTOCOL, R.AUTHORITY_ZERO} <= reasons("step")
  assert R.STALE in reasons("stale200") and R.ANGLE_INVALID in reasons("invalid") and R.JUMP in reasons("step40_jump")
  assert R.STOCK_LKAS_NOT_ENGAGED in reasons("inhibit") and R.PROTOCOL in reasons("protocol")
  assert not any(d[0] & 0x20 for d in datas("bit5off"))                # a frame the loop does not take: never steers
  assert any(d[0] & 0x10 for d in datas("clamp"))                       # the EPS clamp acted
  assert {d[0] & 3 for d in datas("step")} == {0, 1}                    # boots in stock, switches to MODE 1 at idle


# --- startup selection ---

def test_angle_setting_selects_angle_mode_on_modified_clarity_only(angle_file):
  ci = clarity()
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.angle
  assert ci.CC.angle_sender is not None and ci.CS.eps_cal_status.angle
  stock = clarity(b'39990-TRW-A020\x00\x00')
  assert not stock.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and stock.CP.steerControlType == structs.CarParams.SteerControlType.torque
  assert stock.CC.angle_sender is None


def test_angle_setting_off_keeps_torque_mode():
  ci = clarity()
  assert not ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.torque
  assert ci.CC.angle_sender is None and not ci.CS.eps_cal_status.angle


# --- interlock in angle mode ---

def test_no_status_frame_faults_in_angle_mode(angle_file):
  ci = clarity(); f = Feed(ci)
  assert all(s.steerFaultTemporary for s in f.run([None] * 20))
  assert ci.CS.eps_cal_status.fault == "no_status" and not ci.CS.eps_cal_status.angle_ready


def test_emulator_run_ready_only_once_the_eps_runs_mode_1(angle_file):
  ci = clarity(); f = Feed(ci)
  ds = datas("step")
  running = []
  for i, d in enumerate(ds):
    s = run_status(ci, f, d, i)
    assert s.steerFaultTemporary == ((d[0] & 3) != 1 or bool(d[0] & 0x40)), (i, d.hex())
    running.append(ci.CS.eps_cal_status.loop_running)
  assert ci.CS.eps_cal_status.angle_ready
  assert running[-1] == bool(ds[-1][0] & 0x20)


@pytest.mark.parametrize("name,reason", [("step40_jump", "JUMP"), ("stale200", "STALE"), ("invalid", "ANGLE_INVALID")])
def test_eps_angle_fault_faults_openpilot(angle_file, name, reason):
  ci = clarity(); f = Feed(ci)
  ds = datas(name)
  seen = set()
  for i, d in enumerate(ds):
    s = run_status(ci, f, d, i)
    assert s.steerFaultTemporary == ((d[0] & 3) != 1 or bool(d[0] & 0x40)), (i, d.hex())
    seen.add(ci.CS.eps_cal_status.fault)
  assert f"angle_fault ({reason})" in seen


@pytest.mark.parametrize("build,mode", [(0x04, 3), (0x05, 4), (0x06, 3), (0x08, 3), (0x09, 3), (0x0A, 3)])
def test_v1_angle_builds_never_steer(angle_file, build, mode):
  ci = clarity(); f = Feed(ci)
  f.run([v1(mode, mode, build, counter=k % 4, b0_extra=8) for k in range(10)])     # layout 3, loop running
  assert ci.CS.eps_cal_status.fault == "unsupported_build" and not ci.CS.eps_cal_status.angle_ready
  for _ in range(10):
    _, d = e4(ci, True, 10.0, 0.0)
    assert standby(d)


# --- 0xE4 angle target ---

def test_no_payload_until_the_eps_is_ready(angle_file):
  ci = clarity()
  Feed(ci).run([v4(mode=0, steering=False, reason=2, counter=k % 4) for k in range(6)])   # EPS still in stock mode
  for _ in range(20):
    _, f = e4(ci, True, 30.0, 5.0)
    assert standby(f)                                                    # nothing an EPS could read as torque or a target


def test_idle_frames_are_standby(angle_file):
  ci = clarity(); ready(ci)
  for _ in range(10):
    _, f = e4(ci, False, 30.0, 5.0)
    assert standby(f)


def test_engage_starts_at_the_measured_angle_and_fades_in(angle_file):
  ci = clarity(); ready(ci)
  e4(ci, False, 0.0, 12.3)
  raws = []
  for _ in range(300):
    _, f = e4(ci, True, 20.0, 12.3, v=10.0)
    assert f[2] == DRIVE and f[3] == 0                                    # angle marker + DRIVE, no request, byte 3 0
    raws.append(struct.unpack(">h", f[0:2])[0])
  ang = [r / cam.RAW_PER_DEG for r in raws]
  assert ang[0] == pytest.approx(12.3, abs=0.051)                        # first target = the measured angle
  assert max(np.diff(ang[:10])) <= 0.11                                  # no jump: starts at rest, accelerates (0.1 deg raw)
  assert ang[-1] == pytest.approx(20.0, abs=0.051)


def trajectory(v, des, n, meas=0.0, rate0=0.0):
  s = cam.AngleModeSender(); s.update(False, 0.0, meas, v, True, rate0)
  return np.array([s.update(True, des(k), meas, v, True)[0] / cam.RAW_PER_DEG for k in range(n)]), s


@pytest.mark.parametrize("v", [2.0, 8.0, 15.0, 30.0])
def test_target_rate_and_acceleration_limits(v):
  a, s = trajectory(v, lambda k: 60.0 * np.sign(np.sin(k / 40.0)), 600)   # repeated big reversals (a twitchy model)
  w = []; acc = []
  ex = cam.AngleModeSender(); ex.update(False, 0.0, 0.0, v, True)
  prev_a = prev_w = 0.0
  for k in range(600):                                                   # exact (unrounded) trajectory
    ex.update(True, 60.0 * np.sign(np.sin(k / 40.0)), 0.0, v, True)
    w.append((ex.apply_angle - prev_a) / 0.01); acc.append((w[-1] - prev_w) / 0.01); prev_a, prev_w = ex.apply_angle, w[-1]
  assert max(map(abs, w)) <= float(np.interp(v, cam._VT, cam.TARGET_RATE_DEG_S)) + 1e-6
  assert max(map(abs, acc)) <= float(np.interp(v, cam._VT, cam.TARGET_ACCEL_DEG_S2)) + 1e-6


def test_engage_fade_limits_rate_and_acceleration_at_first():
  ex = cam.AngleModeSender(); ex.update(False, 0.0, 0.0, 5.0, True)
  w = []; prev = 0.0
  for k in range(int(cam.ENGAGE_S / 0.01)):
    ex.update(True, 100.0, 0.0, 5.0, True); w.append((ex.apply_angle - prev) / 0.01); prev = ex.apply_angle
  fade = lambda k: cam.ENGAGE_FLOOR + (1 - cam.ENGAGE_FLOOR) * k * 0.01 / cam.ENGAGE_S
  for k, x in enumerate(w):
    assert abs(x) <= fade(k) * float(np.interp(5.0, cam._VT, cam.TARGET_RATE_DEG_S)) + 1e-6
  assert w[0] <= cam.ENGAGE_FLOOR * float(np.interp(5.0, cam._VT, cam.TARGET_ACCEL_DEG_S2)) * 0.01 + 1e-6


def test_engage_carries_the_wheel_rate():
  for w0 in (15.0, 80.0):                                                # driver lets go with the wheel moving
    ex = cam.AngleModeSender(); ex.update(False, 0.0, 10.0, 8.0, True, w0)
    ex.update(True, 100.0, 10.0, 8.0, True)
    a_floor = cam.ENGAGE_FLOOR * float(np.interp(8.0, cam._VT, cam.TARGET_ACCEL_DEG_S2))
    assert abs(ex.apply_rate - w0) <= a_floor * 0.01 + 1e-6               # continues from the wheel's rate, no jolt


def test_no_overshoot_on_a_step():
  a, _ = trajectory(10.0, lambda k: 30.0, 600)
  assert a.max() <= 30.0 + 0.051 and a[-1] == pytest.approx(30.0, abs=0.051)


@pytest.mark.parametrize("v", [2.0, 5.0, 10.0, 15.0, 25.0, 35.0])
def test_steps_stay_inside_the_eps_jump_threshold(angle_file, v):
  ci = clarity(); ready(ci)
  e4(ci, False, 0.0, 0.0, v=v)
  prev = 0.0; worst = 0.0
  for k in range(300):
    des = 15.0 * np.sign(np.sin(k / 25.0))                               # repeated large steps
    act, f = e4(ci, True, des, 0.0, v=v)
    a = struct.unpack(">h", f[0:2])[0] / cam.RAW_PER_DEG
    worst = max(worst, abs(a - prev)); prev = a
    assert act.steeringAngleDeg == pytest.approx(a, abs=0.051)
  jt = float(np.interp(v, cam._V, cam.EPS_JUMP_DEG))
  assert worst <= 0.6 * jt + 0.1                                         # the EPS allows >= 0.8 x JT per frame


@pytest.mark.parametrize("v", [5.0, 12.0, 20.0, 30.0])
def test_target_is_clamped_inside_the_eps_lateral_accel_clamp(angle_file, v):
  ci = clarity(); ready(ci)
  e4(ci, False, 0.0, 0.0, v=v)
  for _ in range(3000):
    _, f = e4(ci, True, 600.0, 0.0, v=v)
  a = struct.unpack(">h", f[0:2])[0] / cam.RAW_PER_DEG
  assert a == pytest.approx(cam.angle_limit(v, linear=True), abs=0.06)


def test_no_engage_while_the_wheel_is_beyond_the_limit(angle_file):
  # parity rule: panda's 3.6 m/s^2 limit is absolute and the first target must be within one step of the wheel, so with
  # the wheel beyond the limit no frame could pass: the request stays down (all-zero frame) until the wheel is inside,
  # then the engage starts at the wheel (review Q-2; the Hyundai EV9 path gates its request the same way)
  ci = clarity(); ready(ci)
  e4(ci, False, 0.0, 40.0, v=30.0)
  for _ in range(50):
    _, f = e4(ci, True, 40.0, 40.0, v=30.0)                             # 30 m/s, wheel at 40 deg (linear limit 18.2)
    assert standby(f)
  _, f = e4(ci, True, 40.0, 10.0, v=30.0)                               # wheel back inside: engage at the wheel
  assert f[2] == DRIVE
  assert struct.unpack(">h", f[0:2])[0] / cam.RAW_PER_DEG == pytest.approx(10.0, abs=cam.std_angle_step(30.0, True) + 0.06)
  for _ in range(400):
    _, f = e4(ci, True, 40.0, 10.0, v=30.0)
    assert abs(struct.unpack(">h", f[0:2])[0] / cam.RAW_PER_DEG) <= cam.std_angle_limit(30.0, True) + 0.06
  assert struct.unpack(">h", f[0:2])[0] / cam.RAW_PER_DEG == pytest.approx(cam.angle_limit(30.0, True), abs=0.06)


def test_driver_press_yields_and_release_resumes_from_the_wheel(angle_file):
  # a press: YIELD (the EPS drops the loop's authority to 0 at once) with the target following the wheel; the release:
  # DRIVE at once, the target walks from the wheel to the plan
  ci = clarity(); ready(ci)
  e4(ci, False, 0.0, 0.0)
  for _ in range(100):
    _, f = e4(ci, True, 10.0, 0.0)
  assert f[2] == DRIVE
  for _ in range(50):
    _, f = e4(ci, True, 10.0, -5.0, pressed=True)
    assert f[2] == YIELD and f[3] == 0
  assert struct.unpack(">h", f[0:2])[0] / cam.RAW_PER_DEG == pytest.approx(-5.0, abs=0.051)   # the target reached the wheel
  outs = [e4(ci, True, 10.0, -5.0)[1] for _ in range(300)]               # released: from the wheel, faded in
  a = [struct.unpack(">h", f[0:2])[0] / cam.RAW_PER_DEG for f in outs]
  assert all(f[2] == DRIVE for f in outs) and a[0] == pytest.approx(-5.0, abs=0.051)
  steps = np.abs(np.diff(a))
  assert steps[:10].max() <= 0.11                                        # no snap: the target starts at rest (0.1 deg raw)
  assert steps.max() <= float(np.interp(10.0, cam._VT, cam.TARGET_RATE_DEG_S)) * 0.01 + 0.051
  assert a[-1] == pytest.approx(10.0, abs=0.051)


def test_fault_mid_drive_stops_the_target_at_once(angle_file):
  ci = clarity(); f6 = ready(ci)
  e4(ci, False, 0.0, 0.0)
  for _ in range(60):
    _, f = e4(ci, True, 5.0, 0.0)
  assert f[2] == DRIVE
  f6.run([v4(fault=True, steering=False, reason=4, counter=k % 4) for k in range(8, 10)])   # EPS reports FAULT (JUMP)
  assert ci.CS.eps_cal_status.fault == "angle_fault (JUMP)"
  _, f = e4(ci, True, 5.0, 0.0)
  assert standby(f)


def test_loop_not_running_faults_after_100ms(angle_file):
  # a request the loop never takes up (bit lost, mode not reached) would otherwise be a silent no-steer (audit S-4)
  ci = clarity()
  f6 = ready(ci)
  e4(ci, False, 0.0, 0.0)
  _, f = e4(ci, True, 0.0, 0.0)
  assert f[2] == DRIVE and ci.CS.eps_cal_status.request_sent
  f6.run([v4(steering=False, reason=1, counter=k % 4) for k in range(8, 13)])   # 5 status frames = 10 carState updates
  assert ci.CS.eps_cal_status.fault == ""
  f6.run([v4(steering=False, reason=1, counter=1)])
  assert ci.CS.eps_cal_status.fault == "loop_not_running (NO_REQUEST)" and not ci.CS.eps_cal_status.angle_ready
  _, f = e4(ci, True, 0.0, 0.0)
  assert standby(f)                                                      # the target stops, which clears the fault
  f6.run([v4(steering=False, reason=1, counter=k % 4) for k in range(2, 4)])
  assert ci.CS.eps_cal_status.fault == "" and ci.CS.eps_cal_status.angle_ready


def test_loop_not_running_without_a_request_is_not_a_fault(angle_file):
  ci = clarity()
  f6 = ready(ci)
  for k in range(20):
    e4(ci, False, 0.0, 0.0)
    f6.run([v4(steering=False, reason=1, counter=k % 4)])
  assert ci.CS.eps_cal_status.fault == ""


def test_angle_mode_sets_the_panda_angle_bit():
  from opendbc.car.honda.stock_aol import qualified
  from opendbc.car.honda.values import HondaSafetyFlags
  bit = int(HondaSafetyFlags.CLARITY_ANGLE)
  off = cam.apply_angle_mode(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), False)
  on = cam.apply_angle_mode(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), True)
  stock = cam.apply_angle_mode(params(CAR.HONDA_CLARITY, [eps(b'39990-TRW-A020\x00\x00')]), True)
  assert on.safetyConfigs[-1].safetyParam & bit and not off.safetyConfigs[-1].safetyParam & bit
  assert not stock.safetyConfigs[-1].safetyParam & bit                   # stock EPS firmware: no angle mode, no bit
  assert on.safetyConfigs[-1].safetyParam & ~bit == off.safetyConfigs[-1].safetyParam
  # AOL qualification sees the Nidec word without the bit, and the bit must match the flag
  for cp in (on, off):
    cp.alternativeExperience = 32
  assert qualified(on) == qualified(off)
  off.safetyConfigs[-1].safetyParam |= bit
  assert not qualified(off)


def test_angle_mode_reports_the_angle_lateral_limit():
  # the UI torque bar scales its angle-mode estimate by CP.maxLateralAccel, as on the other angle cars
  from opendbc.car.lateral import ISO_LATERAL_ACCEL
  off = cam.apply_angle_mode(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), False)
  on = cam.apply_angle_mode(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), True)
  stock = cam.apply_angle_mode(params(CAR.HONDA_CLARITY, [eps(b'39990-TRW-A020\x00\x00')]), True)
  assert on.maxLateralAccel == ISO_LATERAL_ACCEL == 3.0
  assert off.maxLateralAccel == stock.maxLateralAccel != on.maxLateralAccel   # torque mode / stock EPS: unchanged
  assert abs(off.maxLateralAccel - 0.325) < 0.01                               # the Accord's measured max (substitute.toml)


def test_angle_mode_with_a_pedal_qualifies_like_the_pedal_alone():
  # the owner's Clarity (11-21 parity drive: no lateral): panda now installs 7 RX checks + the AOL pair, so angle mode +
  # pedal must qualify exactly as the pedal alone did (544 -> 544 | 4096, alternativeExperience 32)
  from opendbc.car.honda.stock_aol import qualified
  from opendbc.car.honda.nidec_interceptor import qualified as interceptor_qualified
  from opendbc.car.honda.values import HondaFlags, HondaSafetyFlags
  cps = [cam.apply_angle_mode(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), angle) for angle in (False, True)]
  for cp in cps:
    cp.alternativeExperience = 32
    cp.flags |= HondaFlags.GAS_INTERCEPTOR.value
    cp.safetyConfigs[-1].safetyParam |= int(HondaSafetyFlags.GAS_INTERCEPTOR | HondaSafetyFlags.NIDEC_PEDAL_AOL)
    cp.pcmCruise = False
  assert [cp.safetyConfigs[-1].safetyParam for cp in cps] == [544, 4640]
  assert qualified(cps[0]) and qualified(cps[1])
  assert interceptor_qualified(cps[0]) and interceptor_qualified(cps[1])
  # the angle bit must match the flag, on both checks
  cps[1].safetyConfigs[-1].safetyParam &= ~int(HondaSafetyFlags.CLARITY_ANGLE)
  assert not qualified(cps[1]) and not interceptor_qualified(cps[1])


def test_torque_mode_frames_unchanged():
  ci = clarity()
  ci.update([])
  ci.CS.out = structs.CarState(vEgo=15.0).as_reader()
  cc = structs.CarControl(latActive=True)
  cc.actuators.torque = 0.3
  _, frames = ci.apply(cc.as_reader(), 1_000_000_000)
  f = next(bytes(x[1]) for x in frames if x[0] == 0xE4)
  assert f[3] == 0x00 and f[2] & 0x0C != 0x0C                            # no angle marker in torque mode


def test_angle_setting_leaves_other_hondas_alone():
  cp = params(CAR.HONDA_CIVIC_BOSCH, [])
  flags, sct = cp.flags, cp.steerControlType
  cam.apply_angle_mode(cp, True)
  assert cp.flags == flags and cp.steerControlType == sct


# Owner rule 11-18: no angle request ever leaves openpilot unless the EPS build itself reports angle support and runs it.
NOT_ANGLE_CAPABLE = {
  "no 0x6A4 (stock, CleanPTM, P1)": [None] * 20,
  "MM 0x02 in torque mode (v1)": [v1(1, 1, 0x02, counter=k % 4) for k in range(10)],
  "MM 0x02 stock mode (v1)": [v1(0, 0, 0x02, counter=k % 4) for k in range(10)],
  "0x0A in mode 3 (v1)": [v1(3, 3, 0x0A, counter=k % 4, b0_extra=8) for k in range(10)],
  "unknown layout-4 build claiming MODE 1": [v4(build=0x11, counter=k % 4) for k in range(10)],
  "v2 build 0x0B in MODE 1": [v4(build=0x0B, counter=k % 4) for k in range(10)],
  "v2 build 0x0D in MODE 1": [v4(build=0x0D, counter=k % 4) for k in range(10)],
  "0x0E still in stock mode (switch pending)": [v4(mode=0, steering=False, reason=2, counter=k % 4) for k in range(10)],
  "0x0E in MODE 1 with the FAULT bit": [v4(fault=True, steering=False, reason=5, counter=k % 4) for k in range(10)],
}


@pytest.mark.parametrize("state", NOT_ANGLE_CAPABLE)
def test_no_angle_request_unless_the_build_reports_angle_support(angle_file, state):
  ci = clarity(); f = Feed(ci)
  f.run(NOT_ANGLE_CAPABLE[state])
  assert not ci.CS.eps_cal_status.angle_ready and ci.CS.eps_cal_status.fault, state
  for k in range(30):                                  # lateral active, a real target, the wheel elsewhere
    _, d = e4(ci, True, 20.0 + k, 0.0)
    assert standby(d), (state, d.hex())                # no target, no request: STANDBY, which any other build ignores


@pytest.mark.parametrize("setting", [dict(fade_down_s=1.0), dict(assist_during_override=True), dict(torque_scale=0.5)])
def test_press_yields_whatever_the_torque_mode_settings(angle_file, setting):
  # Override Fade Down / Assist During Override / Torque During Override shape a press in torque mode; angle mode always
  # yields (and the Night Star page hides those rows in angle mode)
  import dataclasses
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
  ci = clarity(); ready(ci)
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, **setting)})()
  e4(ci, False, 0.0, 0.0)
  for _ in range(100):
    _, f = e4(ci, True, 10.0, 0.0)
  assert f[2] == DRIVE
  for _ in range(50):
    _, f = e4(ci, True, 10.0, -5.0, pressed=True)
    assert f[2] == YIELD and f[3] == 0


@pytest.mark.parametrize("fade_up", [0.0, 0.5, 3.0])
def test_engage_fade_follows_override_fade_up(angle_file, fade_up):
  import dataclasses
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
  ci = clarity(); ready(ci)
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, fade_up_s=fade_up)})()
  e4(ci, False, 0.0, 0.0, v=5.0)
  ex = ci.CC.angle_sender; w = []; prev = 0.0
  for _ in range(600):
    e4(ci, True, 350.0, 0.0, v=5.0); w.append(abs(ex.apply_angle - prev) / 0.01); prev = ex.apply_angle
  full = min(float(np.interp(5.0, cam._VT, cam.TARGET_RATE_DEG_S)), float(np.interp(5.0, cam._V, cam.ANGLE_STEP_DEG)) / 0.01)
  t_full = next(k for k, x in enumerate(w) if x >= 0.99 * full) * 0.01      # first time the full rate is reached
  if fade_up == 0.0:
    assert t_full < 0.5                                                  # only the acceleration limit
  else:
    assert t_full >= 0.6 * fade_up                                       # the limits fade over the setting


@pytest.mark.parametrize("limit", [0.0, 40.0])
def test_steering_angle_rate_limit_caps_the_target_in_carcontroller(angle_file, limit):
  # Night Star "Steering Angle Rate Limit" (HondaEpsAngleRateLimit): applied to the angle target in CarController
  import dataclasses
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
  ci = clarity(); ready(ci)
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, angle_rate_limit_deg_s=limit,
                                                                                          fade_up_s=0.0)})()
  e4(ci, False, 0.0, 0.0, v=5.0)
  ex = ci.CC.angle_sender; w = []; prev = 0.0
  for _ in range(400):
    e4(ci, True, 300.0, 0.0, v=5.0); w.append(abs(ex.apply_angle - prev) / 0.01); prev = ex.apply_angle
  cap = min(float(np.interp(5.0, cam._VT, cam.TARGET_RATE_DEG_S)), float(np.interp(5.0, cam._V, cam.ANGLE_STEP_DEG)) / 0.01)
  if limit:
    assert max(w) <= limit + 1e-6 and max(w) > 0.99 * limit
  else:
    assert max(w) > 0.99 * cap                                           # 0 = off: only the sender's own cap


# --- '+' software ID (39990+TRW+A020, PTM 2.0 / angle PTM marker): same application as ',' ---
PTM2 = b'39990+TRW+A020\x00\x00'


def test_ptm2_id_is_the_same_modified_clarity():
  from opendbc.car.honda.steer_ratio import get_honda_vgr_profile, normalize_honda_eps_fw
  from opendbc.car.honda.fingerprints import FW_VERSIONS
  from opendbc.car.structs import CarParams
  assert normalize_honda_eps_fw(PTM2) == normalize_honda_eps_fw(MODIFIED) == "39990-TRW-A020"
  assert PTM2 in FW_VERSIONS[CAR.HONDA_CLARITY][(CarParams.Ecu.eps, 0x18da30f1, None)]
  a, b = params(CAR.HONDA_CLARITY, [eps(PTM2)]), params(CAR.HONDA_CLARITY, [eps(MODIFIED)])
  assert a.flags & HondaFlags.EPS_MODIFIED and a.flags == b.flags                       # modified, same VGR flags
  assert get_honda_vgr_profile([eps(PTM2)]) == get_honda_vgr_profile([eps(MODIFIED)]) is not None


def test_ptm2_id_gets_angle_mode(angle_file):
  ci = clarity(PTM2)
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CC.angle_sender is not None


# --- effort fade: sent = wheel + w * (trajectory - wheel), w smoothstep 0 -> 1 over engage_s ---

def _release(engage_s, effort_fade=True, frames=120, v=8.0):
  s = cam.AngleModeSender()
  wheel, rate = -37.0, 100.0                       # car e8/e9: released 35-60 deg from the target, wheel still moving
  s.update(False, 2.0, wheel, v, True, measured_rate_deg_s=rate)
  log = []
  for _ in range(frames):
    wheel += rate * cam.DT_CTRL
    rate *= 0.97
    _, req = s.update(True, 2.0, wheel, v, True, measured_rate_deg_s=rate, engage_s=engage_s, effort_fade=effort_fade)
    log.append((wheel, s.apply_angle, s.out_angle, float(req)))
  return np.array(log)


def test_effort_fade_starts_at_the_wheel_and_hands_over_to_the_trajectory():
  L = _release(0.5)
  gap = np.abs(L[:, 2] - L[:, 0])                  # what the EPS loop sees as its error
  traj_gap = np.abs(L[:, 1] - L[:, 0])
  assert gap[0] < 0.05 * max(traj_gap[0], 0.1) + 0.01
  assert np.all(gap[:49] <= traj_gap[:49] + 1e-9)
  assert L[49, 2] == pytest.approx(L[49, 1], abs=1e-9)        # w = 1 at engage_s (50 frames)
  assert np.allclose(L[50:, 2], L[50:, 1], atol=1e-9)


def test_effort_fade_off_or_zero_time_sends_the_trajectory():
  for L in (_release(0.5, effort_fade=False), _release(0.0)):
    assert np.allclose(L[:, 2], L[:, 1], atol=1e-9)


@pytest.mark.parametrize("v", [2.0, 10.0, 20.0])
def test_effort_fade_respects_the_eps_step_limit(v):
  L = _release(1.0, v=v, frames=200)
  step = min(float(np.interp(v, cam._V, cam.ANGLE_STEP_DEG)), cam.std_angle_step(v))
  sent = (L[1:, 3] > 0) & (L[:-1, 3] > 0)          # steps between frames that both carry the request
  assert sent.sum() > 150                            # at 20 m/s the wheel starts beyond the limit: a few frames wait
  assert np.abs(np.diff(L[:, 2]))[sent].max() <= step + 1e-9


def test_below_min_steer_speed_is_standby(angle_file):
  import dataclasses
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
  ci = clarity()
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, min_steer_speed_mph=10.0)})()
  ready(ci)
  _, d = e4(ci, True, 10.0, 0.0, v=2.0)
  assert standby(d)


def test_min_steer_speed_zero_keeps_steering_at_standstill(angle_file):
  # 0 = no speed gate. At a stop vEgo dithers between 0 and about -1e-5; `v >= 0` dropped the request on every negative
  # sample (Clarity joystick 11-24: request on 0.3 s, off 0.3 s)
  import dataclasses
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
  ci = clarity()
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, min_steer_speed_mph=0)})()
  ready(ci)
  frames = [e4(ci, True, 10.0, 0.0, v=v)[1] for v in [0.0, -1e-5, 0.0, -3e-6] * 10]
  assert all(d[2] == DRIVE for d in frames)                                           # steering held through the dither


# --- angle mode: the override levels are the settings up to 5 deg and rise to 1.28 x in sharp turns (from 45 deg) ---

def test_angle_mode_threshold_curve():
  from opendbc.car.honda.modified_eps import angle_mode_threshold
  assert [round(angle_mode_threshold(1300, a)) for a in (0, 5, -15, 30, 45, 200)] == [1300, 1300, 1404, 1534, 1664, 1664]


def test_default_levels_match_the_old_single_setting():
  # the old 2000 setting scaled 0.78 / 0.84 / 1.0 at 5 / 15 / 45 deg, and a press ended under 0.6 of that (personal branch)
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS, angle_mode_threshold
  for a, old in ((0, 0.78), (15, 0.84), (45, 1.0)):
    assert angle_mode_threshold(DEFAULT_SETTINGS.override_start_torque, a) == pytest.approx(2000 * old, rel=0.005)
    assert angle_mode_threshold(DEFAULT_SETTINGS.override_end_torque, a) == pytest.approx(0.6 * 2000 * old, rel=0.005)


def _press_at(ci, angle, torque, n=6):
  from opendbc.can import CANPacker
  pk = CANPacker("honda_clarity_hybrid_2018_can_generated")
  cs = None
  for _ in range(n):
    _press_at.t += 10_000_000
    msgs = [pk.make_can_msg("STEERING_SENSORS", 0, {"STEER_ANGLE": angle, "COUNTER": _press_at.c}),
            pk.make_can_msg("STEER_STATUS", 0, {"STEER_TORQUE_SENSOR": torque, "COUNTER": _press_at.c})]
    _press_at.c = (_press_at.c + 1) % 4
    cs = ci.update([(_press_at.t, [(a, d, b) for a, d, b in msgs])])
  return cs.steeringPressed
_press_at.t, _press_at.c = 3_000_000_000, 0


def test_angle_mode_press_threshold_follows_the_angle(angle_file):
  import dataclasses
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
  ci = clarity()
  ci.CS.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, override_start_torque=1300,
                                                                                          override_end_torque=500)})()
  assert _press_at(ci, 2.0, 1400)              # near center 1400 > 1300: a press
  assert _press_at(ci, 2.0, 550, n=50)         # still above the end level: still pressed
  assert not _press_at(ci, 2.0, 450, n=12)     # under the end level for 0.1 s: released
  assert not _press_at(ci, 60.0, 1400)         # 60 deg: 1400 < 1664, not a press
  assert _press_at(ci, 60.0, 1700)
  assert _press_at(ci, 60.0, 700, n=50)        # 60 deg: the end level rises too (500 -> 640)
  assert not _press_at(ci, 60.0, 600, n=12)


def test_torque_mode_press_threshold_ignores_the_angle():
  import dataclasses
  from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
  ci = clarity()                                # Angle Mode off: torque mode
  ci.CS.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, override_start_torque=1660)})()
  assert not _press_at(ci, 2.0, 1400)
  assert _press_at(ci, 60.0, 1700)             # torque mode: the setting at every angle
  assert not _press_at(ci, 60.0, 0, n=150)
  assert not _press_at(ci, 60.0, 1650)


def test_only_v3_and_torque_frames_are_packed():
  # the v2 byte-3 mode / authority, payload bit and stock arm bits are gone from the packer
  import inspect
  from opendbc.car.honda import hondacan
  args = inspect.signature(hondacan.create_steering_control).parameters
  assert not {"eps_mode", "angle_payload", "arm_bits"} & set(args)
  for name in ("AuthorityRamp", "stock_arm_bits", "STOCK_ARM_IMAGES", "ANGLE_PAYLOAD", "HOLD_LIMITS_FADE_S"):
    assert not hasattr(cam, name), name
