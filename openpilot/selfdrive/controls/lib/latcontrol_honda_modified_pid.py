"""Angle-space PID for modified-EPS Hondas that have no EPS firmware calibration (LatControlHondaEps).

Ported from vfn's latcontrol_pid.py. StarPilot 7.0's own LatControlPID is left untouched: this subclass takes
over update() only for a modified-EPS Honda (create_lateral_controller decides), so every other car runs 7.0's stock
PID. Left behind on vfn: the StarPilot 6.x vehicle tunes (Subaru Impreza, RAV4 TSS2, CR-V 5G output shaping), the
Civic Bosch testing ground and the starpilot_toggles gain scales, none of which exist in 7.0, and NNFF.
"""
import math

import numpy as np

from openpilot.cereal import log
from opendbc.car.honda.carcontroller import get_eps_modified_steering_pressed
from opendbc.car.honda.steer_ratio import get_honda_vgr_inverse, vgr_linear_to_physical
from opendbc.car.honda.values import HondaFlags
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.honda_lateral_common import (
  HONDA_ANGLE_RATE_LIMIT_DEG_S,
  HONDA_TORQUE_OUTPUT_LPF_TAU,
  rate_limit_desired_angle,
  _get_param_float,
  _get_param_bool,
)

_MPH_TO_MS = 0.44704
_LAT_SCALE_LOW_MAX = 25.0 * _MPH_TO_MS
_LAT_SCALE_STD_MAX = 50.0 * _MPH_TO_MS

# Modified-EPS speed-banded feedforward shared by every car in MODIFIED_EPS_KF_CARS. The
# duplicate-near-25 breakpoint preserves the road-tested hard handoff.
MODIFIED_EPS_KF_SPEED_BP = [0.0, 25.0 * _MPH_TO_MS - 1e-3, 25.0 * _MPH_TO_MS, 50.0 * _MPH_TO_MS]  # m/s
MODIFIED_EPS_KF_V = [2.4e-6, 1.8e-6, 3.6e-6, 6.0e-6]

# Cars carrying the shared modified-EPS tune (the four-point kp/ki in interface.py). They all
# take the banded feedforward above; any other modified-EPS Honda keeps the scalar kf from CarParams.
MODIFIED_EPS_KF_CARS = frozenset({
  "HONDA_CLARITY",
  "HONDA_CIVIC",
  "HONDA_CIVIC_BOSCH",
  "HONDA_CRV_5G",
  "HONDA_INSIGHT",
  "ACURA_RDX_3G",
  "ACURA_RDX_3G_MMR",
})

# After a press the carcontroller fades torque back in over HondaOverrideFadeUpSecs, and
# every faded frame trips steer_limited_by_safety, which froze the integrator at its pre-press
# value. Route 11c8fa231c0499ed|0000027a--4eae257c95 at 12:34: two override trips held I at 0.19
# into the turn through the unwind, where it cancelled 35-45 % of P and the car ran wide toward
# the curb. Below 25 mph, 60-70 % of the non-pressed limited frames on routes 277/278/27a were in
# that window. The held I now bleeds toward 0 during the fade instead. 0.5 s leaves 37 % of it
# after a 0.5 s fade.
OVERRIDE_FADE_I_BLEED_TAU = 0.5
OVERRIDE_FADE_UP_S_DEFAULT = 1.5   # carcontroller's HondaOverrideFadeUpSecs default


def use_honda_modified_pid(CP) -> bool:
  return CP.brand == "honda" and bool(CP.flags & HondaFlags.EPS_MODIFIED) and CP.lateralTuning.which() == "pid"


def get_modified_eps_kf(v_ego: float) -> float:
  return float(np.interp(v_ego, MODIFIED_EPS_KF_SPEED_BP, MODIFIED_EPS_KF_V))


def _lat_pid_scale_banded(v_ego: float, low: float, standard: float, highway: float) -> float:
  if v_ego < _LAT_SCALE_LOW_MAX:
    return low
  if v_ego < _LAT_SCALE_STD_MAX:
    return standard
  return highway


