#!/usr/bin/env python3
import unittest
import numpy as np

from opendbc.car.honda.values import HondaSafetyFlags
from opendbc.safety.tests.libsafety import libsafety_py
import opendbc.safety.tests.common as common
from opendbc.car.structs import CarParams
from opendbc.safety.tests.common import MAX_WRONG_COUNTERS

HONDA_N_COMMON_TX_MSGS = [[0xE4, 0], [0x194, 0], [0x1FA, 0], [0x30C, 0], [0x33D, 0]]


class Btn:
  NONE = 0
  MAIN = 1
  CANCEL = 2
  SET = 3
  RESUME = 4

# Honda safety has several different configurations tested here:
#  * Nidec
#    * normal (PCM-enable)
#    * alt SCM messages  (PCM-enable)
#  * Bosch
#    * Bosch with Longitudinal Support
#  * Bosch Radarless
#    * Bosch Radarless with Longitudinal Support


class HondaButtonEnableBase(common.CarSafetyTest):

  # override these inherited tests since we're using button enable
  def test_disable_control_allowed_from_cruise(self):
    pass

  def test_enable_control_allowed_from_cruise(self):
    pass

  def test_cruise_engaged_prev(self):
    pass

  def test_buttons_with_main_off(self):
    for btn in (Btn.SET, Btn.RESUME, Btn.CANCEL):
      self.safety.set_controls_allowed(1)
      self._rx(self._acc_state_msg(False))
      self._rx(self._button_msg(btn, main_on=False))
      self.assertFalse(self.safety.get_controls_allowed())

  def test_set_resume_buttons(self):
    """
      Both SET and RES should enter controls allowed on their falling edge.
    """
    for main_on in (True, False):
      self._rx(self._acc_state_msg(main_on))
      for btn_prev in range(8):
        for btn_cur in range(8):
          self._rx(self._button_msg(Btn.NONE))
          self.safety.set_controls_allowed(0)
          for _ in range(10):
            self._rx(self._button_msg(btn_prev))
            self.assertFalse(self.safety.get_controls_allowed())

          # should enter controls allowed on falling edge and not transitioning to cancel or main
          should_enable = (main_on and
                           btn_cur != btn_prev and
                           btn_prev in (Btn.RESUME, Btn.SET) and
                           btn_cur not in (Btn.CANCEL, Btn.MAIN))

          self._rx(self._button_msg(btn_cur, main_on=main_on))
          self.assertEqual(should_enable, self.safety.get_controls_allowed(), msg=f"{main_on=} {btn_prev=} {btn_cur=}")

  def test_main_cancel_buttons(self):
    """
      Both MAIN and CANCEL should exit controls immediately.
    """
    for btn in (Btn.MAIN, Btn.CANCEL):
      self.safety.set_controls_allowed(1)
      self._rx(self._button_msg(btn, main_on=True))
      self.assertFalse(self.safety.get_controls_allowed())

  def test_disengage_on_main(self):
    self.safety.set_controls_allowed(1)
    self._rx(self._acc_state_msg(True))
    self.assertTrue(self.safety.get_controls_allowed())
    self._rx(self._acc_state_msg(False))
    self.assertFalse(self.safety.get_controls_allowed())

  def test_rx_hook(self):

    # TODO: move this test to common
    # checksum checks
    for msg_type in ["btn", "gas", "speed"]:
      self.safety.set_controls_allowed(1)
      if msg_type == "btn":
        msg = self._button_msg(Btn.SET)
      if msg_type == "gas":
        msg = self._user_gas_msg(0)
      if msg_type == "speed":
        msg = self._speed_msg(0)
      self.assertTrue(self._rx(msg))
      if msg_type != "btn":
        msg[0].data[4] = 0  # invalidate checksum
        msg[0].data[5] = 0
        msg[0].data[6] = 0
        msg[0].data[7] = 0
        self.assertFalse(self._rx(msg))
        self.assertFalse(self.safety.get_controls_allowed())

    # counter
    # Skip every other counter to trigger counter faults.
    for i in range(MAX_WRONG_COUNTERS + 1):
      self._speed_msg(0)
      self._button_msg(Btn.SET)
      self._user_gas_msg(0)
      if i < MAX_WRONG_COUNTERS:
        self.safety.set_controls_allowed(1)
        self._rx(self._button_msg(Btn.SET))
        self._rx(self._speed_msg(0))
        self._rx(self._user_gas_msg(0))
      else:
        self.assertFalse(self._rx(self._button_msg(Btn.SET)))
        self.assertFalse(self._rx(self._speed_msg(0)))
        self.assertFalse(self._rx(self._user_gas_msg(0)))
        self.assertFalse(self.safety.get_controls_allowed())

    # restore counters for future tests with a couple of good messages
    for _ in range(2):
      self.safety.set_controls_allowed(1)
      self._rx(self._button_msg(Btn.SET, main_on=True))
      self._rx(self._speed_msg(0))
      self._rx(self._user_gas_msg(0))
    self._rx(self._button_msg(Btn.SET, main_on=True))
    self.assertTrue(self.safety.get_controls_allowed())


class HondaPcmEnableBase(common.CarSafetyTest):

  def test_buttons(self):
    """
      Buttons should only cancel in this configuration,
      since our state is tied to the PCM's cruise state.
    """
    for controls_allowed in (True, False):
      for main_on in (True, False):
        # not a valid state
        if controls_allowed and not main_on:
          continue

        for btn in (Btn.SET, Btn.RESUME, Btn.CANCEL):
          self.safety.set_controls_allowed(controls_allowed)
          self._rx(self._acc_state_msg(main_on))

          # btn + none for falling edge
          self._rx(self._button_msg(btn, main_on=main_on))
          self._rx(self._button_msg(Btn.NONE, main_on=main_on))

          if btn == Btn.CANCEL:
            self.assertFalse(self.safety.get_controls_allowed())
          else:
            self.assertEqual(controls_allowed, self.safety.get_controls_allowed())


