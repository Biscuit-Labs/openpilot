"""Angle mode: openpilot sends a steering-wheel angle target in 0xE4 to an angle-mode EPS build, protocol v3 only (build 0x0E
on; meps/protocol.py, rwd-xray lab/PROTOCOL_V3_20261125.md). Older angle builds (v1 0x04-0x0A, v2 0x0B-0x0D) are no longer
supported: eps_cal_status faults them ("unsupported_build" / "unknown_build") and nothing steers.

Chosen at startup by the setting ANGLE_MODE_PARAM (Night Star / Galaxy row "Angle Mode", default on): card's startup
hook (openpilot starpilot/car/honda/clarity_angle_mode.py) calls apply_angle_mode, which on a car with an angle-mode EPS
image sets HondaFlags.CLARITY_ANGLE_MODE and steerControlType = angle. Off: the angle image runs its stock torque mode
with the stock tune (torque frames; the v3 front end reads any non-angle frame as stock mode). On a Clarity whose EPS is
not a v3 build, the 0x6A4 interlock never reports ready, so openpilot faults and sends no steering.

0xE4 in angle mode (every frame, 100 Hz; CarController, hondacan._create_steering_control_v3):
  steering: byte 2 = 0x4C DRIVE / 0x0C YIELD (bits 3:2 = 3 with the request bit 0 mark an angle frame), bytes 0-1 the
           target, byte 3 0. Only while the EPS reports in 0x6A4 that it runs MODE 1 (eps_cal_status.angle_ready) and
           lateral is active.
  otherwise: STANDBY, byte 2 = 0x0D with target 0, so the EPS selects its angle table set at LKAS idle.
Panda (safety bit HondaSafetyFlags.CLARITY_ANGLE, honda.h): the marker only as STANDBY while lateral is not allowed; the
  request bit never in angle mode. Steering: the standard angle rule of the other angle brands, |target| <= the
  3.6 m/s^2 angle (std_angle_limit) and per-frame step <= the 3.6 m/s^3 jerk step (std_angle_step), at speed - 1 m/s,
  with the last target reset to the measured angle after a blocked frame or while not steering. No exemptions: the
  sender applies the same limits to every frame.
Units: bytes 0-1 = the EPS's own angle raw value (0.1 deg/bit, raw = -10 * CS.steeringAngleDeg; rack-linear on a
  linear-angle EPS).

Limits (all inside the EPS's own, so its jump-reject fault and its clamps never act in normal driving):
  - per-frame step <= 0.6 x the EPS jump threshold (4 deg/10 ms below 5 m/s, 1 deg/10 ms from 15 m/s; the EPS
    allows 0.8 x at the worst frame spacing) and <= 0.9 x the EPS reference slew (5 m/s^3 lateral jerk, 170 deg/s cap)
  - the target moves as a rate- and acceleration-limited trajectory: rate <= TARGET_RATE(v), acceleration <=
    TARGET_ACCEL(v) (~1.5 x the wheel acceleration openpilot produced hands-off in torque mode, p99), braking ahead of
    the target so it never overshoots
  - the Steering Angle Rate Limit setting (HondaEpsAngleRateLimit, deg/s, 0 = off; CarController passes it) lowers the
    rate cap further
  - engage and release after an override: the trajectory starts at the measured angle and wheel rate, its limits ramp
    from ENGAGE_FLOOR to full and the effort fade eases the loop in over Override Fade Up (HondaOverrideFadeUpSecs)
  - |desired| <= panda's 3.6 m/s^2 angle; the sent angle never moves more than panda's 3.6 m/s^3 jerk step per frame
  - override: YIELD, the target follows the wheel (sender_follow)
  - not active: the target is the measured angle (the Tesla pattern), so the first target the EPS sees equals its own
    angle.
"""
import numpy as np

from opendbc.car import DT_CTRL
from opendbc.car import structs
from opendbc.car.lateral import ISO_LATERAL_ACCEL
from opendbc.car.honda.angle_profiles import AngleProfile, angle_profile, own_geometry, safety_param_bits, vm_angle_limit
from opendbc.car.honda.values import CAR, HondaFlags, HondaSafetyFlags, is_angle_image

ANGLE_MODE_PARAM = "HondaClarityAngleMode"   # BOOL, default "1" (params_keys.h); read once at startup
RAW_PER_DEG = -10.0           # 0x14A STEER_ANGLE factor is -0.1

