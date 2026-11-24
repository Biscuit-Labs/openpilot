"""RDX 3G (TJB) angle mode on the linear-angle EPS build 0x0C, the first angle-profile car (angle_profiles.py).

The whole openpilot side runs as on the car: CarInterface on the angle PTM image, carState from 0x6A2 / 0x6A4 frames the
EPS would send, the real CarController and packer (Bosch STEERING_CONTROL), and every 0xE4 it builds goes through panda's
own safety code (libsafety, hondaBosch with the angle bit and profile 1) on the bus it is sent on."""
import numpy as np
import pytest

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, OWN_GEOMETRY, safety_param_bits, vm_angle_limit
from opendbc.car.honda.hondacan import CanBus
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.meps.linear_angle import SEND_FRAMES, STALE_FRAMES
from opendbc.car.honda.tests.test_eps_cal_status import honda_checksum, v4
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.values import CAR, DBC, HondaFlags, HondaSafetyFlags
from opendbc.safety.tests.libsafety import libsafety_py

ANGLE_FW = b'39990+TJB+A220\x00\x00'   # angle PTM (build 0x0C)
TORQUE_FW = b'39990-TJB,A220\x00\x00'  # torque PTM (FadeMatch)
STOCK_FW = b'39990-TJB-A220\x00\x00'
PROFILE = ANGLE_PROFILES[CAR.ACURA_RDX_3G]
LIN, STATUS = 0x6A2, 0x6A4
SAFETY = libsafety_py.libsafety


def rdx(fw=ANGLE_FW, angle=True, candidate=CAR.ACURA_RDX_3G):
  # card: CarParams from the interface (car_helpers sets carFw), then the pre-create hook applies the setting
  cp = params(candidate, [eps(fw)])
  cp.carFw = [eps(fw)]
  return CarInterface(cam.apply_angle_mode(cp, angle))


def lin_frame(lin_deg, pub_deg, counter, loop=1, ref_latched=1):
  b = bytearray(8)
  b[0:2] = (int(round(-10 * lin_deg)) & 0xFFFF).to_bytes(2, "big")   # STEER_ANGLE sign (raw = -10 x deg)
  b[2:4] = (int(round(-10 * pub_deg)) & 0xFFFF).to_bytes(2, "big")
  b[6] = loop | (ref_latched << 1)
  b[7] = (counter & 3) << 4
  b[7] |= honda_checksum(bytes(b), LIN)
  return bytes(b)


