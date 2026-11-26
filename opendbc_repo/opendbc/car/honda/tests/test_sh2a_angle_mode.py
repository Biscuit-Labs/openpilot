"""SH-2A family linear-angle EPS build 0x0E, protocol v3 (rwd-xray lab/ptm-family SH2A ports) on their angle-profile rows:
Civic (Nidec, row 2: TBA-A030, TEG-A010), Civic Bosch (row 3: TGG-A120, TBA-C020, TBA-C120), CR-V 5G (row 1: TLA-A040,
TLA-A220), Insight (row 1, shared with the CR-V: TXM-A040).

Same harness as test_rdx_angle_mode.py: the real CarInterface on the car's angle PTM image ('+' in both separator slots),
carState from the 0x6A2 / 0x6A4 frames the EPS sends (0x6A2 byte 6 = loop running | REF_LATCHED 1: the SH-2A reference is
the EPS's own, so the bit is always set), the real CarController and the platform's own packer/DBC, and every 0xE4 through
panda's own safety code (libsafety) with the car's safety model (hondaNidec or hondaBosch) and its profile bits."""
import pytest

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, CAR_ROWS, OWN_GEOMETRY, safety_param_bits, vm_angle_limit
from opendbc.car.honda.tests import test_rdx_angle_mode as rdx_t
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.values import CAR, DBC, MODIFIED_EPS_FW, HondaFlags, HondaSafetyFlags
from opendbc.car.honda.interface import CarInterface

SAFETY = rdx_t.SAFETY
request = rdx_t.request
DRIVE, YIELD = rdx_t.DRIVE, rdx_t.YIELD

# (platform, part code) of every SH-2A angle build; the angle image is 39990+CODE+VAR, the torque PTM 39990-CODE,VAR
SH2A = [
  (CAR.HONDA_CIVIC, "TBA", "A030"), (CAR.HONDA_CIVIC, "TEG", "A010"),
  (CAR.HONDA_CIVIC_BOSCH, "TGG", "A120"), (CAR.HONDA_CIVIC_BOSCH, "TBA", "C020"), (CAR.HONDA_CIVIC_BOSCH, "TBA", "C120"),
  (CAR.HONDA_CRV_5G, "TLA", "A040"), (CAR.HONDA_CRV_5G, "TLA", "A220"),
  (CAR.HONDA_INSIGHT, "TXM", "A040"),
]
IDS = [f"{code}-{var}" for _, code, var in SH2A]
ROW = {CAR.HONDA_CRV_5G: 1, CAR.HONDA_CIVIC: 2, CAR.HONDA_CIVIC_BOSCH: 3, CAR.HONDA_INSIGHT: 1}   # orchestrator allocation 11-23 (measured rows, 767ceebb60)


def fw(code, var, sep):
  return f"39990{sep[0]}{code}{sep[1]}{var}".encode() + b"\x00\x00"


def make(car, code, var, kind="angle", angle=True):
  version = fw(code, var, {"angle": "++", "torque": "-,", "stock": "--"}[kind])
  cp = params(car, [eps(version)])
  cp.carFw = [eps(version)]
  return CarInterface(cam.apply_angle_mode(cp, angle))


class Car(rdx_t.Car):
  """test_rdx_angle_mode.Car with the platform's own DBC and safety model."""
  def __init__(self, ci, v=10.0, wheel=0.0, send_lin=True, build=0x0E):
    self.ci, self.v, self.wheel, self.send_lin, self.build = ci, float(v), float(wheel), send_lin, build
    self.ref_latched = 1
    self.bus = rdx_t.CanBus(ci.CP)
    self.k, self.t = 0, 1_000_000_000
    self.packer = CANPacker(DBC[ci.CP.carFingerprint][Bus.pt])
    self.rate = 0.0
    sc = ci.CP.safetyConfigs[-1]
    SAFETY.set_safety_hooks(int(sc.safetyModel.raw), int(sc.safetyParam))
    SAFETY.set_controls_allowed(True)
    self.set_speed(v)


@pytest.fixture(params=SH2A, ids=IDS)
def build(request):
  return request.param


# --- selection ---

def test_firmware_list_has_every_angle_image():
  for car, code, var in SH2A:
    assert fw(code, var, "++") in MODIFIED_EPS_FW[car], (car, code, var)


def test_rows_are_the_allocation():
  for car, row in ROW.items():
    assert CAR_ROWS[car] == row and ANGLE_PROFILES[car].index == row


def test_angle_image_selects_angle_mode_on_its_row(build):
  car, code, var = build
  ci = make(car, code, var)
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.angle
  sc = ci.CP.safetyConfigs[-1]
  assert sc.safetyParam & HondaSafetyFlags.CLARITY_ANGLE and (sc.safetyParam & 0xE000) == safety_param_bits(ANGLE_PROFILES[car]) == ROW[car] << 13
  bosch = bool(ci.CP.flags & HondaFlags.BOSCH)
  assert sc.safetyModel == (structs.CarParams.SafetyModel.hondaBosch if bosch else structs.CarParams.SafetyModel.hondaNidec)
  assert ci.CP.steerRatio == pytest.approx(OWN_GEOMETRY[car].steer_ratio)
  assert ci.CP.maxLateralAccel == 3.0
  assert ci.CC.angle_sender.profile is ANGLE_PROFILES[car] and ci.CC.angle_sender.linear
  assert ci.CS.linear_angle.required


