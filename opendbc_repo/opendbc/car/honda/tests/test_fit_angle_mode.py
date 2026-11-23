"""Fit (T5R-C030) angle mode on the linear-angle EPS build: panda row 7 = the Fit's own measured model (17.0 / 2.53 / -0.000973,
one public T5R-C030 route, 6-18 m/s),
Nidec, and the angle-only PTM image (39990+T5R+C030; no Fit torque-PTM image exists, so mode 0 is the stock torque mode).

Same harness as the RDX (test_rdx_angle_mode.Car): the real Fit CarInterface / CarController / packer on the ILX-family DBC, and
every 0xE4 through panda's own safety code (libsafety, hondaNidec with NIDEC_ALT, the angle bit and profile 7)."""
import pytest

from opendbc.car import structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda import stock_aol
from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, OWN_GEOMETRY, safety_param_bits, vm_angle_limit
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.meps.linear_angle import SEND_FRAMES, STALE_FRAMES
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.tests.test_rdx_angle_mode import Car, request
from opendbc.car.honda.values import CAR, HondaFlags, HondaSafetyFlags

ANGLE_FW = b'39990+T5R+C030\x00\x00'   # angle PTM (build 0x0C)
STOCK_FW = b'39990-T5R-C030\x00\x00'
PROFILE = ANGLE_PROFILES[CAR.HONDA_FIT]


def fit(fw=ANGLE_FW, angle=True):
  cp = params(CAR.HONDA_FIT, [eps(fw)])
  cp.carFw = [eps(fw)]
  return CarInterface(cam.apply_angle_mode(cp, angle))


# --- startup selection ---

def test_angle_image_selects_angle_mode_with_profile_7():
  ci = fit()
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.angle
  param = ci.CP.safetyConfigs[-1].safetyParam
  assert PROFILE.index == 7 and (param & 0xE000) == safety_param_bits(PROFILE) == 7 << 13
  assert param & HondaSafetyFlags.CLARITY_ANGLE and param & HondaSafetyFlags.NIDEC_ALT          # Nidec, alt SCM messages
  assert ci.CP.steerRatio == pytest.approx(OWN_GEOMETRY[CAR.HONDA_FIT].steer_ratio)
  assert ci.CP.maxLateralAccel == 3.0
  assert ci.CC.angle_sender.profile == PROFILE and ci.CC.angle_sender.linear and not ci.CC.stock_arm
  assert ci.CS.eps_cal_status.enabled and ci.CS.linear_angle.required
  assert ci.CC.eps_mode == 0xF1


@pytest.mark.parametrize("fw,angle", [(ANGLE_FW, False), (STOCK_FW, True)], ids=["setting_off", "stock"])
def test_setting_off_or_stock_image_is_stock_torque_mode(fw, angle):
  ci = fit(fw, angle)
  assert ci.CP.steerControlType == structs.CarParams.SteerControlType.torque
  assert not ci.CP.flags & (HondaFlags.CLARITY_ANGLE_MODE | HondaFlags.EPS_MODIFIED)    # an angle image's mode 0 is stock
  assert not ci.CP.safetyConfigs[-1].safetyParam & (HondaSafetyFlags.CLARITY_ANGLE | 0xE000)
  assert ci.CC.angle_sender is None and ci.CC.eps_mode == 0


def test_nidec_stock_aol_sees_the_angle_bits_masked():
  # panda masks the angle bit and the profile out of the Nidec word (honda.h); openpilot's qualifier does the same, so angle
  # mode never changes whether AOL qualifies, and a wrong profile never qualifies
  cp_on, cp_off = fit(angle=True).CP, fit(angle=False).CP
  for cp in (cp_on, cp_off):
    cp.alternativeExperience = 32
  assert stock_aol.qualified(cp_on) == stock_aol.qualified(cp_off)
  cp_on.safetyConfigs[-1].safetyParam = (cp_on.safetyConfigs[-1].safetyParam & ~0xE000) | (6 << 13)
  assert not stock_aol.qualified(cp_on)


# --- the 0x6A2 latch ---

def test_carstate_angle_is_the_linear_angle():
  car = Car(fit(), wheel=-9.5)
  for _ in range(6):
    cs, *_ = car.step(False, 0.)
  assert car.ci.CS.linear_angle.latched and not cs.steerFaultTemporary and car.ci.CS.eps_cal_status.angle_ready
  assert cs.steeringAngleDeg == pytest.approx(-9.5, abs=0.05)


@pytest.mark.parametrize("build", [0x0C, 0x0B])
def test_no_linear_angle_never_steers(build):
  car = Car(fit(), send_lin=False, build=build)
  for _ in range(20):
    cs, dat, ok, _ = car.step(True, 5.)
    assert ok and not request(dat)
  assert cs.steerFaultTemporary and not car.ci.CS.linear_angle.latched


def test_reference_not_latched_is_not_ready():
  car = Car(fit(), wheel=4.0)
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
  car = Car(fit())
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


# --- the sender on row 7, every frame through panda (hondaNidec) ---

def test_sender_limit_is_row_7():
  for v in (1., 3., 5., 10., 20., 30., 40.):
    assert cam.std_angle_limit(v, profile=PROFILE) == pytest.approx(vm_angle_limit(v, PROFILE))
  assert (PROFILE.steer_ratio, PROFILE.wheelbase, PROFILE.slip_factor) == (17.0, 2.53, -0.000973)   # measured (one public route)


@pytest.mark.parametrize("v", [3., 10., 20., 30., 40.])
@pytest.mark.parametrize("sign", [1., -1.])
def test_sender_at_its_clamp_passes_panda(v, sign):
  car = Car(fit(), v=v)
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
  car = Car(fit(), v=v)
  plan = 0.5 * vm_angle_limit(v, PROFILE)
  auth = []
  for i in range(700):
    pressed = 150 <= i < 400
    car.wheel = min(car.wheel + 3.5, 450.) if pressed else car.wheel + 0.2 * (car.ci.CC.angle_sender.out_angle - car.wheel)
    _, dat, ok, target = car.step(True, plan, pressed=pressed, torque=3000. if pressed else 0.)
    assert ok, (v, i, target)
    if i > 20:
      assert request(dat) and (dat[2] & 0x7F) == 0x20, (i, hex(dat[2]))     # no stock arm bits off the Clarity
    auth.append(dat[3] >> 4)
  assert min(auth[160:400]) == 0 and auth[-1] == 15
  assert target == pytest.approx(plan, abs=0.06)


@pytest.mark.parametrize("v", [10., 20., 30.])
@pytest.mark.parametrize("rate", [20., -60.])
def test_engage_with_the_wheel_moving_passes_panda(v, rate):
  car = Car(fit(), v=v)
  for _ in range(10):
    car.step(False, 0.)
  for i in range(160):
    if i < 30:
      car.wheel += rate * 0.01
      car.rate = rate
    else:
      car.rate = 0.
    _, dat, ok, target = car.step(True, 0.)
    assert ok, (v, rate, i, target)
    if i >= 30:
      car.wheel = target


def test_waits_for_the_wheel_inside_the_limit():
  v = 20.
  lim = vm_angle_limit(v, PROFILE)
  car = Car(fit(), v=v, wheel=-(lim + 20.))
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
