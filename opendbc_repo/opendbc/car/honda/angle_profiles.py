"""Angle profiles of the fleet's linear-angle EPS builds (0x0C on).

Panda (safety/modes/honda.h HONDA_ANGLE_VM_PARAMS) selects one with safety param bits 15:13 next to the angle bit
(HondaSafetyFlags.CLARITY_ANGLE, 4096). Profile 0 is the Clarity rule (its own EPS clamp table, clarity_angle_mode.py).
Profile 1..7 is one platform: the EPS takes and publishes (0x6A2) the rack-linear angle in steering-wheel degrees at the
on-center ratio, so the 3.6 m/s^2 angle is the standard vehicle model at that ratio. These rows and the panda rows must
match: test_honda.py checks both against this file.

Adding a car: the next free index, slip_factor = calc_slip_factor(VehicleModel(CP)) of that platform, steer_ratio = the
on-center ratio (what paramsd learns on that car's routes; not the CarSpecs ratio of a VGR rack), wheelbase = CarSpecs.
"""
from dataclasses import dataclass

from opendbc.car.honda.values import CAR

ANGLE_PROFILE_SHIFT = 13
ISO_LATERAL_ACCEL = 3.0
MAX_LATERAL_ACCEL = ISO_LATERAL_ACCEL + 9.81 * 0.06  # panda's ~3.6 m/s^2 (road roll)
MAX_ANGLE_LINEAR = 578.4  # deg, panda's cap (HONDA_ANGLE_MAX_LINEAR)


@dataclass(frozen=True)
class AngleProfile:
  """a panda row (honda.h HONDA_ANGLE_VM_PARAMS[index - 1])"""
  index: int
  slip_factor: float
  steer_ratio: float
  wheelbase: float


@dataclass(frozen=True)
class OwnGeometry:
  """a platform's own on-center vehicle model: its EPS clamp (at 4.0 m/s^2) and paramsd's starting ratio come from this"""
  steer_ratio: float  # on-center: what paramsd learns on that platform's routes (not the CarSpecs ratio of a VGR rack)
  wheelbase: float    # CarSpecs
  slip_factor: float  # calc_slip_factor(VehicleModel(CP))


# A platform may use a row only if, over 5-40 m/s, 0.90 <= row limit / own limit <= 1.00: never looser than its own model,
# and at most 10 % less authority (openpilot asks for <= 3.0 m/s^2, panda allows 3.6). Rows are scarce (bits 15:13, 7 rows),
# so platforms share rows where that holds (test_angle_profiles.py checks it). The orchestrator allocates the indices.
PANDA_ROWS: dict[int, AngleProfile] = {
  1: AngleProfile(1, -0.000782, 16.28, 2.66),     # HONDA_CRV_5G's own; also ACURA_RDX_3G (0.94-1.00) and HONDA_INSIGHT (0.91-1.00)
  2: AngleProfile(2, -0.000448, 14.99, 2.70),     # HONDA_CIVIC (Nidec)'s own
  3: AngleProfile(3, -0.000638, 16.0, 2.70),      # HONDA_CIVIC_BOSCH's own
  4: AngleProfile(4, -0.00035, 17.81, 3.00),      # HONDA_ODYSSEY's own (one public route)
  5: AngleProfile(5, -0.00075, 18.01, 3.18),      # HONDA_RIDGELINE's own
  6: AngleProfile(6, -0.001329, 17.47, 2.82),     # HONDA_PILOT's own (one public route, EPS image unrecorded)
  7: AngleProfile(7, -0.000973, 17.0, 2.53),      # HONDA_FIT's own (one public route, no highway)
}