@pytest.mark.parametrize("kind,angle", [("torque", True), ("angle", False), ("stock", True)], ids=["torque_ptm", "setting_off", "stock"])
def test_other_images_and_setting_off_keep_torque_mode(build, kind, angle):
  car, code, var = build
  ci = make(car, code, var, kind, angle)
  assert not ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.torque
  assert not ci.CP.safetyConfigs[-1].safetyParam & (HondaSafetyFlags.CLARITY_ANGLE | 0xE000)
  assert ci.CC.angle_sender is None


# --- 0x6A2 ---

def test_carstate_angle_is_the_linear_angle(build):
  car = Car(make(*build), wheel=12.5)
  for _ in range(6):
    cs, *_ = car.step(False, 0.)
  assert car.ci.CS.linear_angle.latched and car.ci.CS.linear_angle.ref_latched and not cs.steerFaultTemporary
  assert cs.steeringAngleDeg == pytest.approx(12.5, abs=0.05)


def test_build_0e_steers(build):
  car = Car(make(*build), wheel=3.0, build=0x0E)
  for _ in range(30):
    cs, dat, ok, _ = car.step(True, 3.)
    assert ok
  assert car.ci.CS.linear_angle.latched and request(dat) and dat[2] == DRIVE and not cs.steerFaultTemporary


@pytest.mark.parametrize("bid", [0x0B, 0x0C, 0x0D])
def test_v2_builds_never_steer(build, bid):
  # protocol v2 builds are unsupported: eps_cal_status faults them (unknown_build) and only STANDBY goes out
  car = Car(make(*build), wheel=3.0, build=bid)
  for _ in range(30):
    cs, dat, ok, _ = car.step(True, 3.)
    assert ok and not request(dat)
  assert cs.steerFaultTemporary and car.ci.CS.eps_cal_status.fault == "unknown_build"


def test_no_linear_angle_never_steers(build):
  car = Car(make(*build), send_lin=False)
  for _ in range(20):
    cs, dat, ok, _ = car.step(True, 5.)
    assert ok and not request(dat)
  assert cs.steerFaultTemporary


def test_stale_linear_angle_drops_the_request_before_panda(build):
  car = Car(make(*build))
  for _ in range(20):
    _, dat, ok, _ = car.step(True, 2.)
    assert ok
  assert request(dat)
  car.send_lin = False
  for i in range(rdx_t.STALE_FRAMES + 3):
    cs, dat, ok, _ = car.step(True, 2.)
    assert ok and request(dat) == (i < rdx_t.SEND_FRAMES), i
  assert cs.steerFaultTemporary


# --- the sender through panda ---

@pytest.mark.parametrize("v", [3., 10., 20., 40.])
@pytest.mark.parametrize("sign", [1., -1.])
def test_sender_at_its_clamp_passes_panda(build, v, sign):
  car, code, var = build
  prof = ANGLE_PROFILES[car]
  c = Car(make(car, code, var), v=v)
  desired = sign * 1.2 * vm_angle_limit(v, prof)
  for i in range(700):
    _, dat, ok, target = c.step(True, desired)
    assert ok, (v, i, target)
    c.wheel = target
  assert request(dat) and dat[2] == DRIVE
  assert abs(target) > 0.98 * vm_angle_limit(v, prof)
  assert abs(target) <= vm_angle_limit(max(v - 1., 1.), prof) + 0.1


@pytest.mark.parametrize("v", [2.2, 20.])
def test_sender_through_an_override_passes_panda(build, v):
  # protocol v3: YIELD while pressed with the target following the wheel (inside panda's angle limit), DRIVE after the
  # release with the target walking back to the plan
  car, code, var = build
  c = Car(make(car, code, var), v=v)
  plan = 0.5 * vm_angle_limit(v, ANGLE_PROFILES[car])
  wheel_max = 0.9 * vm_angle_limit(v, ANGLE_PROFILES[car])
  b2, tg = [], []
  for i in range(700):
    pressed = 150 <= i < 400
    c.wheel = min(c.wheel + 3.5, wheel_max) if pressed else c.wheel + 0.2 * (c.ci.CC.angle_sender.out_angle - c.wheel)
    _, dat, ok, target = c.step(True, plan, pressed=pressed, torque=3000. if pressed else 0.)
    assert ok, (v, i, target)
    if i > 20:
      assert request(dat) and dat[2] in (DRIVE, YIELD), (i, hex(dat[2]))
    b2.append(dat[2])
    tg.append(target)
  assert set(b2[21:150]) == {DRIVE} and set(b2[160:400]) == {YIELD} and set(b2[450:]) == {DRIVE}
  assert 1.5 * plan < tg[399] <= wheel_max + 0.2
  assert target == pytest.approx(plan, abs=0.06)


@pytest.mark.parametrize("rate", [20., 60.])
def test_engage_with_the_wheel_moving_passes_panda(build, rate):
  c = Car(make(*build), v=20.)
  for _ in range(10):
    c.step(False, 0.)
  for i in range(160):
    if i < 30:
      c.wheel += rate * 0.01
      c.rate = rate
    else:
      c.rate = 0.
    _, dat, ok, target = c.step(True, 0.)
    assert ok, (rate, i, target)
    if i >= 30:
      c.wheel = target


def test_waits_for_the_wheel_inside_the_limit(build):
  car, code, var = build
  v = 20.
  lim = vm_angle_limit(v, ANGLE_PROFILES[car])
  c = Car(make(car, code, var), v=v, wheel=lim + 20.)
  for i in range(60):
    _, dat, ok, _ = c.step(True, 0.)
    assert ok and not request(dat), i
  steered = False
  for i in range(300):
    c.wheel = max(c.wheel - 0.5, 0.)
    _, dat, ok, target = c.step(True, 0.)
    assert ok, (i, c.wheel, target)
    if request(dat):
      steered = True
      assert abs(c.wheel) <= lim + 0.5
  assert steered