# EPS limits (angle_ref.py v3: JUMP, SLEW, AMAX), speed m/s
_V = [0., 5., 8., 10., 12., 15., 20., 25., 30.]
EPS_JUMP_DEG = [4.0, 4.0, 3.1, 2.5, 1.9, 1.0, 1.0, 1.0, 1.0]                     # per 10 ms
EPS_SLEW_DEG_S = [170.0, 170.0, 170.0, 143.9, 103.1, 69.7, 43.8, 31.8, 25.3]
ANGLE_STEP_DEG = [min(0.6 * j, 0.9 * s * DT_CTRL) for j, s in zip(EPS_JUMP_DEG, EPS_SLEW_DEG_S, strict=True)]
AMAX_V = [5., 8., 10., 12., 16., 20., 25., 30.]
EPS_AMAX_DEG = [379., 160., 109., 80.3, 50.0, 35.3, 25.7, 20.4]
ANGLE_MAX_FRAC = 0.95
# panda's limits (honda.h honda_angle_accel_limit), the standard angle rule of the other angle brands: 3.6 m/s^2 lateral
# accel and 3.6 m/s^3 lateral jerk (opendbc car/lateral.py MAX_LATERAL_ACCEL / MAX_LATERAL_JERK), with the angle for a
# lateral acceleration from the EPS's own clamp table (0.9 x EPS_AMAX_DEG = 3.6 m/s^2), 1/v^2 below 5 and above 30 m/s,
# capped at STEER_ANGLE_MAX. Panda evaluates them at speed - 1 m/s, openpilot at v_ego, so openpilot stays inside.
STD_ACCEL_SCALE = 0.9
STEER_ANGLE_MAX = 500.0       # deg (panda HONDA_ANGLE_MAX); the logged wheel reached 439
# Linear-angle EPS (build 0x0C on): the same 3.6 m/s^2 limit in the EPS's rack-linear units (0x6A2), i.e. the published
# limit above converted through the firmware VGR map, at the EPS clamp table's knots. Generated with panda's copy
# (honda.h honda_angle_accel_limit_linear) by rwd-xray lab/clarity/CLARITY_ANGLE_MODE_0x0C_20261122/gen_linear_limit.py;
# the EPS clamp is never tighter. 1/v^2 above 80 m/s.
# understeer (cautious second car, owner's car), same method (rwd-xray shared notes CLARITY_ARAGON_UNDERSTEER.md)
LINEAR_SPREAD_KUS = (0.00049, 0.00062)
LINEAR_LIMIT_V = [1.0, 4.13, 4.25, 4.5, 4.75, 5., 8., 10., 12., 16., 20., 25., 30., 32.5, 35., 37.5, 40., 45., 50., 60., 80.]
LINEAR_LIMIT_DEG = [578.36, 578.30, 546.10, 486.34, 434.20, 390.11, 156.61, 102.65, 73.63, 44.91, 31.47, 22.85, 18.15,
                    15.45, 13.35, 11.64, 10.22, 8.05, 6.52, 4.53, 2.56]
STEER_ANGLE_MAX_LINEAR = 578.4   # deg (panda HONDA_ANGLE_MAX_LINEAR)
# target trajectory (v2): rate and acceleration limits by speed, engage fade
_VT = [0., 5., 10., 15., 20., 30.]
TARGET_RATE_DEG_S = [150., 150., 100., 60., 40., 25.]
TARGET_ACCEL_DEG_S2 = [450., 600., 450., 300., 225., 180.]    # 1.5 x torque-mode hands-off p99 (11-15 route)
ENGAGE_S, ENGAGE_FLOOR = 1.5, 0.15    # limits ramp 15% -> 100% after the request rises; ENGAGE_S = default engage time
RAW_MAX = 32767


def angle_build(CP) -> bool:
  """An EPS image that can run angle mode. The Clarity: any modified image (the 0x6A4 interlock finds out which build it
  is). A car with an angle profile (angle_profiles.py): only an angle PTM image, which reports '+' in both separator
  slots (39990+TJB+A220); its torque PTM image (39990-TJB,A220) keeps torque mode whatever the setting says."""
  if not CP.flags & HondaFlags.EPS_MODIFIED:
    return False
  if CP.carFingerprint == CAR.HONDA_CLARITY:
    return True
  return angle_profile(CP) is not None and angle_image(CP)


def angle_image(CP) -> bool:
  return any(fw.ecu == "eps" and is_angle_image(fw.fwVersion) for fw in CP.carFw)