def _clarity_eps_pid_output_scale(desired_angle_deg: float, v_ego: float) -> float:
  abs_angle = abs(desired_angle_deg)
  speed_weight = min(max((v_ego - 4.0) / 10.0, 0.0), 1.0)
  mid_turn_weight = min(max((abs_angle - 10.0) / 10.0, 0.0), 1.0)
  angle_weight = min(max((abs_angle - 16.0) / 12.0, 0.0), 1.0)

  # Keep the road-tuned magnitude shaping while removing the artificial
  # left/right bias. Since the output scale is linear in these coefficients,
  # the arithmetic means preserve the exact midpoint of the former left/right
  # behavior for every angle and speed.
  mid_turn_scale = 0.0675  # mean(0.1200 left, 0.0150 right)
  base_scale = 0.0847      # mean(0.0722 left, 0.0972 right)

  scale = 1.0 + (speed_weight * mid_turn_weight * mid_turn_scale)
  scale += speed_weight * angle_weight * base_scale

  return max(scale, 0.6863)


class LatControlHondaModifiedPID(LatControlPID):
  def __init__(self, CP, CI, dt):
    super().__init__(CP, CI, dt)
    self.is_eps_modified = use_honda_modified_pid(CP)
    self.is_modified_eps_kf_car = self.is_eps_modified and str(CP.carFingerprint) in MODIFIED_EPS_KF_CARS
    # Geometry: the exact image's firmware VGR table on top of paramsd's learned ratio, else that fixed ratio.
    # There is intentionally no vehicle-family fallback: another rack's table is not interchangeable. The road-fit
    # steer-ratio curves vfn used here are not ported, so HondaEpsFirmwareVgr is inert.
    self.vgr_inverse = get_honda_vgr_inverse(CP.flags)
    self.prev_angle_steers_des_no_offset = 0.0
    self.eps_modified_steering_pressed_filter_s = 0.0
    self.eps_modified_steering_pressed_prev = False
    self.prev_output_torque = 0.0
    self.params = Params()
    self.frame = -1
    self.lat_p_scale_low = 1.0
    self.lat_p_scale_standard = 1.0
    self.lat_p_scale_highway = 1.0
    self.lat_i_scale_low = 0.2
    self.lat_i_scale_standard = 1.0
    self.lat_i_scale_highway = 0.0
    self.lat_f_scale_low = 1.0
    self.lat_f_scale_standard = 1.0
    self.lat_f_scale_highway = 1.0
    self.angle_rate_limit_deg_s = HONDA_ANGLE_RATE_LIMIT_DEG_S
    # The rate limiter needs its own reference so its allowance is independent of the output LPF.
    self.prev_rate_limited_angle = 0.0
    self.torque_output_lpf = FirstOrderFilter(0.0, HONDA_TORQUE_OUTPUT_LPF_TAU, dt)
    self.torque_output_lpf_enabled = True
    self.torque_output_lpf_tau_low = HONDA_TORQUE_OUTPUT_LPF_TAU
    self.torque_output_lpf_tau_standard = HONDA_TORQUE_OUTPUT_LPF_TAU
    self.torque_output_lpf_tau_highway = HONDA_TORQUE_OUTPUT_LPF_TAU
    self.override_fade_up_s = OVERRIDE_FADE_UP_S_DEFAULT
    self.since_press_s = math.inf  # time since the modified-EPS press detector last fired

  def reset(self):
    super().reset()
    self.pid.reset()
    self.since_press_s = math.inf

  def _read_settings(self):
    # Lat*Scale are user fine-trim shared by every modified-EPS Honda; the base speed banding stays in
    # kpBP/kpV in interface.py. A persisted value always has the same scope across the modified-EPS group.
    self.lat_p_scale_low = _get_param_float(self.params, "LatPScaleLowSpeed", 1.0, 0.0, 5.0, scale=100.0)
    self.lat_p_scale_standard = _get_param_float(self.params, "LatPScaleStandard", 1.0, 0.0, 5.0, scale=100.0)
    self.lat_p_scale_highway = _get_param_float(self.params, "LatPScaleHighway", 1.0, 0.0, 5.0, scale=100.0)
    self.lat_i_scale_low = _get_param_float(self.params, "LatIScaleLowSpeed", 0.2, 0.0, 5.0, scale=100.0)
    self.lat_i_scale_standard = _get_param_float(self.params, "LatIScaleStandard", 1.0, 0.0, 5.0, scale=100.0)
    self.lat_i_scale_highway = _get_param_float(self.params, "LatIScaleHighway", 0.0, 0.0, 5.0, scale=100.0)
    self.lat_f_scale_low = _get_param_float(self.params, "LatFScaleLowSpeed", 1.0, 0.0, 5.0, scale=100.0)
    self.lat_f_scale_standard = _get_param_float(self.params, "LatFScaleStandard", 1.0, 0.0, 5.0, scale=100.0)
    self.lat_f_scale_highway = _get_param_float(self.params, "LatFScaleHighway", 1.0, 0.0, 5.0, scale=100.0)
    self.angle_rate_limit_deg_s = _get_param_float(self.params, "HondaEpsAngleRateLimit",
                                                   HONDA_ANGLE_RATE_LIMIT_DEG_S, 0.0, 2000.0)
    self.override_fade_up_s = _get_param_float(self.params, "HondaOverrideFadeUpSecs",
                                               OVERRIDE_FADE_UP_S_DEFAULT, 0.0, 10.0)
    self.torque_output_lpf_enabled = _get_param_bool(self.params, "HondaTorqueOutputLowPassFilter", True)
    self.torque_output_lpf_tau_low = _get_param_float(
      self.params, "HondaTorqueOutputLpfTauLowSpeed", HONDA_TORQUE_OUTPUT_LPF_TAU, 0.0, 5.0,
    )
    self.torque_output_lpf_tau_standard = _get_param_float(
      self.params, "HondaTorqueOutputLpfTauStandard", HONDA_TORQUE_OUTPUT_LPF_TAU, 0.0, 5.0,
    )
    self.torque_output_lpf_tau_highway = _get_param_float(
      self.params, "HondaTorqueOutputLpfTauHighway", HONDA_TORQUE_OUTPUT_LPF_TAU, 0.0, 5.0,
    )

  def update(self, active, CS, VM, params, steer_limited_by_safety, desired_curvature, curvature_limited,
             lat_delay, calibrated_pose=None, model_data=None, starpilot_toggles=None):
    # StarPilot 7.0's controlsd passes only the first eight; the last three are unused here.
    pid_log = log.ControlsState.LateralPIDState.new_message()
    pid_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    pid_log.steeringRateDeg = float(CS.steeringRateDeg)

    # Firmware VGR: VehicleModel keeps the scalar sR paramsd learned, so it returns the angle a constant-ratio rack
    # would need; the image's measured position table is then inverted to the angle this rack needs (identity when
    # the image has no traced table). Solving at the DESIRED angle keeps measurement wobble out of the target.
    linear_des_no_offset = math.degrees(VM.get_steer_from_curvature(-desired_curvature, CS.vEgo, params.roll))
    angle_steers_des_no_offset = vgr_linear_to_physical(linear_des_no_offset, self.vgr_inverse)

    # Shape the target before it becomes error or feedforward: the angle-rate ceiling handles target continuity,
    # while the single speed-banded LPF below acts on the final torque command.
    if active:
      angle_steers_des_no_offset = rate_limit_desired_angle(
        angle_steers_des_no_offset, self.prev_rate_limited_angle, self.angle_rate_limit_deg_s, self.dt,
      )
      self.prev_rate_limited_angle = angle_steers_des_no_offset

    angle_steers_des = angle_steers_des_no_offset + params.angleOffsetDeg
    error = angle_steers_des - CS.steeringAngleDeg

    pid_log.steeringAngleDesiredDeg = angle_steers_des
    pid_log.angleError = error
    if not active:
      output_torque = 0.0
      pid_log.active = False
      self.prev_angle_steers_des_no_offset = angle_steers_des_no_offset
      self.prev_rate_limited_angle = angle_steers_des_no_offset
      self.torque_output_lpf.x = 0.0
      self.torque_output_lpf.initialized = True
      self.eps_modified_steering_pressed_filter_s = 0.0
      self.eps_modified_steering_pressed_prev = False
      self.prev_output_torque = 0.0
      # PR #8 piece 3: controlsd only resets LatControl.sat_time on disengage, so the
      # integrator carried across it (routes 277/278/27a: up to 0.32 into a fresh engagement).
      self.pid.reset()
      self.since_press_s = math.inf

    else:
      self.frame += 1

      # offset does not contribute to resistive torque
      ff_factor = get_modified_eps_kf(CS.vEgo) if self.is_modified_eps_kf_car else self.ff_factor
      ff = ff_factor * self.get_steer_feedforward(angle_steers_des_no_offset, CS.vEgo)

      self.eps_modified_steering_pressed_filter_s, steering_pressed = get_eps_modified_steering_pressed(
        bool(CS.steeringPressed),
        float(getattr(CS, "steeringTorque", 0.0)),
        float(self.prev_output_torque),
        self.eps_modified_steering_pressed_filter_s,
        self.eps_modified_steering_pressed_prev,
      )
      self.eps_modified_steering_pressed_prev = steering_pressed
      self.since_press_s = 0.0 if steering_pressed else self.since_press_s + self.dt

      freeze_threshold = 2.0
      freeze_integrator = steer_limited_by_safety or steering_pressed or CS.vEgo < freeze_threshold
      # LatIScale is the effective integrator gain, not merely an output multiplier.
      # In particular, a zero-I highway band must not retain hidden integral state that
      # comes back when the car crosses into another speed band.
      i_scale = _lat_pid_scale_banded(CS.vEgo, self.lat_i_scale_low, self.lat_i_scale_standard, self.lat_i_scale_highway)

      self.pid.update(error,
                      feedforward=ff,
                      speed=CS.vEgo,
                      freeze_integrator=freeze_integrator,
                      integrator_gain_scale=i_scale,
                      reset_integrator=i_scale <= 0.0 or CS.vEgo < freeze_threshold)
      if steer_limited_by_safety and not steering_pressed and self.since_press_s <= self.override_fade_up_s + self.dt:
        self.pid.i *= math.exp(-self.dt / OVERRIDE_FADE_I_BLEED_TAU)

      if self.frame % 300 == 0:  # same place in the frame as on vfn: after the integrator, before the P/F scales
        self._read_settings()

      p_scale = _lat_pid_scale_banded(CS.vEgo, self.lat_p_scale_low, self.lat_p_scale_standard, self.lat_p_scale_highway)
      f_scale = _lat_pid_scale_banded(CS.vEgo, self.lat_f_scale_low, self.lat_f_scale_standard, self.lat_f_scale_highway)
      output_torque = self.pid.p * p_scale + self.pid.i + self.pid.d + self.pid.f * f_scale
      output_torque *= _clarity_eps_pid_output_scale(angle_steers_des_no_offset, CS.vEgo)
      output_torque = float(max(min(output_torque, self.steer_max), -self.steer_max))

      if self.torque_output_lpf_enabled:
        self.torque_output_lpf.update_alpha(
          _lat_pid_scale_banded(CS.vEgo, self.torque_output_lpf_tau_low, self.torque_output_lpf_tau_standard,
                                self.torque_output_lpf_tau_highway)
        )
        output_torque = float(self.torque_output_lpf.update(output_torque))
      else:
        self.torque_output_lpf.x = output_torque
        self.torque_output_lpf.initialized = True
      output_torque = float(max(min(output_torque, self.steer_max), -self.steer_max))

      pid_log.active = True
      pid_log.p = float(self.pid.p)
      pid_log.i = float(self.pid.i)
      pid_log.f = float(self.pid.f)
      pid_log.output = float(output_torque)
      pid_log.saturated = bool(self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS,
                                                      steer_limited_by_safety, curvature_limited))
      self.prev_angle_steers_des_no_offset = angle_steers_des_no_offset
      self.prev_output_torque = float(output_torque)

    return output_torque, angle_steers_des, pid_log