# MEASURED (owner 11-23): on-center SR and understeer K_us from each platform's routes, in the EPS's linear unit
# (rwd-xray lab/FLEET_0x0C_LINEAR_SPEC_20261123.md "Measured understeer"; SH-2A stage3/kus, THR kefit_logs/kus_fleet, V850
# README). Of the SR-fixed and joint fits, the pair giving the smaller angle at 30 m/s, with slip = -(K_us - 1 sigma).
OWN_GEOMETRY: dict[str, OwnGeometry] = {
  CAR.ACURA_RDX_3G: OwnGeometry(16.79, 2.75, -0.00077),       # TJB, 8 routes / 74 seg (joint fit, a_y floor)
  CAR.ACURA_RDX_3G_MMR: OwnGeometry(16.79, 2.75, -0.00077),
  CAR.HONDA_CRV_5G: OwnGeometry(16.28, 2.66, -0.000782),      # TLA A220, 6 routes (SR fixed, a_y floor)
  CAR.HONDA_CIVIC: OwnGeometry(14.99, 2.70, -0.000448),       # TEG A010, 16 routes / 533 seg (SR fixed)
  CAR.HONDA_CIVIC_BOSCH: OwnGeometry(16.0, 2.70, -0.000638),  # TGG A120 6 routes + TBA C020 1 route (SR fixed)
  CAR.HONDA_INSIGHT: OwnGeometry(17.66, 2.70, -0.00074),      # TXM, 1 route (joint fit)
  CAR.HONDA_RIDGELINE: OwnGeometry(18.01, 3.18, -0.00075),    # T6Z A110, 132 seg (joint fit; low-speed bands confirm SR 18)
  CAR.HONDA_PILOT: OwnGeometry(17.47, 2.82, -0.001329),       # public 2017 Touring route (0x91 yaw, GPS-scaled; SR fixed, floor)
  CAR.HONDA_ODYSSEY: OwnGeometry(17.81, 3.00, -0.00035),      # public route, THR-A030 hardware (joint fit, floor)
  CAR.HONDA_FIT: OwnGeometry(17.0, 2.53, -0.000973),          # public route T5R-C030, 6-18 m/s only (SR fixed, floor)
}

CAR_ROWS: dict[str, int] = {
  CAR.ACURA_RDX_3G: 1,
  CAR.ACURA_RDX_3G_MMR: 1,
  CAR.HONDA_CRV_5G: 1,
  CAR.HONDA_INSIGHT: 1,
  CAR.HONDA_CIVIC: 2,
  CAR.HONDA_CIVIC_BOSCH: 3,
  CAR.HONDA_ODYSSEY: 4,
  CAR.HONDA_RIDGELINE: 5,
  CAR.HONDA_PILOT: 6,
  CAR.HONDA_FIT: 7,
}

ANGLE_PROFILES: dict[str, AngleProfile] = {car: PANDA_ROWS[row] for car, row in CAR_ROWS.items()}


def own_geometry(CP) -> OwnGeometry | None:
  return OWN_GEOMETRY.get(CP.carFingerprint)


def own_angle_limit(v_ego: float, geometry: OwnGeometry, accel: float = 4.0) -> float:
  """the platform's own model (deg, linear, uncapped): the EPS clamp table is this at 4.0 m/s^2"""
  v = max(v_ego, 1.0)
  return accel / v ** 2 * geometry.steer_ratio * geometry.wheelbase * (1.0 - geometry.slip_factor * v ** 2) * 57.29577951308232


def angle_profile(CP) -> AngleProfile | None:
  """The car's angle profile, None for the Clarity (profile 0, its own rule) and for cars without a row."""
  return ANGLE_PROFILES.get(CP.carFingerprint)


def safety_param_bits(profile: AngleProfile) -> int:
  return profile.index << ANGLE_PROFILE_SHIFT


def vm_angle_limit(v_ego: float, profile: AngleProfile, accel: float = MAX_LATERAL_ACCEL) -> float:
  """steering-wheel angle (deg, linear) for a lateral acceleration at speed, the panda vehicle model, capped"""
  v = max(v_ego, 1.0)
  deg = accel / v ** 2 * profile.steer_ratio * profile.wheelbase * (1.0 - profile.slip_factor * v ** 2) * 57.29577951308232
  return min(deg, MAX_ANGLE_LINEAR)