def apply_angle_mode(CP, requested: bool):
  """Startup choice. Only a Clarity on modified EPS firmware, or a car with an angle profile on its angle PTM image, can
  run the angle build; every other car is untouched."""
  if angle_image(CP) and not (requested and angle_build(CP)):
    # an angle image with angle mode off runs its STOCK torque mode (v2 MODE 0): stock tune (interface.py), and no
    # modified-EPS behaviour anywhere (steer maps, PTM calibration, thresholds, controller)
    CP.flags &= ~HondaFlags.EPS_MODIFIED.value
  if requested and angle_build(CP):
    CP.flags |= HondaFlags.CLARITY_ANGLE_MODE.value
    CP.steerControlType = structs.CarParams.SteerControlType.angle
    # panda's angle rule (honda.h HONDA_PARAM_ANGLE), the standard angle rule: request/payload/target only while lateral
    # is allowed, |target| within the 3.6 m/s^2 angle, per-frame steps within the 3.6 m/s^3 jerk step, the first target
    # within one step of the wheel
    CP.safetyConfigs[-1].safetyParam |= HondaSafetyFlags.CLARITY_ANGLE.value
    profile = angle_profile(CP)
    if profile is not None:
      # a profile car (linear from the start, 0x6A2 the RX check): panda's vehicle-model row, in param bits 15:13. The
      # EPS publishes wheel degrees at the on-center ratio, so the vehicle model starts paramsd at that ratio (the
      # CarSpecs ratio of a VGR rack is not it: the RDX's 11.95 against 16.2 learned).
      CP.safetyConfigs[-1].safetyParam |= safety_param_bits(profile)
      CP.steerRatio = own_geometry(CP).steer_ratio  # the platform's own ratio (rows may be shared)
    # as the other angle cars (torque_data/override.toml): maxLateralAccel is the angle-mode limit the UI torque bar's
    # lateral-acceleration estimate is scaled to. The torque-mode value (0.32, the Accord's measured max via substitute.toml)
    # pegs the bar at a tenth of what openpilot can command; controls clip lateral accel at ISO_LATERAL_ACCEL (3.0, no roll).
    # Nothing else reads it in angle mode (the torque controller is not used, controls use their own limit).
    CP.maxLateralAccel = ISO_LATERAL_ACCEL
    # every angle build steers down to standstill (the proof gates' parking cases); an angle image keeps the stock tune
    # (interface.py), which may carry a stock minimum steer speed, so angle mode sets these itself
    CP.steerAtStandstill = True
    CP.minSteerSpeed = -1.0
  return CP


def angle_mode(CP) -> bool:
  return bool(CP.flags & HondaFlags.CLARITY_ANGLE_MODE)


def std_angle_limit(v_ego: float, linear: bool = False, profile: AngleProfile | None = None) -> float:
  """The 3.6 m/s^2 steering-wheel angle (deg), panda's absolute limit at this speed (linear: in rack-linear units; a
  profile: panda's vehicle-model row for that car, angle_profiles.vm_angle_limit)."""
  v = max(float(v_ego), 1.0)
  if profile is not None:
    return vm_angle_limit(v, profile)
  if linear:
    lim = float(np.interp(v, LINEAR_LIMIT_V, LINEAR_LIMIT_DEG)) if v <= LINEAR_LIMIT_V[-1] else \
          LINEAR_LIMIT_DEG[-1] * (LINEAR_LIMIT_V[-1] / v) ** 2
    # panda's car-to-car spread scaling (honda.h honda_angle_accel_limit_linear): a second Clarity understeers less
    lim *= (1.0 + LINEAR_SPREAD_KUS[0] * v * v) / (1.0 + LINEAR_SPREAD_KUS[1] * v * v)
    return min(lim, STEER_ANGLE_MAX_LINEAR)
  if v < AMAX_V[0]:
    lim = STD_ACCEL_SCALE * EPS_AMAX_DEG[0] * (AMAX_V[0] / v) ** 2
  elif v > AMAX_V[-1]:
    lim = STD_ACCEL_SCALE * EPS_AMAX_DEG[-1] * (AMAX_V[-1] / v) ** 2
  else:
    lim = STD_ACCEL_SCALE * float(np.interp(v, AMAX_V, EPS_AMAX_DEG))
  return min(lim, STEER_ANGLE_MAX)


def std_angle_step(v_ego: float, linear: bool = False, profile: AngleProfile | None = None) -> float:
  """Per-frame step (deg) from the 3.6 m/s^3 jerk limit: jerk = accel = 3.6, so the 3.6 m/s^2 angle per second."""
  return std_angle_limit(v_ego, linear, profile) * DT_CTRL