class HondaBase(common.CarSafetyTest):
  MAX_BRAKE = 255
  PT_BUS: int | None = None  # must be set when inherited
  STEER_BUS: int | None = None  # must be set when inherited
  BUTTONS_BUS: int | None = None  # must be set when inherited, tx on this bus, rx on PT_BUS

  RELAY_MALFUNCTION_ADDRS = {0: (0xE4, 0x194)}  # STEERING_CONTROL

  def _powertrain_data_msg(self, cruise_on=None, brake_pressed=None, gas_pressed=None):
    # preserve the state
    if cruise_on is None:
      # or'd with controls allowed since the tests use it to "enable" cruise
      cruise_on = self.safety.get_cruise_engaged_prev() or self.safety.get_controls_allowed()
    if brake_pressed is None:
      brake_pressed = self.safety.get_brake_pressed_prev()
    if gas_pressed is None:
      gas_pressed = self.safety.get_gas_pressed_prev()

    values = {
      "ACC_STATUS": cruise_on,
      "BRAKE_PRESSED": brake_pressed,
      "PEDAL_GAS": gas_pressed,
    }
    return self.packer.make_can_msg_safety("POWERTRAIN_DATA", self.PT_BUS, values)

  def _pcm_status_msg(self, enable):
    return self._powertrain_data_msg(cruise_on=enable)

  def _speed_msg(self, speed):
    values = {"XMISSION_SPEED": speed}
    return self.packer.make_can_msg_safety("ENGINE_DATA", self.PT_BUS, values)

  def _acc_state_msg(self, main_on):
    values = {"MAIN_ON": main_on}
    return self.packer.make_can_msg_safety("SCM_FEEDBACK", self.PT_BUS, values)

  def _button_msg(self, buttons, main_on=False, bus=None):
    bus = self.PT_BUS if bus is None else bus
    values = {"CRUISE_BUTTONS": buttons}
    return self.packer.make_can_msg_safety("SCM_BUTTONS", bus, values)

  def _user_brake_msg(self, brake):
    return self._powertrain_data_msg(brake_pressed=brake)

  def _user_gas_msg(self, gas):
    return self._powertrain_data_msg(gas_pressed=gas)

  def _send_steer_msg(self, steer):
    values = {"STEER_TORQUE": steer}
    return self.packer.make_can_msg_safety("STEERING_CONTROL", self.STEER_BUS, values)

  def _send_brake_msg(self, brake):
    # must be implemented when inherited
    raise NotImplementedError

  def test_disengage_on_brake(self):
    self.safety.set_controls_allowed(1)
    self._rx(self._user_brake_msg(1))
    self.assertFalse(self.safety.get_controls_allowed())

  def test_steer_safety_check(self):
    self.safety.set_controls_allowed(0)
    self.assertTrue(self._tx(self._send_steer_msg(0x0000)))
    self.assertFalse(self._tx(self._send_steer_msg(0x1000)))


# ********************* Honda Nidec **********************


class TestHondaNidecSafetyBase(HondaBase):
  DBC = "honda_civic_touring_2016_can_generated"
  SAFETY_MODEL = CarParams.SafetyModel.hondaNidec

  TX_MSGS = HONDA_N_COMMON_TX_MSGS
  FWD_BLACKLISTED_ADDRS = {2: [0xE4, 0x194, 0x33D, 0x30C]}
  RELAY_MALFUNCTION_ADDRS = {0: (0xE4, 0x194, 0x33D, 0x30C)}

  PT_BUS = 0
  STEER_BUS = 0
  BUTTONS_BUS = 0

  MAX_GAS = 198

  def _send_brake_msg(self, brake, aeb_req=0, bus=0):
    values = {"COMPUTER_BRAKE": brake, "AEB_REQ_1": aeb_req}
    return self.packer.make_can_msg_safety("BRAKE_COMMAND", bus, values)

  def _rx_brake_msg(self, brake, aeb_req=0):
    return self._send_brake_msg(brake, aeb_req, bus=2)

  def _send_acc_hud_msg(self, pcm_gas, pcm_speed):
    # Used to control ACC on Nidec without pedal
    values = {"PCM_GAS": pcm_gas, "PCM_SPEED": pcm_speed}
    return self.packer.make_can_msg_safety("ACC_HUD", 0, values)

  def test_acc_hud_safety_check(self):
    for controls_allowed in [True, False]:
      self.safety.set_controls_allowed(controls_allowed)
      for pcm_gas in range(255):
        for pcm_speed in range(100):
          send = (controls_allowed and pcm_gas <= self.MAX_GAS) or (pcm_gas == 0 and pcm_speed == 0)
          self.assertEqual(send, self._tx(self._send_acc_hud_msg(pcm_gas, pcm_speed)))

  def test_fwd_hook(self):
    # normal operation, not forwarding AEB
    self.FWD_BLACKLISTED_ADDRS[2].append(0x1FA)
    self.safety.set_honda_fwd_brake(False)
    super().test_fwd_hook()

    # forwarding AEB brake signal
    self.FWD_BLACKLISTED_ADDRS = {2: [0xE4, 0x194, 0x33D, 0x30C]}
    self.safety.set_honda_fwd_brake(True)
    super().test_fwd_hook()

  def test_honda_fwd_brake_latching(self):
    # Shouldn't fwd stock Honda requesting brake without AEB
    self.assertTrue(self._rx(self._rx_brake_msg(self.MAX_BRAKE, aeb_req=0)))
    self.assertFalse(self.safety.get_honda_fwd_brake())

    # Now allow controls and request some brake
    openpilot_brake = round(self.MAX_BRAKE / 2.0)
    self.safety.set_controls_allowed(True)
    self.assertTrue(self._tx(self._send_brake_msg(openpilot_brake)))

    # Still shouldn't fwd stock Honda brake until it's more than openpilot's
    for stock_honda_brake in range(self.MAX_BRAKE + 1):
      self.assertTrue(self._rx(self._rx_brake_msg(stock_honda_brake, aeb_req=1)))
      should_fwd_brake = stock_honda_brake >= openpilot_brake
      self.assertEqual(should_fwd_brake, self.safety.get_honda_fwd_brake())

    # Shouldn't stop fwding until AEB event is over
    for stock_honda_brake in range(self.MAX_BRAKE + 1)[::-1]:
      self.assertTrue(self._rx(self._rx_brake_msg(stock_honda_brake, aeb_req=1)))
      self.assertTrue(self.safety.get_honda_fwd_brake())

    self.assertTrue(self._rx(self._rx_brake_msg(0, aeb_req=0)))
    self.assertFalse(self.safety.get_honda_fwd_brake())

  def test_brake_safety_check(self):
    for fwd_brake in [False, True]:
      self.safety.set_honda_fwd_brake(fwd_brake)
      for brake in np.arange(0, self.MAX_BRAKE + 10, 1):
        for controls_allowed in [True, False]:
          self.safety.set_controls_allowed(controls_allowed)
          if fwd_brake:
            send = False  # block openpilot brake msg when fwd'ing stock msg
          elif controls_allowed:
            send = self.MAX_BRAKE >= brake >= 0
          else:
            send = brake == 0
          self.assertEqual(send, self._tx(self._send_brake_msg(brake)))

  def test_block_aeb(self):
    for controls_allowed in [True, False]:
      self.safety.set_controls_allowed(controls_allowed)
      for aeb_signals in ({"AEB_REQ_1": 1}, {"AEB_REQ_2": 1}, {"AEB_STATUS": 1}):
        values = {"COMPUTER_BRAKE": 0, **aeb_signals}
        msg = self.packer.make_can_msg_safety("BRAKE_COMMAND", self.PT_BUS, values)
        self.assertFalse(self._tx(msg), msg=aeb_signals)
      self.assertTrue(self._tx(self._send_brake_msg(0)))


