import math
import numpy as np

from opendbc.can import CANPacker
from opendbc.car import Bus, DT_CTRL, rate_limit, make_tester_present_msg, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.honda import hondacan
from opendbc.car.honda.angle_profiles import angle_profile
from opendbc.car.honda.clarity_angle_mode import HOLD_LIMITS_FADE_S, AngleModeSender, AuthorityRamp, angle_mode, stock_arm_bits, \
  stock_arm_bits_supported
from opendbc.car.honda.meps import protocol as meps_protocol
from opendbc.car.honda.accord_mvl_stock import AccordMvlStock, qualified as mvl_stock_qualified
from opendbc.car.honda.bcan_blinker import BcanBlinker
from opendbc.car.honda.modified_eps import ModifiedEpsSteering, below_min_steer_speed, current_settings, get_eps_modified_steering_pressed, modified_eps  # noqa: F401
from opendbc.car.honda.nidec_interceptor import NidecInterceptor, create_command, qualified as interceptor_qualified
from opendbc.car.honda.bosch_longitudinal import BoschLongitudinal, qualified as bosch_long_qualified
from opendbc.car.honda import pcm_acc
from opendbc.car.honda.values import CAR, CruiseButtons, HondaFlags, CarControllerParams
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.lateral import apply_steer_angle_limits_vm
from opendbc.car.vehicle_model import VehicleModel

VisualAlert = structs.CarControl.HUDControl.VisualAlert
LongCtrlState = structs.CarControl.Actuators.LongControlState
SteerControlType = structs.CarParams.SteerControlType


def compute_gb_honda_bosch(accel, speed):
  # TODO returns 0s, is unused
  return 0.0, 0.0


def compute_gb_honda_nidec(accel, speed):
  creep_brake = 0.0
  creep_speed = 2.3
  creep_brake_value = 0.15
  if speed < creep_speed:
    creep_brake = (creep_speed - speed) / creep_speed * creep_brake_value
  gb = float(accel) / 4.8 - creep_brake
  return np.clip(gb, 0.0, 1.0), np.clip(-gb, 0.0, 1.0)


# A Nidec hybrid's COMPUTER_BRAKE_HYBRID reaches 320, the stock ACC camera's own ceiling (00000042--6d427003af segs
# 5/10). Under the Nidec 255 the Clarity's hardest braking was ~-2.7 m/s2, mostly regen, against a -3.5 plan
# (00000047--ac3b1f5def seg 6, the driver finished the stop at -6 to -9).
# The command is the inverse of the Clarity's measured brake curve (aEgo 0.15 s after the command, openpilot braking
# alone, 00000042/43/47): regen alone and linear to ~52, a knee where regen saturates (~10k on 0x183) and friction
# starts, then friction carries the rest. Decel = -1.24e-4*regen - 1.47*pressure - 0.34 explains 93% of it; the top
# knot (320 <-> 3.3 m/s2) is that fit extrapolated (3.3-3.8 by speed), placed so -4.0 less wind_brake reaches the
# ceiling up to ~75 mph.
# The brake fraction (accel / 4.8, after wind_brake) is read as the brake's share of the decel in m/s2.
HYBRID_DECEL_BP = [0.0, 0.3, 0.7, 1.0, 1.27, 1.5, 1.7, 1.85, 2.2, 2.55, 2.7, 3.3]
HYBRID_COMMAND_V = [0.0, 8.0, 22.0, 38.0, 52.0, 95.0, 112.0, 130.0, 150.0, 170.0, 200.0, 320.0]
HYBRID_BRAKE_MAX = 320


def hybrid_brake_command(brake_fraction: float, v_ego: float = 10.0) -> int:
  measured = float(np.interp(brake_fraction * 4.8, HYBRID_DECEL_BP, HYBRID_COMMAND_V))
  # The curve was measured at 5-35 mph. Below ~3 mph regen fades out and the brake is all friction, so the road-tested
  # linear command (fraction * 256, the final-stop and hold behavior of 00000039/3a/3b) stays a floor, fading by ~7 mph.
  linear_floor = brake_fraction * 256.0 * float(np.interp(v_ego, [1.3, 3.0], [1.0, 0.0]))
  return int(np.clip(max(measured, linear_floor), 0, HYBRID_BRAKE_MAX))


