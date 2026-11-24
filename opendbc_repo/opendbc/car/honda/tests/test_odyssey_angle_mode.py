"""Odyssey (THR-A020) angle mode on the linear-angle EPS build (39990+THR+A020, rwd-xray THR_0x0C_PORTS/thr): panda row 4 = the
Odyssey's own measured model (17.81 / 3.00 / -0.00035: paramsd + understeer from one public route on THR-A030 hardware; A030 = A020
rack is an inference, rwd-xray kefit_logs/FIT_ODYSSEY_KE_SR_20261123.md), Nidec, and the angle-only PTM image (mode 0 is stock).

Same harness as the RDX (test_rdx_angle_mode.Car): the real Odyssey CarInterface / CarController / packer, and every 0xE4 through
panda's own safety code (libsafety, hondaNidec with the angle bit and profile 4)."""
import pytest

from opendbc.car import structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, OWN_GEOMETRY, safety_param_bits, vm_angle_limit
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.meps.linear_angle import SEND_FRAMES, STALE_FRAMES
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.tests.test_rdx_angle_mode import Car, request
from opendbc.car.honda.values import CAR, HondaFlags, HondaSafetyFlags

ANGLE_FW = b'39990+THR+A020\x00\x00'   # angle PTM (build 0x0C / 0x0D)
STOCK_FW = b'39990-THR-A020\x00\x00'
PROFILE = ANGLE_PROFILES[CAR.HONDA_ODYSSEY]


def odyssey(fw=ANGLE_FW, angle=True):
  cp = params(CAR.HONDA_ODYSSEY, [eps(fw)])
  cp.carFw = [eps(fw)]
  return CarInterface(cam.apply_angle_mode(cp, angle))


# --- startup selection ---

def test_angle_image_selects_angle_mode_with_profile_4():
  ci = odyssey()
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.angle
  param = ci.CP.safetyConfigs[-1].safetyParam
  assert PROFILE.index == 4 and (param & 0xE000) == safety_param_bits(PROFILE) == 4 << 13
  assert param & HondaSafetyFlags.CLARITY_ANGLE and not param & HondaSafetyFlags.NIDEC_ALT
  assert ci.CP.steerRatio == pytest.approx(OWN_GEOMETRY[CAR.HONDA_ODYSSEY].steer_ratio)
  assert ci.CP.maxLateralAccel == 3.0
  assert ci.CC.angle_sender.profile == PROFILE and ci.CC.angle_sender.linear and ci.CC.stock_arm   # Clarity arm/abort field (STOCK_ARM_IMAGES)
  assert ci.CS.eps_cal_status.enabled and ci.CS.linear_angle.required
  assert ci.CC.eps_mode == 0xF1


@pytest.mark.parametrize("fw,angle", [(ANGLE_FW, False), (STOCK_FW, True)], ids=["setting_off", "stock"])
def test_setting_off_or_stock_image_is_stock_torque_mode(fw, angle):
  ci = odyssey(fw, angle)
  assert ci.CP.steerControlType == structs.CarParams.SteerControlType.torque
  assert not ci.CP.flags & (HondaFlags.CLARITY_ANGLE_MODE | HondaFlags.EPS_MODIFIED)
  assert not ci.CP.safetyConfigs[-1].safetyParam & (HondaSafetyFlags.CLARITY_ANGLE | 0xE000)
  assert ci.CC.angle_sender is None and ci.CC.eps_mode == 0


# --- the 0x6A2 latch ---

def test_carstate_angle_is_the_linear_angle():
  car = Car(odyssey(), wheel=-9.5)
  for _ in range(6):
    cs, *_ = car.step(False, 0.)
  assert car.ci.CS.linear_angle.latched and not cs.steerFaultTemporary and car.ci.CS.eps_cal_status.angle_ready
  assert cs.steeringAngleDeg == pytest.approx(-9.5, abs=0.05)


def test_reference_not_latched_is_not_ready():
  car = Car(odyssey(), wheel=4.0)
  car.ref_latched = 0
  for i in range(30):
    cs, dat, ok, _ = car.step(True, 3.)
    assert ok and not request(dat), i
  assert cs.steerFaultTemporary and car.ci.CS.linear_angle.fault_reason == "linear_angle_not_aligned"
  car.ref_latched = 1
  for i in range(30):
    cs, dat, ok, target = car.step(True, 3.)
    assert ok, i
    car.wheel = target
  assert request(dat) and not cs.steerFaultTemporary