class TestHondaNidecPcmSafety(HondaPcmEnableBase, TestHondaNidecSafetyBase):
  """
    Covers the Honda Nidec safety mode
  """

  # Nidec doesn't disengage on falling edge of cruise. See comment in safety_honda.h
  def test_disable_control_allowed_from_cruise(self):
    pass


class TestHondaNidecHybridSafety(TestHondaNidecPcmSafety):
  """
    Nidec hybrids (Clarity) carry the brake in COMPUTER_BRAKE_HYBRID. Every inherited brake test runs with the
    brake in that field; safety checks the larger of the two fields, so no hybrid safety param is needed.
  """

  def _send_brake_msg(self, brake, aeb_req=0, bus=0):
    values = {"COMPUTER_BRAKE_HYBRID": brake, "AEB_REQ_1": aeb_req}
    return self.packer.make_can_msg_safety("BRAKE_COMMAND", bus, values)

  # the hybrid field may reach the stock ACC camera's ceiling; COMPUTER_BRAKE keeps the Nidec 255
  MAX_BRAKE = 320
  MAX_STANDARD_BRAKE = 255

  def test_each_brake_field_has_its_own_limit(self):
    self.safety.set_controls_allowed(True)
    std, hyb = self.MAX_STANDARD_BRAKE, self.MAX_BRAKE
    for standard, hybrid, ok in ((std, 0, True), (0, hyb, True), (std + 1, 0, False), (0, hyb + 1, False),
                                 (std, hyb, True), (std + 1, hyb, False), (0, 300, True)):
      values = {"COMPUTER_BRAKE": standard, "COMPUTER_BRAKE_HYBRID": hybrid}
      msg = self.packer.make_can_msg_safety("BRAKE_COMMAND", self.PT_BUS, values)
      self.assertEqual(ok, self._tx(msg), msg=(standard, hybrid))

  def test_hybrid_brake_needs_controls_allowed(self):
    self.safety.set_controls_allowed(False)
    self.assertFalse(self._tx(self._send_brake_msg(1)))
    self.assertTrue(self._tx(self._send_brake_msg(0)))