def compute_gas_brake(accel, speed, CP):
  if CP.flags & HondaFlags.BOSCH:
    return compute_gb_honda_bosch(accel, speed)
  else:
    return compute_gb_honda_nidec(accel, speed)


# TODO not clear this does anything useful
def actuator_hysteresis(brake, braking, brake_steady):
  # hyst params
  brake_hyst_on = 0.02    # to activate brakes exceed this value
  brake_hyst_off = 0.005  # to deactivate brakes below this value
  brake_hyst_gap = 0.01   # don't change brake command for small oscillations within this value

  # *** hysteresis logic to avoid brake blinking. go above 0.1 to trigger
  if (brake < brake_hyst_on and not braking) or brake < brake_hyst_off:
    brake = 0.
  braking = brake > 0.

  # for small brake oscillations within brake_hyst_gap, don't change the brake command
  if brake == 0.:
    brake_steady = 0.
  elif brake > brake_steady + brake_hyst_gap:
    brake_steady = brake - brake_hyst_gap
  elif brake < brake_steady - brake_hyst_gap:
    brake_steady = brake + brake_hyst_gap
  brake = brake_steady

  return brake, braking, brake_steady


def brake_pump_hysteresis(apply_brake, apply_brake_last, last_pump_ts, ts):
  pump_on = False

  # reset pump timer if:
  # - there is an increment in brake request
  # - we are applying steady state brakes and we haven't been running the pump
  #   for more than 20s (to prevent pressure bleeding)
  if apply_brake > apply_brake_last or (ts - last_pump_ts > 20. and apply_brake > 0):
    last_pump_ts = ts

  # once the pump is on, run it for at least 0.2s
  if ts - last_pump_ts < 0.2 and apply_brake > 0:
    pump_on = True

  return pump_on, last_pump_ts


def process_hud_alert(hud_alert):
  alert_fcw = False
  alert_steer_required = False

  # Make sure FCW is prioritized over steering required
  # TODO: implement separate available LDW alert
  if hud_alert == VisualAlert.fcw:
    alert_fcw = True
  elif hud_alert in (VisualAlert.steerRequired, VisualAlert.ldw):
    alert_steer_required = True

  return alert_fcw, alert_steer_required