class Car:
  """The EPS side of the bus at 100 Hz (0x6A2 every frame, 0x6A4 every other), openpilot's CarInterface, and panda."""
  def __init__(self, ci, v=10.0, wheel=0.0, send_lin=True, build=0x0C):
    self.ci, self.v, self.wheel, self.send_lin, self.build = ci, float(v), float(wheel), send_lin, build
    self.ref_latched = 1
    self.bus = CanBus(ci.CP)
    self.k, self.t = 0, 1_000_000_000
    self.packer = CANPacker(DBC[ci.CP.carFingerprint][Bus.pt])     # the platform's own DBC (any profile car)
    self.rate = 0.0
    SAFETY.set_safety_hooks(ci.CP.safetyConfigs[-1].safetyModel.raw, int(ci.CP.safetyConfigs[-1].safetyParam))   # hondaBosch / hondaNidec
    SAFETY.set_controls_allowed(True)
    self.set_speed(v)

  def set_speed(self, v):
    self.v = float(v)
    for _ in range(6):   # panda: vehicle_speed.min over the last 6 samples
      msg = self.packer.make_can_msg("ENGINE_DATA", self.bus.pt, {"XMISSION_SPEED": self.v * 3.6})
      SAFETY.safety_rx_hook(libsafety_py.make_CANPacket(msg[0], msg[2], msg[1]))

  def frames(self):
    out = []
    if self.k % 2 == 0:
      out.append((STATUS, v4(build=self.build, counter=(self.k // 2) % 4), self.bus.pt))
    if self.send_lin:
      out.append((LIN, lin_frame(self.wheel, 0.97 * self.wheel, self.k % 4, ref_latched=self.ref_latched), self.bus.pt))
    return out

  def step(self, lat, desired, pressed=False, torque=0.0):
    """One 10 ms frame: the EPS frames reach panda and carState, openpilot builds its 0xE4, panda checks it."""
    self.k += 1
    self.t += 10_000_000
    SAFETY.set_timer((self.t // 1000) & 0xFFFFFFFF)
    frames = self.frames()
    for addr, dat, bus in frames:
      SAFETY.safety_rx_hook(libsafety_py.make_CANPacket(addr, bus, dat))
    cs = self.ci.update([(self.t, frames)])
    # what the rest of carState would say (no wheel-speed or torque frames here); the angle is carState's own (0x6A2)
    self.ci.CS.out = structs.CarState(vEgo=self.v, steeringAngleDeg=cs.steeringAngleDeg, steeringRateDeg=self.rate,
                                      steeringPressed=bool(pressed), steeringTorque=float(torque)).as_reader()
    cc = structs.CarControl(latActive=lat)
    cc.actuators.steeringAngleDeg = float(desired)
    _, sends = self.ci.apply(cc.as_reader(), self.t)
    e4 = [(bytes(d), b) for a, d, b in sends if a == 0xE4]
    assert len(e4) == 1
    dat, bus = e4[0]
    assert bus == self.bus.lkas
    ok = SAFETY.safety_tx_hook(libsafety_py.make_CANPacket(0xE4, bus, dat))
    target = int.from_bytes(dat[0:2], "big", signed=True) / -10.
    return cs, dat, ok, target


def request(dat):
  return bool(dat[2] & 0x80) and bool(dat[2] & 0x20)


# --- startup selection ---

def test_angle_image_selects_angle_mode_with_profile_1():
  ci = rdx()
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.angle
  param = ci.CP.safetyConfigs[-1].safetyParam
  assert param & HondaSafetyFlags.CLARITY_ANGLE and (param & 0xE000) == safety_param_bits(PROFILE) == 1 << 13
  assert ci.CP.steerRatio == pytest.approx(OWN_GEOMETRY[CAR.ACURA_RDX_3G].steer_ratio) == pytest.approx(16.79)         # paramsd starts at the on-center ratio, not 11.95
  assert ci.CP.maxLateralAccel == 3.0                               # the torque bar's angle-mode scale (ISO)
  assert ci.CC.angle_sender.profile is PROFILE and ci.CC.angle_sender.linear and ci.CC.stock_arm   # Clarity arm/abort field (STOCK_ARM_IMAGES)
  assert ci.CS.eps_cal_status.enabled and ci.CS.linear_angle.required
  assert ci.CC.eps_mode == 0xF1


@pytest.mark.parametrize("fw,angle", [(TORQUE_FW, True), (ANGLE_FW, False), (STOCK_FW, True)],
                         ids=["torque_ptm", "setting_off", "stock"])
def test_other_images_and_setting_off_keep_torque_mode(fw, angle):
  ci = rdx(fw, angle)
  assert not ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.torque
  assert not ci.CP.safetyConfigs[-1].safetyParam & (HondaSafetyFlags.CLARITY_ANGLE | 0xE000)
  assert ci.CC.angle_sender is None and ci.CC.eps_mode == 0
  assert not ci.CS.eps_cal_status.enabled and not ci.CS.linear_angle.enabled


def test_mmr_shares_the_profile():
  ci = rdx(candidate=CAR.ACURA_RDX_3G_MMR)
  assert ci.CC.angle_sender.profile == PROFILE
  assert (ci.CP.safetyConfigs[-1].safetyParam & 0xE000) == 1 << 13


def test_bosch_stock_aol_still_qualifies_in_angle_mode():
  # panda compares the Bosch word with the angle bits masked out (honda.h); openpilot's AOL qualifier does the same
  from opendbc.car.honda import stock_aol
  for angle in (False, True):
    cp = rdx(angle=angle).CP
    cp.alternativeExperience = 32
    assert stock_aol.qualified(cp), angle
  cp = rdx().CP
  cp.alternativeExperience = 32
  cp.safetyConfigs[-1].safetyParam = (cp.safetyConfigs[-1].safetyParam & ~0xE000) | (2 << 13)   # wrong profile
  assert not stock_aol.qualified(cp)


# --- the 0x6A2 latch: linear from the start ---

def test_carstate_angle_is_the_linear_angle():
  car = Car(rdx(), wheel=12.5)
  for _ in range(6):
    cs, *_ = car.step(False, 0.)
  assert car.ci.CS.linear_angle.latched and not cs.steerFaultTemporary and car.ci.CS.eps_cal_status.angle_ready
  assert cs.steeringAngleDeg == pytest.approx(12.5, abs=0.05)
  assert car.ci.CS.linear_angle.published_deg == pytest.approx(0.97 * 12.5, abs=0.05)


@pytest.mark.parametrize("build", [0x0C, 0x0B])
def test_no_linear_angle_never_steers(build):
  # a profile car needs 0x6A2 whatever build 0x6A4 reports (panda: it is the RX check); never a silent fallback
  car = Car(rdx(), send_lin=False, build=build)
  for _ in range(20):
    cs, dat, ok, _ = car.step(True, 5.)
    assert ok and not request(dat)
  assert cs.steerFaultTemporary and not car.ci.CS.linear_angle.latched


def test_reference_not_latched_is_not_ready():
  # before the EPS latches its reference from 0x156, 0x6A2 carries the published SAS with REF_LATCHED 0: carState shows
  # that sane angle, openpilot faults (temporary) and never requests; the latch then brings steering in like an engage
  car = Car(rdx(), wheel=7.0)
  car.ref_latched = 0
  for i in range(30):
    cs, dat, ok, _ = car.step(True, 3.)
    assert ok and not request(dat), i
  assert cs.steerFaultTemporary and car.ci.CS.linear_angle.fault_reason == "linear_angle_not_aligned"
  assert cs.steeringAngleDeg == pytest.approx(7.0, abs=0.05)
  car.ref_latched = 1
  for i in range(30):
    cs, dat, ok, target = car.step(True, 3.)
    assert ok, i
    car.wheel = target
  assert request(dat) and not cs.steerFaultTemporary
  # and a later drop of the latch (EPS re-aligning) stops the request at once
  car.ref_latched = 0
  cs, dat, ok, _ = car.step(True, 3.)
  assert ok and not request(dat) and cs.steerFaultTemporary


def test_stale_linear_angle_faults_and_drops_the_request():
  car = Car(rdx())
  for _ in range(20):
    _, dat, ok, _ = car.step(True, 2.)
    assert ok
  assert request(dat)
  car.send_lin = False
  for i in range(STALE_FRAMES + 3):
    cs, dat, ok, _ = car.step(True, 2.)
    assert ok, i                                   # the request drops (SEND_FRAMES) before panda's 50 ms block
    assert request(dat) == (i < SEND_FRAMES), i
  assert cs.steerFaultTemporary and not request(dat)


# --- the sender: limits from the profile, every frame through panda ---

def test_sender_limit_is_the_profile_row():
  for v in (1., 3., 5., 10., 20., 30., 40.):
    assert cam.std_angle_limit(v, profile=PROFILE) == pytest.approx(vm_angle_limit(v, PROFILE))
    assert cam.angle_limit(v, profile=PROFILE) == pytest.approx(vm_angle_limit(v, PROFILE))
  assert vm_angle_limit(20., PROFILE) == pytest.approx(29.2, abs=0.1) and vm_angle_limit(30., PROFILE) == pytest.approx(16.9, abs=0.1)


@pytest.mark.parametrize("v", [3., 10., 20., 30., 40.])
@pytest.mark.parametrize("sign", [1., -1.])
def test_sender_at_its_clamp_passes_panda(v, sign):
  # openpilot asks for more than the 3.6 m/s^2 angle with the wheel following the target: every frame passes, and the
  # target walks up to the clamp (byte 3 = MODE 1 | AUTH 15, byte 2 = request | payload, via the Bosch DBC signals)
  car = Car(rdx(), v=v)
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
  # hold through override (default on): the request stays up, AUTH drops to 0 while the driver turns the wheel away at
  # 350 deg/s, then climbs back; the target stays on the plan. Stock arm 2, abort while pressed.
  car = Car(rdx(), v=v)
  plan = 0.5 * vm_angle_limit(v, PROFILE)
  auth, arm = [], []
  for i in range(700):
    pressed = 150 <= i < 400
    car.wheel = min(car.wheel + 3.5, 450.) if pressed else car.wheel + 0.2 * (car.ci.CC.angle_sender.out_angle - car.wheel)
    _, dat, ok, target = car.step(True, plan, pressed=pressed, torque=3000. if pressed else 0.)
    assert ok, (v, i, target)
    if i > 20:
      # payload bit 5 + the stock arm field: arm 2 (0x48), abort (0x44) while the driver yields; panda reads only bits 7 / 5
      assert request(dat) and (dat[2] & 0x7F) in (0x20 | cam.E4_ARM2, 0x20 | cam.E4_ARM2_ABORT), (i, hex(dat[2]))
    auth.append(dat[3] >> 4)
    arm.append(dat[2] & 0x4C)
  assert min(auth[160:400]) == 0 and auth[-1] == 15          # no authority while pressed, full again after the release
  assert set(arm[21:150]) == {cam.E4_ARM2} and set(arm[160:400]) == {cam.E4_ARM2_ABORT} and set(arm[450:]) == {cam.E4_ARM2}
  assert target == pytest.approx(plan, abs=0.06)


@pytest.mark.parametrize("v", [10., 20., 30.])
@pytest.mark.parametrize("rate", [20., 60.])
def test_engage_with_the_wheel_moving_passes_panda(v, rate):
  car = Car(rdx(), v=v)
  for i in range(10):            # the EPS frames first, not engaged
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
      car.wheel = target         # after 0.3 s the wheel follows what passes


def test_waits_for_the_wheel_inside_the_limit():
  # engaging with the wheel beyond the 3.6 m/s^2 angle: no request until it is inside, then every frame passes
  v = 20.
  lim = vm_angle_limit(v, PROFILE)
  car = Car(rdx(), v=v, wheel=lim + 20.)
  for i in range(60):
    _, dat, ok, _ = car.step(True, 0.)
    assert ok and not request(dat), i
  steered = False
  for i in range(300):
    car.wheel = max(car.wheel - 0.5, 0.)   # the driver unwinds
    _, dat, ok, target = car.step(True, 0.)
    assert ok, (i, car.wheel, target)
    if request(dat):
      steered = True
      assert abs(car.wheel) <= lim + 0.5
  assert steered


def test_torque_mode_frames_unchanged_on_the_torque_ptm():
  # the torque PTM image on the same Bosch DBC: no payload bit, byte 3 zero
  ci = rdx(TORQUE_FW)
  ci.update([(1_000_000_000, [])])
  ci.CS.out = structs.CarState(vEgo=10.).as_reader()
  cc = structs.CarControl(latActive=True)
  cc.actuators.torque = 0.3
  _, sends = ci.apply(cc.as_reader(), 1_000_000_000)
  dat = [bytes(d) for a, d, b in sends if a == 0xE4][0]
  assert dat[2] & 0x20 == 0 and dat[3] == 0
  assert np.int16(int.from_bytes(dat[0:2], "big", signed=True)) != 0
