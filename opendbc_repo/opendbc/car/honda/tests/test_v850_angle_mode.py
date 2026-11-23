"""Ridgeline (T6Z-A110) and Pilot (TG7-A070) angle mode on the V850 linear-angle EPS build 0x0C (profiles 5 and 6).

Same harness as test_rdx_angle_mode.py on the Nidec side: CarInterface on the angle PTM image, carState from the 0x6A2 /
0x6A4 frames the EPS would send, the real CarController and packer (Nidec STEERING_CONTROL, 5 bytes: the angle payload is
byte 2 bit 5 via SET_ME_X00, MODE | AUTH is byte 3 via SET_ME_X00_2), and every 0xE4 through panda's own safety code
(libsafety, hondaNidec with the angle bit and the car's profile). The Pilot row is PROVISIONAL (no Pilot routes)."""
import pytest

from opendbc.car import structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, CAR_ROWS, OWN_GEOMETRY, safety_param_bits, vm_angle_limit
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.meps.linear_angle import SEND_FRAMES, STALE_FRAMES
from opendbc.car.honda.tests import test_rdx_angle_mode as rdx_test
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.values import CAR, HondaFlags, HondaSafetyFlags
from opendbc.can import CANPacker
from opendbc.safety.tests.libsafety import libsafety_py

SAFETY = libsafety_py.libsafety
ANGLE_FW = {CAR.HONDA_RIDGELINE: b'39990+T6Z+A110\x00\x00', CAR.HONDA_PILOT: b'39990+TG7+A070\x00\x00'}
STOCK_FW = {CAR.HONDA_RIDGELINE: b'39990-T6Z-A110\x00\x00', CAR.HONDA_PILOT: b'39990-TG7-A070\x00\x00'}
ROWS = {CAR.HONDA_RIDGELINE: 5, CAR.HONDA_PILOT: 6}
CARS = tuple(ANGLE_FW)
request = rdx_test.request


def interface(candidate, fw=None, angle=True):
  fw = ANGLE_FW[candidate] if fw is None else fw
  cp = params(candidate, [eps(fw)])
  cp.carFw = [eps(fw)]
  return CarInterface(cam.apply_angle_mode(cp, angle))


class Car(rdx_test.Car):
  """test_rdx_angle_mode.Car on the Nidec platform DBC and panda's hondaNidec hooks."""
  def __init__(self, ci, v=10.0, wheel=0.0, send_lin=True, build=0x0C):
    self.ci, self.v, self.wheel, self.send_lin, self.build = ci, float(v), float(wheel), send_lin, build
    self.ref_latched = 1
    self.bus = rdx_test.CanBus(ci.CP)
    self.k, self.t = 0, 1_000_000_000
    self.packer = CANPacker("acura_ilx_2016_can_generated")
    self.rate = 0.0
    SAFETY.set_safety_hooks(int(structs.CarParams.SafetyModel.hondaNidec), int(ci.CP.safetyConfigs[-1].safetyParam))
    SAFETY.set_controls_allowed(True)
    self.set_speed(v)


# --- startup selection ---

@pytest.mark.parametrize("candidate", CARS)
def test_angle_image_selects_angle_mode_with_its_profile(candidate):
  ci = interface(candidate)
  profile = ANGLE_PROFILES[candidate]
  assert CAR_ROWS[candidate] == ROWS[candidate]
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.angle
  assert ci.CP.safetyConfigs[-1].safetyModel == structs.CarParams.SafetyModel.hondaNidec
  param = ci.CP.safetyConfigs[-1].safetyParam
  assert param & HondaSafetyFlags.CLARITY_ANGLE and (param & 0xE000) == safety_param_bits(profile) == ROWS[candidate] << 13
  assert ci.CP.steerRatio == pytest.approx(OWN_GEOMETRY[candidate].steer_ratio)
  assert ci.CP.maxLateralAccel == 3.0
  # the EPS steers to standstill in angle mode (its angle row's min speed is 0; the stock row keeps 20 kph)
  assert ci.CP.steerAtStandstill and ci.CP.minSteerSpeed == -1.0
  assert ci.CC.angle_sender.profile is profile and ci.CC.angle_sender.linear and not ci.CC.stock_arm
  assert ci.CS.eps_cal_status.enabled and ci.CS.linear_angle.required
  assert ci.CC.eps_mode == 0xF1


@pytest.mark.parametrize("candidate", CARS)
@pytest.mark.parametrize("which,angle", [("stock", True), ("angle", False)], ids=["stock", "setting_off"])
def test_stock_image_and_setting_off_keep_torque_mode(candidate, which, angle):
  ci = interface(candidate, STOCK_FW[candidate] if which == "stock" else None, angle)
  assert not ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.torque
  assert not ci.CP.safetyConfigs[-1].safetyParam & (HondaSafetyFlags.CLARITY_ANGLE | 0xE000)
  assert ci.CC.angle_sender is None and ci.CC.eps_mode == 0
  assert not ci.CS.eps_cal_status.enabled and not ci.CS.linear_angle.enabled