class CarController(CarControllerBase):
  def __init__(self, dbc_names, CP):
    super().__init__(dbc_names, CP)
    self.packer = CANPacker(dbc_names[Bus.pt])
    self.params = CarControllerParams(CP)
    self.CAN = hondacan.CanBus(CP)
    self.bosch_longitudinal = BoschLongitudinal(CP, self.params) if bosch_long_qualified(CP) else None
    self.bosch_learning_params = None
    self.nidec_interceptor = NidecInterceptor(CP) if interceptor_qualified(CP) else None
    self.interceptor_learning_params = None
    self.accord_mvl_stock = AccordMvlStock() if mvl_stock_qualified(CP) else None
    # B-CAN turn signals (body harness with B-CAN gateway): the BCM holds the lamp for the
    # lane change and cancels it after. The toggle is attached from openpilot (bcan_blinker_settings)
    self.bcan_blinker = BcanBlinker() if CP.flags & HondaFlags.HAS_BSM else None
    self.bcan_blinker_settings = None
    self.tja_control = bool(CP.flags & HondaFlags.BOSCH_TJA_CONTROL)
    # every modified-EPS Honda steers through ModifiedEpsSteering (override detector and fade, minimum steer
    # speed, opt-in rate limit). It replaces 7.0's Civic Bosch-only ModifiedCivicSteering, whose torque low-pass here
    # read as safety limiting in controlsd and froze the lateral integrator. openpilot attaches modified_eps_settings.
    self.modified_eps_steering = ModifiedEpsSteering() if modified_eps(CP) else None
    # 0xE4 byte 3: 0 (stock / CleanPTM firmware ignore it; a v2 EPS reads MODE 0 = stock). Clarity angle mode (protocol
    # v2, build 0x0B on): AUTH << 4 | MODE 1 on every frame and the angle target in bytes 0-1, gated on 0x6A4
    self.eps_mode = 0
    # a profile car (angle_profiles.py): linear from the start, the sender's limits from panda's row for it
    self.angle_sender = AngleModeSender(angle_profile(CP)) if angle_mode(CP) else None
    self.stock_arm = stock_arm_bits_supported(CP)   # the stock byte 2 arm field is traced on the Clarity only
    if self.angle_sender is not None:
      self.eps_mode = meps_protocol.byte3_v2(0)
    self.apply_angle_raw = 0
    self.authority = AuthorityRamp()   # angle-loop authority (byte 3 bits 7:4, AUTH)
    self.angle_cut = 0
    self.angle_hold = False   # authority hold active this frame (target limits at HOLD_LIMITS_FADE_S)
    self.angle_arm_bits = 0   # 0xE4 byte 2 stock arm bits with the hold (clarity_angle_mode.stock_arm_bits)
    self.modified_eps_settings = None
    # Clarity with an interceptor: the PCM stays in ACC while openpilot is engaged (honda/pcm_acc.py)
    self.keep_pcm_acc = pcm_acc.qualified(CP)
    self.standstill_hold = pcm_acc.StandstillHold()

    self.braking = False
    self.brake_steady = 0.
    self.brake_last = 0.
    self.apply_brake_last = 0
    self.last_pump_ts = 0.
    self.stopping_counter = 0

    self.accel = 0.0
    self.speed = 0.0
    self.gas = 0.0
    self.brake = 0.0
    self.last_torque = 0.0
    # frames the driver has been turning the wheel (+) or let go (-), for the cluster lanes
    self.override_frames = 0

    # Accord angle-loop EPS (interface.py sets steerControlType = angle)
    # (the Clarity / angle-profile angle mode also steers by angle, through its own sender self.angle_sender; this path is
    # keyed on the Accord firmware flag so the two never mix)
    self.angle_mode = CP.steerControlType == SteerControlType.angle and bool(CP.flags & HondaFlags.EPS_ANGLE_LOOP_FW)
    self.VM = VehicleModel(CP) if self.angle_mode else None
    self.apply_angle_last = None  # None until the first frame seeds the limiter from the wheel

  def _update_angle(self, CC, CS) -> tuple[float, int]:
    """Angle setpoint (deg) and the 0xE4 STEER_TORQUE field."""
    p = self.params
    steering_angle = float(CS.out.steeringAngleDeg)
    angle_last = steering_angle if self.apply_angle_last is None else self.apply_angle_last
    self.apply_angle_last = apply_steer_angle_limits_vm(CC.actuators.steeringAngleDeg, angle_last, CS.out.vEgoRaw,
                                                        steering_angle, CC.latActive, p, self.VM)
    if not CC.latActive:
      # the frame carries no setpoint while idle (the panda would drop a nonzero one): the field is 0
      return self.apply_angle_last, 0
    # error clip: a pure bound on what is sent, never stored back into the limiter state (a clipped value re-seeding
    # the limiter would feed the wheel's motion into the next frame's setpoint)
    error_max = float(np.interp(CS.out.vEgoRaw, p.ANGLE_ERROR_MAX_BP, p.ANGLE_ERROR_MAX_V))
    apply_angle = float(np.clip(self.apply_angle_last, steering_angle - error_max, steering_angle + error_max))
    # around a wheel past the setpoint limit the error clip lies outside it: the limit wins, and is what gets reported
    apply_angle = float(np.clip(apply_angle, -p.ANGLE_LIMITS.STEER_ANGLE_MAX, p.ANGLE_LIMITS.STEER_ANGLE_MAX))
    # raw = round(-10 * deg), half-up; left-positive degrees are negative raw
    return apply_angle, math.floor(-10.0 * apply_angle + 0.5)

  def update(self, CC, CS, now_nanos):
    _projection = self.learning_projection_observer
    if _projection is not None:
      _projection.begin(CC.actuators.torque, self.frame)
    actuators = CC.actuators
    hud_control = CC.hudControl
    hud_v_cruise = hud_control.setSpeed / CS.v_cruise_factor if hud_control.speedVisible else 255
    if hud_control.speedVisible and not CS.dynamic_v_cruise_units and not CS.is_metric:
      # Imperial cluster reads whole kph on Honda's 1.6 kph-per-mph grid. Exact 50 mph
      # (80.47 kph) rounded to 81 and showed 51 (route 0000008f--1effd6e0ad, 2026-11-05).
      hud_v_cruise = round(hud_control.setSpeed * CV.MS_TO_MPH) * 1.6
    pcm_cancel_cmd = CC.cruiseControl.cancel
    if self.keep_pcm_acc:
      # carstate hides the PCM's ACC from openpilot in this mode, so the cancel on disengage is sent from here
      pcm_cancel_cmd = CS.pcm_acc_active and not CC.enabled
    if self.bosch_longitudinal is not None:
      self.bosch_longitudinal.observe_orientation(CC.orientationNED)

    if CC.longActive:
      accel = actuators.accel
      gas, brake = compute_gas_brake(actuators.accel, CS.out.vEgo, self.CP)
      if self.keep_pcm_acc:
        brake = self.standstill_hold.update(brake, CS.out.standstill, actuators.longControlState == LongCtrlState.stopping)
    else:
      accel = 0.0
      gas, brake = 0.0, 0.0
      self.standstill_hold.latched = False

    # *** rate limit steer ***
    if _projection is not None:
      _projection.capture_honda(None, CS)
    torque_cmd = actuators.torque
    # angle mode: the EPS runs MODE 1 (0x6A4) and, on a linear-angle EPS, its 0x6A2 is fresh (panda's measured angle)
    angle_ready = (self.angle_sender is not None and CS.eps_cal_status.angle_ready and CS.linear_angle.steer_ok)
    if self.angle_mode:
      # Accord angle-loop EPS: the angle setpoint takes the place of the torque command in the 0xE4 STEER_TORQUE field
      apply_angle, apply_torque = self._update_angle(CC, CS)
      limited_torque, lkas_active = 0.0, CC.latActive
    elif self.modified_eps_steering is not None:
      limited_torque, lkas_active, meps_pressed = self.modified_eps_steering.update(CC, CS, current_settings(self.modified_eps_settings))
      angle_hold = (self.angle_sender is not None and CS.eps_cal_status.authority_ready and
                    current_settings(self.modified_eps_settings).angle_hold_override)
      if angle_hold:
        # Angle Hold Through Override (default on): the request stays up through an override.
        # While the driver yields (the press detector OR the torque-mode yield) the loop's authority drops to 0 at once,
        # which keeps the command under the stock lockout's threshold. The sent target stays on openpilot's plan through
        # the override (Hyundai/Kia style; the model assumes its desired curvature is carried out while latActive, so a
        # target that follows the wheel and walks back after the release misleads it): at the release only authority
        # changes, back over Override Fade Up, the setting being the time (0 = at once; the firmware's own slew takes 0 ->
        # full in 0.34 s). Route 000000ed: the 17-frame fade pulled the wheel toward center under the driver's hands.
        mset = current_settings(self.modified_eps_settings)
        yielding = bool(meps_pressed or CS.out.steeringPressed)
        lkas_active = bool(CC.latActive and not below_min_steer_speed(CS.out.vEgo, mset.min_steer_speed_mph))
        cut = self.authority.update(lkas_active and angle_ready, yielding, mset.fade_up_s)
        self.angle_cut = cut if lkas_active else 0   # no request: byte 3 stays 0xF1 (the loop resets G on activation)
        self.angle_hold = True
        # stock arm 2, abort while yielding: the stock inner loop lets go of the wheel during the press (stock_arm_bits)
        self.angle_arm_bits = stock_arm_bits(self.stock_arm, yielding)
      else:
        self.authority.update(False, False, 0.0)
        self.angle_cut = 0
        self.angle_hold = False
        self.angle_arm_bits = 0
      if self.angle_sender is not None and meps_pressed and not angle_hold:
        # Angle mode: no request during a press, whatever Override Fade Down or Assist During Override say. Both keep the
        # request up through a press, which in torque mode eases torque out; in angle mode it would hold the stiff angle
        # loop against the driver (the emulator's no-yield runs: ~3000 counts against the hands, then EPS lockout).
        lkas_active = False
    else:
      limited_torque = rate_limit(torque_cmd, self.last_torque, -self.params.STEER_DELTA_DOWN * DT_CTRL,
                                  self.params.STEER_DELTA_UP * DT_CTRL)
      lkas_active = CC.latActive
    _projection_previous = self.last_torque if _projection is not None else 0.
    self.last_torque = limited_torque

    # *** apply brake hysteresis ***
    pre_limit_brake, self.braking, self.brake_steady = actuator_hysteresis(brake, self.braking, self.brake_steady)

    # *** rate limit after the enable check ***
    self.brake_last = rate_limit(pre_limit_brake, self.brake_last, -2., DT_CTRL)

    # vehicle hud display, wait for one update from 10Hz 0x304 msg
    alert_fcw, alert_steer_required = process_hud_alert(hud_control.visualAlert)

    # **** process the car messages ****

    # steer torque is converted back to CAN reference (positive when steering right)
    # Preserve integer CAN rounding while steering limits are owned by the platform.
    if not self.angle_mode:
      apply_torque = int(np.interp(-limited_torque * self.params.STEER_MAX,
                                   self.params.STEER_LOOKUP, self.params.STEER_LOOKUP_V))
    if _projection is not None:
      _projection.input(apply_torque, self.params.STEER_MAX, _projection_previous, CS.out.steeringTorque, self.params,
                        limiter='normalized_rate', mapping='honda_lookup', codec_input=torque_cmd,
                        lookup_x=self.params.STEER_LOOKUP, lookup_y=self.params.STEER_LOOKUP_V, limited_input=limited_torque)

    # Send CAN commands
    can_sends = []

    # tester present - w/ no response (keeps radar disabled)
    if self.CP.flags & HondaFlags.BOSCH and not (self.CP.flags & HondaFlags.BOSCH_RADARLESS) and self.CP.openpilotLongitudinalControl:
      if self.frame % 10 == 0:
        can_sends.append(make_tester_present_msg(0x18DAB0F1, 1, suppress_response=True))

    # Send steering command.
    angle_payload = 0
    if self.angle_sender is not None:
      # angle mode replaces the torque: bytes 0-1 carry the target only while the EPS reports MODE 1 (angle_ready).
      # The request follows ModifiedEpsSteering's lkas_active exactly as in torque mode: it drops while the driver
      # overrides (and below the min steer speed), so the stiff angle loop never fights the driver; the next request
      # restarts from the measured angle and rate with the engage fade. Keeping the request up through a press made the loop
      # push ~3000 counts against the driver until the stock EPS locked out (emulator be_16/36/37, 11-18).
      settings = current_settings(self.modified_eps_settings)
      # 0xE4 byte 3 (meps/protocol.py, v2): MODE 1 with AUTH = 15 - CUT (15 = full)
      self.eps_mode = meps_protocol.byte3_v2(self.angle_cut)
      # linear-angle EPS: desired (controls), measured (carState) and the sender's limits are all rack-linear; the EPS and
      # panda take the target in those units, so nothing is converted here
      self.angle_sender.linear = CS.linear_angle.latched or self.angle_sender.profile is not None
      self.apply_angle_raw, lkas_active, angle_payload = self.angle_sender.update(
        lkas_active, actuators.steeringAngleDeg, CS.out.steeringAngleDeg, CS.out.vEgo, angle_ready,
        CS.out.steeringRateDeg, HOLD_LIMITS_FADE_S if self.angle_hold else settings.fade_up_s,   # hold: authority ramp is the fade
        rate_limit_deg_s=settings.angle_rate_limit_deg_s)                                 # Steering Angle Rate Limit
      CS.eps_cal_status.note_angle_request(lkas_active)
      apply_torque = self.apply_angle_raw
    can_sends.append(hondacan.create_steering_control(self.packer, self.CAN, apply_torque, lkas_active, self.tja_control,
                                                      eps_mode=self.eps_mode, angle_payload=angle_payload,
                                                      arm_bits=self.angle_arm_bits if self.angle_sender is not None else 0,
                                                      angle_arm=self.params.ANGLE_ARM if self.angle_mode else None))
    if _projection is not None:
      _projection.emit('honda.STEERING_CONTROL', apply_torque, lkas_active, can_sends[-1])

    # wind brake from air resistance decel at high speed
    wind_brake = np.interp(CS.out.vEgo, [0.0, 2.3, 35.0], [0.001, 0.002, 0.15])
    # all of this is only relevant for HONDA NIDEC
    max_accel = np.interp(CS.out.vEgo, self.params.NIDEC_MAX_ACCEL_BP, self.params.NIDEC_MAX_ACCEL_V)
    # TODO this 1.44 is just to maintain previous behavior
    pcm_speed_BP = [-wind_brake,
                    -wind_brake * (3 / 4),
                    0.0,
                    0.5]
    # The Honda ODYSSEY seems to have different PCM_ACCEL
    # msgs, is it other cars too?
    if self.nidec_interceptor is not None or not CC.longActive:
      pcm_speed = 0.0
      pcm_accel = int(0.0)
      if self.keep_pcm_acc and CC.longActive:
        pcm_accel = pcm_acc.hud_gas(CS.out.vEgo)
    elif self.CP.flags & HondaFlags.NIDEC_ALT_PCM_ACCEL:
      pcm_speed_V = [0.0,
                     np.clip(CS.out.vEgo - 3.0, 0.0, 100.0),
                     np.clip(CS.out.vEgo + 0.0, 0.0, 100.0),
                     np.clip(CS.out.vEgo + 5.0, 0.0, 100.0)]
      pcm_speed = float(np.interp(gas - brake, pcm_speed_BP, pcm_speed_V))
      pcm_accel = int(1.0 * self.params.NIDEC_GAS_MAX)
    else:
      pcm_speed_V = [0.0,
                     np.clip(CS.out.vEgo - 2.0, 0.0, 100.0),
                     np.clip(CS.out.vEgo + 2.0, 0.0, 100.0),
                     np.clip(CS.out.vEgo + 5.0, 0.0, 100.0)]
      pcm_speed = float(np.interp(gas - brake, pcm_speed_BP, pcm_speed_V))
      pcm_accel = int(np.clip((accel / 1.44) / max_accel, 0.0, 1.0) * self.params.NIDEC_GAS_MAX)

    if not self.CP.openpilotLongitudinalControl:
      if self.frame % 2 == 0 and not (self.CP.flags & (HondaFlags.BOSCH_RADARLESS | HondaFlags.BOSCH_CANFD)):
        can_sends.append(hondacan.create_bosch_supplemental_1(self.packer, self.CAN))
      # If using stock ACC, spam cancel command to kill gas when OP disengages.
      if pcm_cancel_cmd:
        can_sends.append(hondacan.spam_buttons_command(self.packer, self.CAN, CruiseButtons.CANCEL, self.CP))
      elif CC.cruiseControl.resume:
        can_sends.append(hondacan.spam_buttons_command(self.packer, self.CAN, CruiseButtons.RES_ACCEL, self.CP))

    else:
      # Send gas and brake commands.
      if self.frame % 2 == 0:
        ts = self.frame * DT_CTRL

        if self.CP.flags & HondaFlags.BOSCH:
          gas_force = braking = None
          if self.bosch_longitudinal is not None:
            self.accel, self.gas, gas_force, braking = self.bosch_longitudinal.update(CC, CS, accel)
          else:
            self.accel = float(np.clip(accel, self.params.BOSCH_ACCEL_MIN, self.params.BOSCH_ACCEL_MAX))
            self.gas = float(np.interp(accel, self.params.BOSCH_GAS_LOOKUP_BP, self.params.BOSCH_GAS_LOOKUP_V))

          stopping = actuators.longControlState == LongCtrlState.stopping
          self.stopping_counter = self.stopping_counter + 1 if stopping else 0
          can_sends.extend(hondacan.create_acc_commands(self.packer, self.CAN, CC.enabled, CC.longActive, self.accel, self.gas,
                                                        self.stopping_counter, self.CP, gas_force=gas_force, braking=braking))
        else:
          brake_fraction = np.clip(self.brake_last - wind_brake, 0.0, 1.0)
          if self.CP.flags & HondaFlags.HYBRID:
            apply_brake = hybrid_brake_command(brake_fraction, CS.out.vEgo)
          else:
            apply_brake = int(np.clip(brake_fraction * self.params.NIDEC_BRAKE_MAX, 0, self.params.NIDEC_BRAKE_MAX - 1))
          pump_on, self.last_pump_ts = brake_pump_hysteresis(apply_brake, self.apply_brake_last, self.last_pump_ts, ts)

          pcm_override = True
          can_sends.append(hondacan.create_brake_command(self.packer, self.CAN, apply_brake, pump_on,
                                                         pcm_override, pcm_cancel_cmd, alert_fcw, CS.stock_brake,
                                                         hybrid=bool(self.CP.flags & HondaFlags.HYBRID)))
          self.apply_brake_last = apply_brake
          self.brake = float(brake_fraction) if self.CP.flags & HondaFlags.HYBRID else apply_brake / self.params.NIDEC_BRAKE_MAX
          if self.nidec_interceptor is not None:
            command = self.nidec_interceptor.update(CC, CS, gas, brake, wind_brake)
            can_sends.append(create_command(self.packer, command, (self.frame // 2) % 16))

    if CS.out.steeringPressed:
      self.override_frames = max(self.override_frames, 0) + 1
    elif self.override_frames >= 50:
      self.override_frames = -1
    elif -100 < self.override_frames < 0:
      self.override_frames -= 1
    else:
      self.override_frames = 0

    # Send dashboard UI commands.
    if self.frame % 10 == 0:
      if self.CP.openpilotLongitudinalControl:
        # On Nidec, this also controls longitudinal positive acceleration
        can_sends.append(hondacan.create_acc_hud(self.packer, self.CAN.pt, self.CP, CC.enabled, pcm_speed, pcm_accel,
                                                 hud_control, hud_v_cruise, CS.is_metric, CS.acc_hud))

      steering_available = CS.out.cruiseState.available and CS.out.vEgo > max(self.params.STEER_GLOBAL_MIN_SPEED, self.CP.minSteerSpeed)
      # the cluster shows outline lanes once the driver has turned the wheel for 0.5 s and fills them 1 s after letting
      # go, so a nudge mid-lane does not blink them
      overridden = self.override_frames >= 50 or (-100 < self.override_frames < 0)
      # outline lanes while openpilot is engaged, at any speed; fill them only while it steers above the minimum
      # steer speed. The car cannot see an AOL pause, so a paused AOL with openpilot off shows no lanes.
      engaged = CS.out.cruiseState.available and (CC.enabled or CC.latActive)
      can_sends.extend(hondacan.create_lkas_hud(self.packer, self.CAN.lkas, self.CP, hud_control, CC.latActive,
                                                steering_available, alert_steer_required, CS.lkas_hud,
                                                lanes_active=CC.latActive and not overridden and steering_available,
                                                lanes_outline=engaged))

      if self.CP.openpilotLongitudinalControl:
        # TODO: combining with create_acc_hud block above will change message order and will need replay logs regenerated
        if self.CP.flags & HondaFlags.BOSCH and not (self.CP.flags & HondaFlags.BOSCH_RADARLESS):
          can_sends.append(hondacan.create_radar_hud(self.packer, self.CAN.pt))
        if self.CP.carFingerprint == CAR.HONDA_CIVIC_BOSCH:
          can_sends.append(hondacan.create_legacy_brake_command(self.packer, self.CAN.pt))
        if not (self.CP.flags & HondaFlags.BOSCH):
          self.speed = pcm_speed
          self.gas = (self.nidec_interceptor.command if self.nidec_interceptor is not None else
                      pcm_accel / self.params.NIDEC_GAS_MAX)

    # B-CAN turn signals: the body BCM holds the real lamp for the whole lane change
    if self.bcan_blinker is not None:
      enabled = CS.body_valid and (self.bcan_blinker_settings.current() if self.bcan_blinker_settings is not None else False)
      can_sends.extend(self.bcan_blinker.update(CC, CS, enabled, now_nanos * 1e-9))
      # carstate reads this next frame to keep a quick stalk tap's intent alive while the lamp is held
      CS.bcan_holding_side = self.bcan_blinker.holding_side if enabled else None

    if self.accord_mvl_stock is not None:
      can_sends.extend(self.accord_mvl_stock.update(self.packer, self.CAN, self.CP, CC, CS, self.frame))

    if self.interceptor_learning_params is not None:
      self.interceptor_learning_params.persist(self.frame)
    if self.bosch_learning_params is not None:
      self.bosch_learning_params.persist(self.frame)

    new_actuators = actuators.as_builder()
    new_actuators.speed = self.speed
    new_actuators.accel = self.accel
    new_actuators.gas = self.gas
    new_actuators.brake = self.brake
    new_actuators.torque = self.last_torque
    new_actuators.torqueOutputCan = apply_torque
    if self.angle_sender is not None:
      new_actuators.torque = 0.
      new_actuators.torqueOutputCan = 0.
      new_actuators.steeringAngleDeg = self.angle_sender.out_angle
    elif self.angle_mode:
      new_actuators.steeringAngleDeg = apply_angle

    self.frame += 1
    if _projection is not None:
      _projection.finish(new_actuators.torque)
    return new_actuators, can_sends