class TestHondaNidecClarityAngleSafety(TestHondaNidecHybridSafety):
  """
    Clarity on the angle-mode EPS build (safety bit CLARITY_ANGLE): 0xE4 bytes 0-1 are an angle target (0x14A raw,
    0.1 deg) while byte 2 bits 7 (request) and 5 (payload) are set; byte 3 bits 7:4 are the authority cut (15 = none).
    Every Nidec hybrid test still runs; the angle rule only tightens 0xE4.
  """
  DBC = "honda_clarity_hybrid_2018_can_generated"
  SAFETY_PARAM = HondaSafetyFlags.CLARITY_ANGLE

  # EPS jump threshold (honda.h), speed m/s -> 0.1 deg per frame
  JUMP = ([0., 5., 8., 10., 12., 15., 20., 25., 30.], [40, 40, 31, 25, 19, 10, 10, 10, 10])

  def _angle_msg(self, target, request=True, payload=True, cut=0):
    values = {"STEER_TORQUE": target, "STEER_TORQUE_REQUEST": request, "SET_ME_X00": 0x20 if payload else 0,
              "SET_ME_X00_2": (cut << 4) | 0x09}
    return self.packer.make_can_msg_safety("STEERING_CONTROL", self.STEER_BUS, values)

  def _set_meas(self, raw, checksum_ok=True):
    for _ in range(6):
      corrupt = None if checksum_ok else (lambda m: (m[0], m[1][:7] + bytes([m[1][7] ^ 0x01]), m[2]))
      self._rx(self.packer.make_can_msg_safety("STEERING_SENSORS", self.PT_BUS, {"STEER_ANGLE": -raw / 10.}, fix_checksum=corrupt))

  def _set_speed(self, v_ms):
    for _ in range(6):
      self._rx(self._speed_msg(v_ms * 3.6))

  @staticmethod
  def _lim(v_ms):
    # panda's 3.6 m/s^2 angle at speed - 1 m/s (0.1 deg), the same function the sender uses at its own speed
    from opendbc.car.honda import clarity_angle_mode as cam
    return int(cam.std_angle_limit(max(v_ms - 1., 1.)) * 10 + 1)

  def _step(self, v_ms):
    from opendbc.car.honda import clarity_angle_mode as cam
    s = max(v_ms - 1., 1.)
    return int(min(cam.std_angle_limit(s) * 10 / 100., float(np.interp(s, *self.JUMP))) + 1)

  def _start(self, meas=0, v_ms=10., allowed=True):
    self.safety.set_timer(1_000_000)
    self.safety.set_controls_allowed(allowed)
    self._set_speed(v_ms)
    self._set_meas(meas)
    self.assertTrue(self._tx(self._angle_msg(0, False, False)))   # not steering: the next target starts from the wheel
    self.safety.set_controls_allowed(allowed)

  def test_angle_frames_need_lateral(self):
    # the audit's case: a target of 0 with request + payload is "steer to centre", not "no torque"
    self._start(allowed=False)
    for target, request, payload in ((0, True, True), (0, True, False), (0, False, True), (100, False, False), (100, True, True)):
      self.assertFalse(self._tx(self._angle_msg(target, request, payload)), (target, request, payload))
    for cut in (0, 15):
      self.assertTrue(self._tx(self._angle_msg(0, False, False, cut)))

  def test_inactive_frame_is_all_zero(self):
    self._start()
    self.assertFalse(self._tx(self._angle_msg(0, True, False)))      # request without payload
    self.assertFalse(self._tx(self._angle_msg(0, False, True)))      # payload without request
    self.assertFalse(self._tx(self._angle_msg(100, False, False)))   # a torque word on an angle car
    self.assertTrue(self._tx(self._angle_msg(0, False, False)))

  def test_first_target_within_one_step_of_the_wheel(self):
    for v in (3., 10., 21.):
      step = self._step(v)
      for meas in (-100, 0, 150):
        for offset, ok in ((0, True), (step, True), (-step, True), (step + 1, False), (-step - 1, False), (900, False)):
          self._start(meas, v)
          self.assertEqual(ok, self._tx(self._angle_msg(meas + offset)), (v, meas, offset))

  def test_step_limit_by_speed(self):
    for v in (0., 3., 6., 9., 11., 13., 16., 21., 31., 40.):
      step = self._step(v)
      for sign in (1, -1):
        self._start(0, v)
        self.assertTrue(self._tx(self._angle_msg(0)))
        self.assertTrue(self._tx(self._angle_msg(sign * step)), (v, step))
        self.assertFalse(self._tx(self._angle_msg(sign * (2 * step + 1))), (v, step))
        # after a violation the last target is the measured angle: the next one starts from the wheel
        self.assertFalse(self._tx(self._angle_msg(sign * (step + 1))))
        self.assertTrue(self._tx(self._angle_msg(sign * step)))

  def test_jerk_step_is_the_standard_rate(self):
    # 3.6 m/s^3 = the 3.6 m/s^2 angle per second; at 21 m/s (panda speed 20) that is 31.8 deg/s, 0.318 deg per frame
    self.assertEqual(self._step(21.), 4)
    self.assertEqual(self._step(3.), 41)    # low speed: the EPS jump threshold (4 deg/frame) is tighter

  def test_lateral_accel_limit(self):
    # absolute: no exemption for no authority (cut 15), for moving back in, or for an engage at the wheel
    for v in (1., 2., 6., 11., 17., 21., 31., 40.):
      lim = self._lim(v)
      self.assertLessEqual(lim, 5001)
      for cut in (0, 15):
        self._start(lim, v)
        self.assertTrue(self._tx(self._angle_msg(lim, cut=cut)), (v, lim))
        self.assertFalse(self._tx(self._angle_msg(lim + 1, cut=cut)), (v, lim))
        self._start(-lim - 5, v)
        self.assertFalse(self._tx(self._angle_msg(-lim - 5, cut=cut)), (v, lim))   # engage beyond the limit
        self.assertFalse(self._tx(self._angle_msg(-lim - 2, cut=cut)), (v, lim))   # moving back in, still beyond

  def test_limit_numbers(self):
    # 0.9 x angle_ref AMAX: 31.8 deg at 20 m/s, 18.4 at 30; 1/v^2 outside 5-30 m/s; capped at 500 deg
    self.assertEqual(self._lim(21.), 318)
    self.assertEqual(self._lim(31.), 184)
    self.assertEqual(self._lim(41.), int(183.6 * 900 / 1600 + 1))
    self.assertEqual(self._lim(5.), int(3411 * 25 / 16 + 1) if 3411 * 25 / 16 < 5000 else 5001)
    self.assertEqual(self._lim(2.), 5001)

  def test_held_target_as_the_limit_shrinks(self):
    lim10 = self._lim(10.)
    self._start(lim10 - 5, 10.)
    for _ in range(200):
      self.assertTrue(self._tx(self._angle_msg(lim10 - 5)))
    self._set_speed(30.)
    self._set_meas(lim10 - 5)
    self.assertFalse(self._tx(self._angle_msg(lim10 - 5)))

  def test_drift_never_passes_the_limit(self):
    # closed loop: the wheel follows every target that passes; a target drifting at the jerk step goes no further
    # than the limit, and blocked frames never let it restart beyond it (review R-1)
    v = 21.
    lim, step = self._lim(v), self._step(v)
    self._start(0, v)
    target = wheel = 0
    for _ in range(300):
      target += step - 1
      if self._tx(self._angle_msg(target)):
        wheel = target
      else:
        target = wheel
      self._set_meas(wheel)
    self.assertLessEqual(wheel, lim)
    self.assertGreater(wheel, lim - step)

  def test_stale_or_invalid_measured_angle(self):
    self._start(100)
    self.safety.set_timer(1_000_000 + 50_000)
    self.assertTrue(self._tx(self._angle_msg(100)))
    self.safety.set_timer(1_000_000 + 50_001)
    self.assertFalse(self._tx(self._angle_msg(100)))
    self.assertTrue(self._tx(self._angle_msg(0, False, False)))
    # a 0x14A with a bad checksum fails its RX check: it neither refreshes nor moves the measured angle
    self._set_meas(500, checksum_ok=False)
    self.safety.set_controls_allowed(True)
    self.assertFalse(self._tx(self._angle_msg(500)))
    self._set_meas(500)
    self.safety.set_controls_allowed(True)
    self.assertTrue(self._tx(self._angle_msg(0, False, False)))
    self.assertTrue(self._tx(self._angle_msg(500)))

  def test_sender_at_its_clamp_passes(self):
    # openpilot's own sender asked for more than its clamp, in both EPS profiles (mode 3 = amax_scale 1.0, mode 4 =
    # 0.75), with the wheel at the last target: panda must pass every frame
    from opendbc.car.honda import clarity_angle_mode as cam
    for v in (3., 10., 15., 20., 30., 40.):
      for scale, byte3 in ((1.0, 0x07), (cam.AMAX_CAP3_SCALE, 0x09)):
        for sign in (1., -1.):
          self._start(0, v)
          sender, meas = cam.AngleModeSender(), 0
          desired = sign * 1.2 * cam.std_angle_limit(v)   # op degrees; raw = -10 x deg
          for i in range(600):
            raw, req, pay = sender.update(True, desired, -meas / 10., v, True, 0.0, cam.ENGAGE_S, scale)
            values = {"STEER_TORQUE": raw, "STEER_TORQUE_REQUEST": req, "SET_ME_X00": pay, "SET_ME_X00_2": byte3}
            self.assertTrue(self._tx(self.packer.make_can_msg_safety("STEERING_CONTROL", self.STEER_BUS, values)), (v, scale, i, raw))
            meas = raw
            self._set_meas(meas)
          self.assertGreater(abs(raw), 0.98 * cam.angle_limit(v, scale) * 10, (v, scale))   # it reached the clamp

  def test_sender_through_an_override_passes(self):
    # hold through override: the request stays up with no authority (cut 15) and the target stays on the plan while the
    # driver turns the wheel away at 350 deg/s; those are ordinary frames, so panda passes every one, also at the release
    from opendbc.car.honda import clarity_angle_mode as cam
    for v in (2.2, 10., 20.):
      self._start(0, v)
      sender, wheel, plan = cam.AngleModeSender(), 0., 0.5 * cam.angle_limit(v)
      for i in range(600):
        pressed = 100 <= i < 400
        wheel = min(wheel + 3.5, 450.) if pressed else wheel + 0.2 * (-wheel)   # driver turns away, then lets go
        self._set_meas(int(-10 * wheel))
        raw, req, pay = sender.update(True, plan, wheel, v, True, 0., 0.)
        values = {"STEER_TORQUE": raw, "STEER_TORQUE_REQUEST": req, "SET_ME_X00": pay,
                  "SET_ME_X00_2": ((15 if pressed else 0) << 4) | 0x09}
        self.assertTrue(self._tx(self.packer.make_can_msg_safety("STEERING_CONTROL", self.STEER_BUS, values)), (v, i, raw))
        if i > 200:
          self.assertAlmostEqual(raw / -10., plan, delta=0.06)   # on the plan through the press and the release

  def test_first_target_window_is_the_recent_wheel_samples(self):
    # from the wheel = within one step of any of the last 6 0x14A samples (the standard's inactive check window)
    v = 21.
    step = self._step(v)
    self._start(0, v)
    for meas in (0, 30, 60, 90, 120, 150):      # wheel moving 3 deg per sample
      self._rx(self.packer.make_can_msg_safety("STEERING_SENSORS", self.PT_BUS, {"STEER_ANGLE": -meas / 10.}))
    for target, ok in ((-step, True), (150 + step, True), (75, True), (-step - 1, False), (150 + step + 1, False)):
      self.assertTrue(self._tx(self._angle_msg(0, False, False)))
      self.assertEqual(self._tx(self._angle_msg(target)), ok, target)

  def test_sender_engage_with_the_wheel_moving(self):
    # review Q-1: the request rises while the wheel is turning; openpilot sees the angle 1-2 frames late (carState is
    # 10-20 ms older than the newest 0x14A). After 0.3 s the wheel follows what passes. Every frame must pass.
    from opendbc.car.honda import clarity_angle_mode as cam
    for v in (10., 20., 30.):
      for rate in (20., 60.):
        for lag in (1, 2):
          self._start(0, v)
          sender, hist, wheel = cam.AngleModeSender(), [0.] * 3, 0.
          for i in range(130):
            if i < 30:
              wheel += rate * 0.01
            hist = [wheel] + hist[:2]
            # one 0x14A per 10 ms frame, as on the car
            self._rx(self.packer.make_can_msg_safety("STEERING_SENSORS", self.PT_BUS, {"STEER_ANGLE": -round(10 * wheel) / 10.}))
            raw, req, pay = sender.update(True, 0., hist[lag], v, True, rate if i < 30 else 0., 0.)
            values = {"STEER_TORQUE": raw, "STEER_TORQUE_REQUEST": req, "SET_ME_X00": pay, "SET_ME_X00_2": 0x09}
            self.assertTrue(self._tx(self.packer.make_can_msg_safety("STEERING_CONTROL", self.STEER_BUS, values)), (v, rate, lag, i))
            if i >= 30:
              wheel = raw / -10.

  def test_sender_waits_for_the_wheel_inside_the_limit(self):
    # review Q-2: engaging in a tight turn with the wheel beyond the 3.6 m/s^2 angle: openpilot holds the request
    # down (all-zero frames, which pass) until the wheel comes inside, then engages at the wheel
    from opendbc.car.honda import clarity_angle_mode as cam
    for v, start in ((8., 180.), (7., 230.), (12., 80.)):
      lim = cam.std_angle_limit(v)
      self.assertGreater(start, lim)
      self._start(0, v)
      sender, wheel, engaged = cam.AngleModeSender(), start, False
      for i in range(400):
        wheel = max(wheel - 0.5, 0.5 * lim)     # the driver unwinds at 50 deg/s
        self._set_meas(int(-10 * wheel))
        raw, req, pay = sender.update(True, 0.5 * lim, wheel, v, True, -50., 0.)
        values = {"STEER_TORQUE": raw, "STEER_TORQUE_REQUEST": req, "SET_ME_X00": pay, "SET_ME_X00_2": 0x09}
        self.assertTrue(self._tx(self.packer.make_can_msg_safety("STEERING_CONTROL", self.STEER_BUS, values)), (v, i, wheel, raw))
        if req:
          self.assertLessEqual(abs(raw) / 10., lim + 0.06)
        else:
          self.assertGreater(wheel, lim)
        engaged = engaged or req
      self.assertTrue(engaged)

  def test_no_measured_angle_after_init(self):
    self.safety.set_timer(1_000_000)
    self.safety.set_controls_allowed(True)
    self._set_speed(10.)
    self.assertFalse(self._tx(self._angle_msg(0)))