# --- the 0x6A2 latch ---

@pytest.mark.parametrize("candidate", CARS)
def test_carstate_angle_is_the_linear_angle(candidate):
  car = Car(interface(candidate), wheel=-9.5)
  for _ in range(6):
    cs, *_ = car.step(False, 0.)
  assert car.ci.CS.linear_angle.latched and not cs.steerFaultTemporary and car.ci.CS.eps_cal_status.angle_ready
  assert cs.steeringAngleDeg == pytest.approx(-9.5, abs=0.05)


@pytest.mark.parametrize("candidate", CARS)
def test_reference_not_latched_is_not_ready(candidate):
  # the V850 build latches its reference from 0x156 (published SAS); until then 0x6A2 carries that SAS, REF_LATCHED 0
  car = Car(interface(candidate), wheel=4.0)
  car.ref_latched = 0
  for i in range(30):
    cs, dat, ok, _ = car.step(True, 2.)
    assert ok and not request(dat), i
  assert cs.steerFaultTemporary and car.ci.CS.linear_angle.fault_reason == "linear_angle_not_aligned"
  car.ref_latched = 1
  for i in range(30):
    cs, dat, ok, target = car.step(True, 2.)
    assert ok, i
    car.wheel = target
  assert request(dat) and not cs.steerFaultTemporary


@pytest.mark.parametrize("candidate", CARS)
def test_stale_linear_angle_faults_and_drops_the_request(candidate):
  car = Car(interface(candidate))
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


# --- the sender: the Nidec frame, limits from the profile, every frame through panda ---

@pytest.mark.parametrize("candidate", CARS)
@pytest.mark.parametrize("v", [3., 10., 20., 30., 40.])
@pytest.mark.parametrize("sign", [1., -1.])
def test_sender_at_its_clamp_passes_panda(candidate, v, sign):
  profile = ANGLE_PROFILES[candidate]
  car = Car(interface(candidate), v=v)
  desired = sign * 1.2 * vm_angle_limit(v, profile)
  for i in range(700):
    _, dat, ok, target = car.step(True, desired)
    assert ok, (v, i, target)
    car.wheel = target
  # 5-byte Nidec frame: byte 2 = request | payload exactly (the V850 reads bit 5 only on a v2 angle frame), byte 3 MODE 1 | AUTH 15
  assert len(dat) == 5 and dat[2] == 0xA0 and dat[3] == 0xF1
  assert abs(target) > 0.98 * vm_angle_limit(v, profile)
  assert abs(target) <= vm_angle_limit(max(v - 1., 1.), profile) + 0.1


@pytest.mark.parametrize("candidate", CARS)
@pytest.mark.parametrize("v", [2.2, 10., 20.])
def test_sender_through_an_override_passes_panda(candidate, v):
  profile = ANGLE_PROFILES[candidate]
  car = Car(interface(candidate), v=v)
  plan = 0.5 * vm_angle_limit(v, profile)
  auth = []
  for i in range(700):
    pressed = 150 <= i < 400
    car.wheel = min(car.wheel + 3.5, 450.) if pressed else car.wheel + 0.2 * (car.ci.CC.angle_sender.out_angle - car.wheel)
    _, dat, ok, target = car.step(True, plan, pressed=pressed, torque=3000. if pressed else 0.)
    assert ok, (v, i, target)
    auth.append(dat[3] >> 4)
  assert min(auth[160:400]) == 0 and auth[-1] == 15
  assert target == pytest.approx(plan, abs=0.06)


@pytest.mark.parametrize("candidate", CARS)
@pytest.mark.parametrize("v", [10., 30.])
def test_engage_with_the_wheel_moving_passes_panda(candidate, v):
  car = Car(interface(candidate), v=v)
  for _ in range(10):
    car.step(False, 0.)
  for i in range(160):
    if i < 30:
      car.wheel += 0.6
      car.rate = 60.
    else:
      car.rate = 0.
    _, dat, ok, target = car.step(True, 0.)
    assert ok, (v, i, target)
    if i >= 30:
      car.wheel = target


@pytest.mark.parametrize("candidate", CARS)
def test_waits_for_the_wheel_inside_the_limit(candidate):
  v = 20.
  lim = vm_angle_limit(v, ANGLE_PROFILES[candidate])
  car = Car(interface(candidate), v=v, wheel=lim + 20.)
  for i in range(60):
    _, dat, ok, _ = car.step(True, 0.)
    assert ok and not request(dat), i
  steered = False
  for i in range(300):
    car.wheel = max(car.wheel - 0.5, 0.)
    _, dat, ok, target = car.step(True, 0.)
    assert ok, (i, car.wheel, target)
    if request(dat):
      steered = True
      assert abs(car.wheel) <= lim + 0.5
  assert steered