def angle_limit(v_ego: float, linear: bool = False, profile: AngleProfile | None = None) -> float:
  # 0.95 x the EPS's 4.0 m/s^2 table (inside the 0x0B 3.6 clamp only below 5 m/s, where 1/v^2 takes over) and never past
  # panda's 3.6 m/s^2 angle
  if profile is not None:   # panda's row; each profile car's EPS clamp is never tighter (angle_profiles.py)
    return std_angle_limit(v_ego, True, profile)
  if linear:   # the 0.95 x 4.0 table only binds below 5 m/s, where the 1/v^2 panda limit is tighter anyway
    return std_angle_limit(v_ego, True)
  return min(ANGLE_MAX_FRAC * float(np.interp(v_ego, AMAX_V, EPS_AMAX_DEG)), std_angle_limit(v_ego))


def angle_to_raw(angle_deg: float) -> int:
  return int(max(-RAW_MAX, min(RAW_MAX, round(angle_deg * RAW_PER_DEG))))


class AngleModeSender:
  """Turns actuators.steeringAngleDeg into the 0xE4 angle target. update() returns (raw, steering).
  profile: a profile car's angle profile (angle_profiles.py): linear from the start, limits from panda's row for it."""
  def __init__(self, profile: AngleProfile | None = None):
    self.profile = profile
    self.apply_angle = 0.0
    self.apply_rate = 0.0
    self.active_frames = 0
    self.sent_active = False
    self.linear = profile is not None   # linear-angle EPS (0x0C on): desired / measured / limits are rack-linear (CarController sets it)
    self.out_angle = 0.0      # the angle actually sent (= apply_angle once the effort fade is done)

  def update(self, lat_active: bool, desired_deg: float, measured_deg: float, v_ego: float,
             angle_ready: bool, measured_rate_deg_s: float = 0.0, engage_s: float = ENGAGE_S,
             rate_limit_deg_s: float = 0.0, effort_fade: bool = True) -> tuple[int, bool]:
    active = bool(lat_active and angle_ready)
    if active and not self.sent_active and abs(float(measured_deg)) > std_angle_limit(v_ego, self.linear, self.profile):
      # no engage while the wheel is beyond panda's 3.6 m/s^2 angle: the first target must be within one step of the
      # wheel and inside the limit, so panda would block every frame (the Hyundai EV9 path gates the request the same
      # way). CarController reports the dropped request to the loop-running interlock, so it does not count.
      active = False
    if not active:
      self.apply_angle, self.apply_rate = float(measured_deg), float(measured_rate_deg_s)
      self.out_angle = float(measured_deg)
      self.active_frames, self.sent_active = 0, False
      return 0, False
    lim = angle_limit(v_ego, self.linear, self.profile)
    # clamp the target, not the output, so the output still moves along the limited trajectory (from a measured angle
    # above the clamp it walks down to it instead of jumping, which the EPS would reject)
    target = float(np.clip(float(desired_deg), -lim, lim))
    fade = 1.0 if engage_s <= 0.0 else min(1.0, ENGAGE_FLOOR + (1.0 - ENGAGE_FLOOR) * self.active_frames * DT_CTRL / engage_s)
    # step: 0.6 x the EPS jump threshold and panda's jerk step (the 3.6 m/s^3 standard)
    step = min(float(np.interp(v_ego, _V, ANGLE_STEP_DEG)), std_angle_step(v_ego, self.linear, self.profile))
    rate_cap = min(float(np.interp(v_ego, _VT, TARGET_RATE_DEG_S)), step / DT_CTRL)
    if rate_limit_deg_s > 0.0:                # Steering Angle Rate Limit (Night Star / Galaxy), 0 = off
      rate_cap = min(rate_cap, rate_limit_deg_s)
    rate_max = fade * rate_cap
    accel_max = fade * float(np.interp(v_ego, _VT, TARGET_ACCEL_DEG_S2))
    err = target - self.apply_angle
    # exact discrete braking curve: the fastest rate from which the trajectory can still stop at the target with
    # accel_max per frame (the continuous sqrt(2*A*e) overshoots by a frame)
    ad = accel_max * DT_CTRL
    brake = ad * (((0.25 + 2.0 * abs(err) / (ad * DT_CTRL)) ** 0.5) - 0.5) if ad > 0 else 0.0
    rate_des = float(np.sign(err)) * min(rate_max, brake, abs(err) / DT_CTRL)
    self.apply_rate += float(np.clip(rate_des - self.apply_rate, -accel_max * DT_CTRL, accel_max * DT_CTRL))
    # rate_max shapes rate_des only, so a wheel already turning faster at engage eases down at accel_max instead of being
    # stopped in one frame; the EPS's own per-frame jump limit stays a hard bound
    step_rate = step / DT_CTRL
    self.apply_rate = float(np.clip(self.apply_rate, -step_rate, step_rate))
    self.apply_angle += self.apply_rate * DT_CTRL
    # effort fade: the EPS loop pushes in proportion to (target - wheel), so sending wheel + w * (trajectory - wheel)
    # scales its effort by w. w eases 0 -> 1 (smoothstep) over engage_s after the request rises, so the loop takes the
    # wheel over gently instead of pulling it onto the trajectory at full stiffness. The sent angle still moves at most
    # the EPS's per-frame jump limit.
    out = self.apply_angle
    if effort_fade and engage_s > 0.0:
      x = min(1.0, (self.active_frames + 1) * DT_CTRL / engage_s)
      w = x * x * (3.0 - 2.0 * x)
      out = float(measured_deg) + w * (self.apply_angle - float(measured_deg))
    if not self.sent_active:
      self.out_angle = float(measured_deg)   # panda: the first target within one step of the measured angle
    std_lim = std_angle_limit(v_ego, self.linear, self.profile)
    self.out_angle = float(np.clip(self.out_angle + np.clip(out - self.out_angle, -step, step), -std_lim, std_lim))
    self.active_frames += 1
    self.sent_active = True
    return angle_to_raw(self.out_angle), True