class TestHondaNidecPcmAltSafety(TestHondaNidecPcmSafety):
  """
    Covers the Honda Nidec safety mode with alt SCM messages
  """
  DBC = "acura_ilx_2016_can_generated"

  SAFETY_PARAM = HondaSafetyFlags.NIDEC_ALT

  def _acc_state_msg(self, main_on):
    values = {"MAIN_ON": main_on}
    return self.packer.make_can_msg_safety("SCM_BUTTONS", self.PT_BUS, values)

  def _button_msg(self, buttons, main_on=False, bus=None):
    bus = self.PT_BUS if bus is None else bus
    values = {"CRUISE_BUTTONS": buttons, "MAIN_ON": main_on}
    return self.packer.make_can_msg_safety("SCM_BUTTONS", bus, values)


# ********************* Honda Bosch **********************


class TestHondaBoschSafetyBase(HondaBase):
  DBC = "honda_civic_hatchback_ex_2017_can_generated"
  SAFETY_MODEL = CarParams.SafetyModel.hondaBosch

  PT_BUS = 1
  STEER_BUS = 0
  BUTTONS_BUS = 1

  TX_MSGS = [[0xE4, 0], [0xE5, 0], [0x296, 1], [0x33D, 0], [0x33DA, 0], [0x33DB, 0]]
  FWD_BLACKLISTED_ADDRS = {2: [0xE4, 0xE5, 0x33D, 0x33DA, 0x33DB]}
  RELAY_MALFUNCTION_ADDRS = {0: (0xE4, 0xE5, 0x33D, 0x33DA, 0x33DB)}  # STEERING_CONTROL, BOSCH_SUPPLEMENTAL_1

  def _alt_brake_msg(self, brake):
    values = {"BRAKE_PRESSED": brake}
    return self.packer.make_can_msg_safety("BRAKE_MODULE", self.PT_BUS, values)

  def _send_brake_msg(self, brake):
    pass

  def test_spam_cancel_safety_check(self):
    self.safety.set_controls_allowed(0)
    self.assertTrue(self._tx(self._button_msg(Btn.CANCEL, bus=self.BUTTONS_BUS)))
    self.assertFalse(self._tx(self._button_msg(Btn.RESUME, bus=self.BUTTONS_BUS)))
    self.assertFalse(self._tx(self._button_msg(Btn.SET, bus=self.BUTTONS_BUS)))
    # do not block resume if we are engaged already
    self.safety.set_controls_allowed(1)
    self.assertTrue(self._tx(self._button_msg(Btn.RESUME, bus=self.BUTTONS_BUS)))


