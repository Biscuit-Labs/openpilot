"""Modified-EPS Honda steering in the car controller (from vfn), for every Honda on a recognized modified EPS.

Kept free of openpilot settings: openpilot attaches a source of ModifiedEpsSettings (starpilot/car/honda/modified_eps.py)
to the car controller and car state; without one the defaults below apply.

INVARIANT: every stage here may only reduce the command because the car genuinely cannot deliver it -- below the
minimum steer speed, cut for a driver override, or held back by the opt-in steer-delta limiter. controlsd turns any
difference between CC.actuators.torque and what is sent into steer_limited_by_safety, which freezes the lateral
integrator, so comfort shaping (the output low-pass) lives in the lateral controller, never here.
"""
from dataclasses import dataclass

from opendbc.car import DT_CTRL, rate_limit
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.honda.values import HondaFlags, STEER_THRESHOLD

STOCK_STEER_THRESHOLD = 1200


@dataclass(frozen=True)
class ModifiedEpsSettings:
  override_threshold: int = 2000         # HondaDriverOverrideThreshold, driver torque for steeringPressed (stock 1200)
  min_steer_speed_mph: int = 1           # HondaMinSteerSpeed, no torque below this
  fade_down_s: float = 0.1               # HondaOverrideFadeDownSecs, torque fade on a press (0 = cut at once)
  fade_up_s: float = 1.5                 # HondaOverrideFadeUpSecs, torque fade back in after a press
  torque_scale: float = 0.0              # HondaOverrideTorqueScale / 100, torque kept while pressed
  assist_during_override: bool = False   # HondaDriverAssistDuringOverride, keep LKAS active while pressed
  delta_limiter: bool = False            # HondaSteerDeltaLimiter, the stock steer rate limit, opt-in
  delta_up: float = 3.0                  # HondaSteerDeltaUp, per second of the normalized command
  delta_down: float = 3.0                # HondaSteerDeltaDown


DEFAULT_SETTINGS = ModifiedEpsSettings()


def modified_eps(CP) -> bool:
  return (CP.brand == "honda" and bool(CP.flags & HondaFlags.EPS_MODIFIED) and
          not CP.passive and not CP.dashcamOnly and not CP.notCar)


def current_settings(source) -> ModifiedEpsSettings:
  return source.current() if source is not None else DEFAULT_SETTINGS


def steering_pressed_threshold(CP, override_threshold: int) -> float:
  # A modified EPS pushes column torque of its own, which trips the stock threshold. The setting is in stock-1200 units;
  # a car whose stock threshold differs scales it.
  stock = STEER_THRESHOLD.get(CP.carFingerprint, STOCK_STEER_THRESHOLD)
  if override_threshold <= 0:
    return stock
  return override_threshold if stock == STOCK_STEER_THRESHOLD else stock * override_threshold / STOCK_STEER_THRESHOLD


def lane_change_nudge_torque(CP) -> float | None:
  # With steeringPressed raised on a modified EPS, a lane-change nudge still counts at the car's stock threshold.
  return STEER_THRESHOLD.get(CP.carFingerprint, STOCK_STEER_THRESHOLD) if modified_eps(CP) else None


def get_eps_modified_steering_pressed(
  raw_pressed: bool, steering_torque: float, torque_cmd: float, filter_s: float, previous_pressed: bool
) -> tuple[float, bool]:
  # The EPS's own column torque trips steeringPressed. A press that pushes against the command, or one with almost
  # no command, is the driver at once; one that agrees with the command must hold for 0.28 s first.
  if not raw_pressed:
    return 0.0, False

  torque_product = float(steering_torque) * float(torque_cmd)
  torque_cmd_abs = abs(float(torque_cmd))
  if previous_pressed or torque_cmd_abs < 0.10 or torque_product < 0.0:
    return 1.0, True

  filter_s = min(1.0, filter_s + DT_CTRL)
  return filter_s, filter_s >= 0.28


class ModifiedEpsSteering:
  def __init__(self):
    self.steering_pressed_filter_s = 0.0
    self.steering_pressed_prev = False
    self.override_ramp = 1.0
    self.lat_active_prev = False
    self.last_torque = 0.0

  def update(self, CC, CS, settings: ModifiedEpsSettings) -> tuple[float, bool, bool]:
    """Returns (torque to send, LKAS active, filtered steering pressed)."""
    torque_cmd = float(CC.actuators.torque) if CC.latActive else 0.0
    steering_pressed = False
    below_min_steer_speed = CS.out.vEgo < settings.min_steer_speed_mph * CV.MPH_TO_MS
    if below_min_steer_speed:
      torque_cmd = 0.0

    if CC.latActive:
      # The same press detector as the modified-EPS lateral controllers, so the actuator never fades on a press the
      # controller does not see (false safety limiting and integrator-freeze churn).
      self.steering_pressed_filter_s, steering_pressed = get_eps_modified_steering_pressed(
        bool(CS.out.steeringPressed), float(CS.out.steeringTorque), torque_cmd,
        self.steering_pressed_filter_s, self.steering_pressed_prev)
      self.steering_pressed_prev = steering_pressed

      if not self.lat_active_prev:
        self.override_ramp = 0.0
      if steering_pressed:
        if settings.fade_down_s <= 0.0:
          self.override_ramp = settings.torque_scale
        else:
          self.override_ramp = max(settings.torque_scale, self.override_ramp - DT_CTRL / settings.fade_down_s)
      else:
        self.override_ramp = 1.0 if settings.fade_up_s <= 0.0 else min(1.0, self.override_ramp + DT_CTRL / settings.fade_up_s)
      torque_cmd *= self.override_ramp
    else:
      self.override_ramp = 0.0
      self.steering_pressed_filter_s = 0.0
      self.steering_pressed_prev = False

    # Unlike a low-pass filter, the limiter withholds authority for as long as it is saturated, so reporting it as
    # limiting -- and freezing the integrator against it -- is correct.
    if settings.delta_limiter:
      torque_cmd = rate_limit(torque_cmd, self.last_torque, -settings.delta_down * DT_CTRL, settings.delta_up * DT_CTRL)

    self.last_torque = torque_cmd
    self.lat_active_prev = CC.latActive
    lkas_active = CC.latActive and (settings.assist_during_override or not steering_pressed) and not below_min_steer_speed
    return torque_cmd, lkas_active, steering_pressed