def _follow_step(sender, v_ego: float) -> float:
  return min(float(np.interp(v_ego, _V, ANGLE_STEP_DEG)), std_angle_step(v_ego, sender.linear, sender.profile))


def sender_follow(sender: "AngleModeSender", measured_deg: float, measured_rate_deg_s: float, v_ego: float,
                  tracks_wheel: bool = False) -> tuple[int, bool]:
  """Protocol v3 YIELD (meps/protocol.py): while the driver overrides, the loop has no authority. Returns (raw, steering).
  The trajectory restarts from the wheel with the engage fade, so on the release the target walks from the wheel to the plan
  over Override Fade Up (smoothstep effort fade): rwd-xray clarity/CLARITY_ANGLE_MODE_20261117/hand/V3_ANGLE_RAMP_20261124.md.
  tracks_wheel (builds >= 0x0F, meps_protocol.YIELD_TRACKS_WHEEL_BUILDS: the EPS skips the jump check on YIELD and pins its
  reference to the wheel): the sent target IS the wheel, every frame, as the other angle brands send while not steering (panda
  checks a YIELD frame against the measured wheel, honda.h). Past panda's 3.6 m/s^2 angle the target cannot be both the wheel
  and inside the limit, so the frame is STANDBY instead (steering False): the sender resets, and the next engage waits until
  the wheel is back inside and starts from it (AngleModeSender.update).
  Otherwise (0x0E, which jump-checks YIELD frames): the target follows the wheel step-limited (the EPS jump limit and
  panda's step), waiting at panda's absolute limit past it (beyond_limit keeps the frames YIELD until the wheel is back inside)."""
  sender.apply_angle, sender.apply_rate, sender.active_frames = float(measured_deg), float(measured_rate_deg_s), 0
  if tracks_wheel:
    # the release starts at rest: carrying the driver's unwind rate into the trajectory, whose acceleration the engage
    # fade holds at 15 % at first, coasted the target 15.7 deg (median, up to 64) past the plan and the EPS dragged the
    # wheel after it (Clarity 0x0F route 00000129, rwd-xray clarity/CLARITY_0x0F_FIRST_DRIVE_20261126/REPORT.md); on 0x0E the
    # step-limited follow below lagged the wheel and hid it
    sender.apply_rate = 0.0
    sender.out_angle = float(measured_deg)
    if beyond_limit(sender, measured_deg, v_ego):
      sender.sent_active = False
      return 0, False
    sender.sent_active = True
    return angle_to_raw(sender.out_angle), True
  step = _follow_step(sender, v_ego)
  std_lim = std_angle_limit(v_ego, sender.linear, sender.profile)
  sender.out_angle = float(np.clip(sender.out_angle + np.clip(float(measured_deg) - sender.out_angle, -step, step), -std_lim, std_lim))
  sender.sent_active = True
  return angle_to_raw(sender.out_angle), True


def beyond_limit(sender: "AngleModeSender", measured_deg: float, v_ego: float) -> bool:
  """The wheel is past panda's 3.6 m/s^2 angle. After a press CarController keeps yielding until it is back inside, so
  DRIVE never resumes with the loop pulling the wheel in to a clamped target (the engage waits the same way)."""
  return abs(float(measured_deg)) > std_angle_limit(v_ego, sender.linear, sender.profile)