class TestHondaBoschAltBrakeSafetyBase(TestHondaBoschSafetyBase):
  """
    Base Bosch safety test class with an alternate brake message
  """
  SAFETY_PARAM = HondaSafetyFlags.ALT_BRAKE

  def _user_brake_msg(self, brake):
    return self._alt_brake_msg(brake)

  def test_alt_brake_rx_hook(self):
    self.safety.set_honda_alt_brake_msg(1)
    self.safety.set_controls_allowed(1)
    msg = self._alt_brake_msg(0)
    self.assertTrue(self._rx(msg))
    msg[0].data[2] = msg[0].data[2] & 0xF0  # invalidate checksum
    self.assertFalse(self._rx(msg))
    self.assertFalse(self.safety.get_controls_allowed())

  def test_alt_disengage_on_brake(self):
    self.safety.set_honda_alt_brake_msg(1)
    self.safety.set_controls_allowed(1)
    self._rx(self._alt_brake_msg(1))
    self.assertFalse(self.safety.get_controls_allowed())

    self.safety.set_honda_alt_brake_msg(0)
    self.safety.set_controls_allowed(1)
    self._rx(self._alt_brake_msg(1))
    self.assertTrue(self.safety.get_controls_allowed())


class TestHondaBoschSafety(HondaPcmEnableBase, TestHondaBoschSafetyBase):
  """
    Covers the Honda Bosch safety mode with stock longitudinal
  """


class TestHondaBoschAltBrakeSafety(HondaPcmEnableBase, TestHondaBoschAltBrakeSafetyBase):
  """
    Covers the Honda Bosch safety mode with stock longitudinal and an alternate brake message
  """