def test_stale_linear_angle_faults_and_drops_the_request():
  car = Car(odyssey())
  for _ in range(20):
    _, dat, ok, _ = car.step(True, 2.)
    assert ok
  assert request(dat)
  car.send_lin = False
  for i in range(STALE_FRAMES + 3):
    cs, dat, ok, _ = car.step(True, 2.)
    assert ok, i
    assert request(dat) == (i < SEND_FRAMES), i
  assert cs.steerFaultTemporary and not request(dat)


# --- the sender on row 4, every frame through panda (hondaNidec) ---

def test_sender_limit_is_row_4():
  for v in (1., 3., 5., 10., 20., 30., 40.):
    assert cam.std_angle_limit(v, profile=PROFILE) == pytest.approx(vm_angle_limit(v, PROFILE))
  assert (PROFILE.steer_ratio, PROFILE.wheelbase, PROFILE.slip_factor) == (17.81, 3.00, -0.00035)
  assert vm_angle_limit(20., PROFILE) == pytest.approx(31.31, abs=0.01) and vm_angle_limit(30., PROFILE) == pytest.approx(16.05, abs=0.01)


@pytest.mark.parametrize("v", [3., 10., 20., 30., 40.])
@pytest.mark.parametrize("sign", [1., -1.])
def test_sender_at_its_clamp_passes_panda(v, sign):
  car = Car(odyssey(), v=v)
  desired = sign * 1.2 * vm_angle_limit(v, PROFILE)
  for i in range(700):
    _, dat, ok, target = car.step(True, desired)
    assert ok, (v, i, target)
    car.wheel = target
  assert request(dat) and dat[3] == 0xF1
  assert abs(target) > 0.98 * vm_angle_limit(v, PROFILE)
  assert abs(target) <= vm_angle_limit(max(v - 1., 1.), PROFILE) + 0.1


@pytest.mark.parametrize("v", [2.2, 10., 20.])
def test_sender_through_an_override_passes_panda(v):
  car = Car(odyssey(), v=v)
  plan = 0.5 * vm_angle_limit(v, PROFILE)
  auth, arm = [], []
  for i in range(700):
    pressed = 150 <= i < 400
    car.wheel = min(car.wheel + 3.5, 520.) if pressed else car.wheel + 0.2 * (car.ci.CC.angle_sender.out_angle - car.wheel)
    _, dat, ok, target = car.step(True, plan, pressed=pressed, torque=3000. if pressed else 0.)
    assert ok, (v, i, target)
    if i > 20:
      # payload bit 5 + the stock arm field: arm 2 (0x48), abort (0x44) while the driver yields; panda reads only bits 7 / 5
      assert request(dat) and (dat[2] & 0x7F) in (0x20 | cam.E4_ARM2, 0x20 | cam.E4_ARM2_ABORT), (i, hex(dat[2]))
    auth.append(dat[3] >> 4)
    arm.append(dat[2] & 0x4C)
  assert min(auth[160:400]) == 0 and auth[-1] == 15
  assert set(arm[21:150]) == {cam.E4_ARM2} and set(arm[160:400]) == {cam.E4_ARM2_ABORT} and set(arm[450:]) == {cam.E4_ARM2}
  assert target == pytest.approx(plan, abs=0.06)


def test_waits_for_the_wheel_inside_the_limit():
  v = 20.
  lim = vm_angle_limit(v, PROFILE)
  car = Car(odyssey(), v=v, wheel=-(lim + 20.))
  for i in range(60):
    _, dat, ok, _ = car.step(True, 0.)
    assert ok and not request(dat), i
  steered = False
  for i in range(300):
    car.wheel = min(car.wheel + 0.5, 0.)
    _, dat, ok, target = car.step(True, 0.)
    assert ok, (i, car.wheel, target)
    if request(dat):
      steered = True
      assert abs(car.wheel) <= lim + 0.5
  assert steered
