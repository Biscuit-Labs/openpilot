"""Angle-profile cars in their option combinations (owner 11-23): a Nidec angle car with a pedal interceptor, and a Bosch
angle car with openpilot longitudinal. The angle rule (0x6A2 the measured angle, the row's 3.6 m/s^2 limit, the jerk
step) must hold unchanged, and the option's own messages must stay bounded exactly as without angle mode."""
import unittest

import numpy as np

from opendbc.can import CANPacker
from opendbc.car import Bus, gen_empty_fingerprint, structs
from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, CAR_ROWS, safety_param_bits, vm_angle_limit
from opendbc.car.honda.hondacan import honda_checksum
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.nidec_interceptor import create_command
from opendbc.car.honda.values import CAR, DBC, HondaFlags, HondaSafetyFlags
from opendbc.safety.tests.libsafety import libsafety_py

SafetyModel = structs.CarParams.SafetyModel
JUMP = ([0., 5., 8., 10., 12., 15., 20., 25., 30.], [40, 40, 31, 25, 19, 10, 10, 10, 10])


def base_config(car):
  cp = CarInterface.get_params(car, gen_empty_fingerprint(), [], False, False, False)
  return cp, cp.safetyConfigs[-1].safetyModel.raw, cp.safetyConfigs[-1].safetyParam


NIDEC_CARS = [c for c in CAR_ROWS if base_config(c)[1] == int(SafetyModel.hondaNidec)]
BOSCH_CARS = [c for c in CAR_ROWS if base_config(c)[1] == int(SafetyModel.hondaBosch) and not base_config(c)[0].flags & HondaFlags.BOSCH_RADARLESS]


class AngleComboBase(unittest.TestCase):
  PT_BUS = 0
  STEER_BUS = 0

  def setup_car(self, car, model, word):
    self.car, self.profile = car, ANGLE_PROFILES[car]
    self.safety = libsafety_py.libsafety
    self.assertEqual(self.safety.set_safety_hooks(model, word), 0)
    self.safety.init_tests()
    self.safety.set_timer(1_000_000)
    self.packer = CANPacker(DBC[car][Bus.pt])
    self.ctr = 0

  def tx(self, msg):
    return self.safety.safety_tx_hook(libsafety_py.make_CANPacket(msg[0], msg[2], msg[1]))

  def rx_raw(self, addr, bus, dat):
    return self.safety.safety_rx_hook(libsafety_py.make_CANPacket(addr, bus, bytes(dat)))

  def lin(self, raw):
    self.ctr = (self.ctr + 1) & 3
    w = raw & 0xFFFF
    dat = bytearray([w >> 8, w & 0xFF, w >> 8, w & 0xFF, 0, 0, 0x03, self.ctr << 4])
    dat[7] |= honda_checksum(0x6A2, None, dat)
    return self.rx_raw(0x6A2, self.PT_BUS, dat)

  def speed(self, v_ms):
    msg = self.packer.make_can_msg("ENGINE_DATA", self.PT_BUS, {"XMISSION_SPEED": v_ms * 3.6})
    return self.rx_raw(msg[0], msg[2], msg[1])

  def angle(self, target, request=True, payload=True):
    # protocol v3 (meps/protocol.py): request + payload = a DRIVE angle frame (0x4C), neither = STANDBY (0x0D); byte 3 0
    b2 = 0x4C if (request and payload) else 0x0D if not (request or payload) else (0x80 if request else 0) | (0x20 if payload else 0)
    t = target & 0xFFFF
    dat = bytearray([t >> 8, t & 0xFF, b2, 0, 0])
    dat[4] = honda_checksum(0xE4, None, dat)
    return self.tx((0xE4, bytes(dat), self.STEER_BUS))

  def start(self, v_ms, meas=0):
    for _ in range(6):
      self.speed(v_ms)
      self.lin(meas)
    self.safety.set_controls_allowed(True)
    self.assertTrue(self.angle(0, False, False))   # not steering: the next target starts from the wheel
    self.safety.set_controls_allowed(True)

  def lim(self, v_ms):
    return int(vm_angle_limit(max(v_ms - 1., 1.), self.profile) * 10 + 1)

  def step(self, v_ms):
    s = max(v_ms - 1., 1.)
    return int(min(vm_angle_limit(s, self.profile) * 10 / 100., float(np.interp(s, *JUMP))) + 1)

  def check_angle_rule(self, v_ms=10.):
    step, lim = self.step(v_ms), self.lim(v_ms)
    self.start(v_ms)
    self.assertTrue(self.angle(0))                       # at the wheel
    self.assertTrue(self.angle(step))                    # one step
    self.assertFalse(self.angle(3 * step))               # beyond the jerk step
    self.start(v_ms, lim)
    self.assertTrue(self.angle(lim))                     # at the row's limit
    self.assertFalse(self.angle(lim + 1))                # beyond it
    self.safety.set_controls_allowed(False)
    self.assertFalse(self.angle(0))                      # not allowed: no angle frame
    self.assertTrue(self.angle(0, False, False))