class TestHondaBoschLongSafety(HondaButtonEnableBase, TestHondaBoschSafetyBase):
  """
    Covers the Honda Bosch safety mode with longitudinal control
  """
  SAFETY_PARAM = HondaSafetyFlags.BOSCH_LONG

  NO_GAS = -30000
  MAX_GAS = 2000
  MAX_ACCEL = 2.0  # accel is used for brakes, but openpilot can set positive values
  MIN_ACCEL = -3.5

  STEER_BUS = 1
  TX_MSGS = [[0xE4, 1], [0x1DF, 1], [0x1EF, 1], [0x1FA, 1], [0x30C, 1], [0x33D, 1], [0x33DA, 1], [0x33DB, 1], [0x39F, 1], [0x18DAB0F1, 1]]
  FWD_BLACKLISTED_ADDRS = {}
  # 0x1DF is to test that radar is disabled
  RELAY_MALFUNCTION_ADDRS = {1: (0xE4, 0x1DF, 0x33D, 0x33DA, 0x33DB)}  # STEERING_CONTROL, ACC_CONTROL

  def _send_gas_brake_msg(self, gas, accel):
    values = {
      "GAS_COMMAND": gas,
      "ACCEL_COMMAND": accel,
      "BRAKE_REQUEST": accel < 0,
    }
    return self.packer.make_can_msg_safety("ACC_CONTROL", self.PT_BUS, values)

  # Longitudinal doesn't need to send buttons
  def test_spam_cancel_safety_check(self):
    pass

  def test_diagnostics(self):
    tester_present = libsafety_py.make_CANPacket(0x18DAB0F1, self.PT_BUS, b"\x02\x3E\x80\x00\x00\x00\x00\x00")
    self.assertTrue(self._tx(tester_present))

    not_tester_present = libsafety_py.make_CANPacket(0x18DAB0F1, self.PT_BUS, b"\x03\xAA\xAA\x00\x00\x00\x00\x00")
    self.assertFalse(self._tx(not_tester_present))

  def test_gas_safety_check(self):
    for controls_allowed in [True, False]:
      for gas in np.arange(self.NO_GAS, self.MAX_GAS + 2000, 100):
        accel = 0 if gas < 0 else gas / 1000
        self.safety.set_controls_allowed(controls_allowed)
        send = (controls_allowed and 0 <= gas <= self.MAX_GAS) or gas == self.NO_GAS
        self.assertEqual(send, self._tx(self._send_gas_brake_msg(gas, accel)), (controls_allowed, gas, accel))

  def test_brake_safety_check(self):
    for controls_allowed in [True, False]:
      for accel in np.arange(self.MIN_ACCEL - 1, self.MAX_ACCEL + 1, 0.01):
        accel = round(accel, 2)  # floats might not hit exact boundary conditions without rounding
        self.safety.set_controls_allowed(controls_allowed)
        send = self.MIN_ACCEL <= accel <= self.MAX_ACCEL if controls_allowed else accel == 0
        self.assertEqual(send, self._tx(self._send_gas_brake_msg(self.NO_GAS, accel)), (controls_allowed, accel))

  def test_block_aeb(self):
    for controls_allowed in [True, False]:
      self.safety.set_controls_allowed(controls_allowed)
      for aeb_signals in ({"AEB_STATUS": 1}, {"AEB_PREPARE": 1}, {"AEB_BRAKING": 1}):
        values = {"GAS_COMMAND": self.NO_GAS, "ACCEL_COMMAND": 0, **aeb_signals}
        msg = self.packer.make_can_msg_safety("ACC_CONTROL", self.PT_BUS, values)
        self.assertFalse(self._tx(msg), msg=aeb_signals)
      self.assertTrue(self._tx(self._send_gas_brake_msg(self.NO_GAS, 0)))


class TestHondaBoschRadarlessSafetyBase(TestHondaBoschSafetyBase):
  """Base class for radarless Honda Bosch"""
  DBC = "honda_bosch_radarless_generated"

  PT_BUS = 0
  STEER_BUS = 0
  BUTTONS_BUS = 2  # camera controls ACC, need to send buttons on bus 2

  TX_MSGS = [[0xE4, 0], [0x296, 2], [0x33D, 0]]
  FWD_BLACKLISTED_ADDRS = {2: [0xE4, 0x33D]}
  RELAY_MALFUNCTION_ADDRS = {0: (0xE4, 0x33D)}  # STEERING_CONTROL


class TestHondaBoschRadarlessSafety(HondaPcmEnableBase, TestHondaBoschRadarlessSafetyBase):
  """
    Covers the Honda Bosch Radarless safety mode with stock longitudinal
  """
  SAFETY_PARAM = HondaSafetyFlags.RADARLESS


class TestHondaBoschRadarlessAltBrakeSafety(HondaPcmEnableBase, TestHondaBoschRadarlessSafetyBase, TestHondaBoschAltBrakeSafetyBase):
  """
    Covers the Honda Bosch Radarless safety mode with stock longitudinal and an alternate brake message
  """
  SAFETY_PARAM = HondaSafetyFlags.RADARLESS | HondaSafetyFlags.ALT_BRAKE


class TestHondaBoschRadarlessLongSafety(common.LongitudinalAccelSafetyTest, HondaButtonEnableBase,
                                        TestHondaBoschRadarlessSafetyBase):
  """
    Covers the Honda Bosch Radarless safety mode with longitudinal control
  """
  SAFETY_PARAM = HondaSafetyFlags.RADARLESS | HondaSafetyFlags.BOSCH_LONG

  TX_MSGS = [[0xE4, 0], [0x33D, 0], [0x1C8, 0], [0x30C, 0]]
  FWD_BLACKLISTED_ADDRS = {2: [0xE4, 0x33D, 0x1C8, 0x30C]}
  RELAY_MALFUNCTION_ADDRS = {0: (0xE4, 0x1C8, 0x30C, 0x33D)}

  def _accel_msg(self, accel):
    values = {
      "ACCEL_COMMAND": accel,
    }
    return self.packer.make_can_msg_safety("ACC_CONTROL", self.PT_BUS, values)

  def test_block_aeb(self):
    for controls_allowed in [True, False]:
      self.safety.set_controls_allowed(controls_allowed)
      for aeb_signals in ({"AEB_STATUS": 1}, {"AEB_PREPARE": 1}, {"AEB_BRAKING": 1}):
        values = {"ACCEL_COMMAND": 0, **aeb_signals}
        msg = self.packer.make_can_msg_safety("ACC_CONTROL", self.PT_BUS, values)
        self.assertFalse(self._tx(msg), msg=aeb_signals)
      self.assertTrue(self._tx(self._accel_msg(0)))

  # Longitudinal doesn't need to send buttons
  def test_spam_cancel_safety_check(self):
    pass


class TestHondaBoschCANFDSafetyBase(TestHondaBoschSafetyBase):
  """Base class for CANFD Honda Bosch"""
  DBC = "honda_common_canfd_generated"

  PT_BUS = 0
  STEER_BUS = 0
  BUTTONS_BUS = 0

  TX_MSGS = [[0xE4, 0], [0x296, 0], [0x33D, 0]]
  FWD_BLACKLISTED_ADDRS = {2: [0xE4, 0x33D]}
  RELAY_MALFUNCTION_ADDRS = {0: (0xE4, 0x33D)}


class TestHondaBoschCANFDSafety(HondaPcmEnableBase, TestHondaBoschCANFDSafetyBase):
  """
    Covers the Honda Bosch CANFD safety mode with stock longitudinal
  """
  SAFETY_PARAM = HondaSafetyFlags.BOSCH_CANFD


class TestHondaBoschCANFDAltBrakeSafety(HondaPcmEnableBase, TestHondaBoschCANFDSafetyBase, TestHondaBoschAltBrakeSafetyBase):
  """
    Covers the Honda Bosch CANFD safety mode with stock longitudinal and an alternate brake message
  """
  SAFETY_PARAM = HondaSafetyFlags.BOSCH_CANFD | HondaSafetyFlags.ALT_BRAKE


class TestHondaBoschAolAxisSafety(unittest.TestCase):
  """Exact classic-CAN Bosch-long opt-in keeps native axes independent."""

  def setUp(self):
    self.fixture = TestHondaBoschLongSafety('test_diagnostics')
    self.fixture.setUp()
    self.safety = self.fixture.safety
    self.safety.set_safety_hooks(CarParams.SafetyModel.hondaBosch,
                                 HondaSafetyFlags.BOSCH_LONG | HondaSafetyFlags.AOL_BOSCH_LONG)
    self.safety.init_tests()
    self.safety.set_timer(1_000_000)
    self.fixture._rx(self.fixture._acc_state_msg(True))
    self.safety.set_aol_test_heartbeat(True)

  def _all_checked_rx(self):
    self.fixture._rx(self.fixture._acc_state_msg(True))
    self.fixture._rx(self.fixture._button_msg(Btn.NONE))
    self.fixture._rx(self.fixture._speed_msg(20))
    self.fixture._rx(self.fixture._powertrain_data_msg())

  def test_request_and_native_ack_are_separate(self):
    self.assertEqual(self.safety.aol_get_permission_mask(), 0)
    self.safety.aol_set_host_request(1)
    self.assertEqual(self.safety.aol_get_permission_mask(), 0)  # main alone is not complete RX health
    self._all_checked_rx()
    self.assertEqual(self.safety.aol_get_permission_mask(), 1)
    self.assertTrue(self.fixture._tx(self.fixture._send_steer_msg(0x100)))
    self.assertFalse(self.fixture._tx(self.fixture._send_gas_brake_msg(0, 1.0)))

    self.safety.set_controls_allowed(True)
    self.safety.aol_set_host_request(2)
    self.assertEqual(self.safety.aol_get_permission_mask(), 2)
    self.assertFalse(self.fixture._tx(self.fixture._send_steer_msg(0x100)))
    self.assertTrue(self.fixture._tx(self.fixture._send_gas_brake_msg(0, 1.0)))

    self.safety.aol_set_host_request(3)
    self.assertEqual(self.safety.aol_get_permission_mask(), 3)
    self.safety.aol_set_host_request(0)
    self.assertEqual(self.safety.aol_get_permission_mask(), 0)

  def test_timeout_main_cancel_and_heartbeat_fail_closed(self):
    self._all_checked_rx()
    self.safety.aol_set_host_request(3)
    self.safety.set_controls_allowed(True)
    self.safety.set_timer(1_300_001)
    self.assertEqual(self.safety.aol_get_permission_mask(), 0)
    self.safety.set_timer(1_400_000)
    self._all_checked_rx()
    self.safety.aol_set_host_request(3)
    self.assertEqual(self.safety.aol_get_permission_mask(), 3)
    self.fixture._rx(self.fixture._button_msg(Btn.CANCEL))
    self.assertEqual(self.safety.aol_get_permission_mask(), 0)
    self.safety.aol_set_host_request(1)
    self.safety.set_aol_test_heartbeat(False)
    self.assertEqual(self.safety.aol_get_permission_mask(), 0)

  def test_unsupported_honda_variants_never_get_aol_grant(self):
    self.safety.set_safety_hooks(CarParams.SafetyModel.hondaBosch,
                                 HondaSafetyFlags.BOSCH_LONG | HondaSafetyFlags.RADARLESS | HondaSafetyFlags.AOL_BOSCH_LONG)
    self.safety.init_tests()
    self.safety.set_aol_test_heartbeat(True)
    self.safety.aol_set_host_request(3)
    self.assertEqual(self.safety.aol_get_permission_mask(), 0)


if __name__ == "__main__":
  unittest.main()