class TestNidecAngleWithPedal(AngleComboBase):
  """Every Nidec angle car with a pedal interceptor (param bit 32, NIDEC_ALT kept as the car has it)."""

  def setup_pedal(self, car):
    cp, model, base = base_config(car)
    word = base | HondaSafetyFlags.GAS_INTERCEPTOR | HondaSafetyFlags.CLARITY_ANGLE | safety_param_bits(ANGLE_PROFILES[car])
    self.setup_car(car, model, word)

  def test_angle_rule_holds_with_the_pedal(self):
    for car in NIDEC_CARS:
      with self.subTest(car=car):
          self.setup_pedal(car)
          self.check_angle_rule()
  

  def engage_physically(self, car):
    # the pedal only accepts gas after a physical set (honda_interceptor); the angle word also needs 0x6A2 fresh to engage
    from opendbc.safety.tests.test_honda_interceptor import TestHondaInterceptor
    cp, model, base = base_config(car)
    word = base | HondaSafetyFlags.GAS_INTERCEPTOR | HondaSafetyFlags.CLARITY_ANGLE | safety_param_bits(ANGLE_PROFILES[car])
    h = TestHondaInterceptor()
    h.init(word)
    # the helper picks the NIDEC_ALT message set from the bare words 4/36; with the angle bits set, pick it from the bit
    h.alt = bool(word & HondaSafetyFlags.NIDEC_ALT)
    h.packer = CANPacker("acura_ilx_2016_can_generated" if h.alt else "honda_civic_touring_2016_can_generated")
    self.safety, self.packer, self.profile, self.ctr = h.safety, h.packer, ANGLE_PROFILES[car], 0
    for tick in range(20):
      h.feed(tick)
      self.lin(0)
    for tick, button in ((20, 3), (21, 0)):
      h.feed(tick, button=button)
      self.lin(0)
    return h

  def test_pedal_and_angle_after_a_physical_engage(self):
    for car in NIDEC_CARS:
      with self.subTest(car=car):
        h = self.engage_physically(car)
        self.assertTrue(self.safety.get_controls_allowed())
        self.assertTrue(h.tx(h.command(0.5)))                       # pedal gas allowed
        self.assertTrue(self.angle(0, False, False))                 # from the wheel
        self.assertTrue(self.angle(0))                               # angle frame at the wheel
        self.assertFalse(self.angle(900))                            # far beyond the step and the limit

  def test_pedal_engage_needs_the_linear_angle(self):
    # without 0x6A2 (an RX check in angle mode) the car never engages, so neither pedal gas nor steering is allowed
    from opendbc.safety.tests.test_honda_interceptor import TestHondaInterceptor
    for car in NIDEC_CARS:
      with self.subTest(car=car):
        cp, model, base = base_config(car)
        word = base | HondaSafetyFlags.GAS_INTERCEPTOR | HondaSafetyFlags.CLARITY_ANGLE | safety_param_bits(ANGLE_PROFILES[car])
        h = TestHondaInterceptor()
        h.init(word)
        h.alt = bool(word & HondaSafetyFlags.NIDEC_ALT)
        h.packer = CANPacker("acura_ilx_2016_can_generated" if h.alt else "honda_civic_touring_2016_can_generated")
        for tick in range(20):
          h.feed(tick)
        h.feed(20, button=3)
        h.feed(21, button=0)
        self.assertFalse(h.safety.get_controls_allowed())
        self.assertFalse(h.tx(h.command(0.5)))
        self.assertTrue(h.tx(h.command(0.0)))

  def test_no_linear_angle_never_steers_with_the_pedal(self):
    for car in NIDEC_CARS:
      with self.subTest(car=car):
          self.setup_pedal(car)
          for _ in range(6):
            self.speed(10.)
          self.safety.set_controls_allowed(True)
          self.assertFalse(self.angle(0))
  


class TestBoschAngleWithLongitudinal(AngleComboBase):
  """Every Bosch angle car with openpilot longitudinal (BOSCH_LONG, debug builds): 0xE4 moves to bus 1 with ACC_CONTROL."""
  PT_BUS = 1
  STEER_BUS = 1

  def setup_long(self, car):
    cp, model, base = base_config(car)
    word = base | HondaSafetyFlags.BOSCH_LONG | HondaSafetyFlags.CLARITY_ANGLE | safety_param_bits(ANGLE_PROFILES[car])
    self.setup_car(car, model, word)

  def acc(self, gas, accel):
    msg = self.packer.make_can_msg("ACC_CONTROL", self.PT_BUS, {"GAS_COMMAND": gas, "ACCEL_COMMAND": accel, "BRAKE_REQUEST": accel < 0})
    return self.tx(msg)

  def test_angle_rule_holds_with_longitudinal(self):
    for car in BOSCH_CARS:
      with self.subTest(car=car):
          self.setup_long(car)
          self.check_angle_rule()
  

  def test_longitudinal_stays_bounded(self):
    for car in BOSCH_CARS:
      with self.subTest(car=car):
          self.setup_long(car)
          self.start(10.)
          self.assertTrue(self.acc(1000, 1.0))
          self.assertTrue(self.acc(-30000, -3.5))
          self.assertFalse(self.acc(-30000, -3.6))       # past the brake limit
          self.safety.set_controls_allowed(False)
          self.assertFalse(self.acc(1000, 1.0))
          self.assertTrue(self.acc(-30000, 0))
  


class TestEveryProfileCarDecodes(unittest.TestCase):
  def test_profile_word_installs(self):
    for car in CAR_ROWS:
      with self.subTest(car=car):
          _, model, base = base_config(car)
          word = base | HondaSafetyFlags.CLARITY_ANGLE | safety_param_bits(ANGLE_PROFILES[car])
          self.assertEqual(libsafety_py.libsafety.set_safety_hooks(model, word), 0)
          self.assertEqual((word >> 13) & 7, CAR_ROWS[car])
  


if __name__ == "__main__":
  unittest.main()
