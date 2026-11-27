"""Startup choice for the Clarity angle-mode EPS build (opendbc car/honda/clarity_angle_mode.py).

HondaClarityAngleMode (Night Star / Galaxy row "Angle Mode", default on) is read once, in card's pre-create hook, before
the car interface, its controller and the first CarParams exist: steerControlType cannot change while driving, so a
change takes effect at the next car start. Unreadable setting -> the default (on).

On a Clarity the setting only applies once the EPS has announced an angle-capable build (HondaAngleEpsAnnounced, written by
AngleAnnouncement below), or its part number marks an angle image ('+'). Without that, the default "on" would put a Clarity
that runs a stock or torque PTM image into angle mode, where the missing 0x6A4 faults "no_status" and nothing steers.
"""
import time

from opendbc.car.honda.clarity_angle_mode import ANGLE_MODE_PARAM, angle_image, apply_angle_mode
from opendbc.car.honda.modified_eps import modified_eps
from opendbc.car.honda.values import CAR

DEFAULT = True
ANNOUNCED_PARAM = "HondaAngleEpsAnnounced"   # BOOL, default 0: saved while a Clarity EPS reports an angle-capable build
# A start with the EPS present and driving but no 0x6A4 layout-4 frame of a V3 build at all is a stock or torque PTM image
# (an angle build sends 0x6A4 at 50 Hz from boot): the saved announcement is cleared after this much driving
CLEAR_AFTER_DRIVE_S = 300.0
CLEAR_MIN_SPEED = 3.0   # m/s


def requested(params) -> bool:
  try:
    value = params.get(ANGLE_MODE_PARAM, return_default=True)
  except Exception:   # unknown key (params library not rebuilt), unreadable file
    return DEFAULT
  return DEFAULT if value is None else bool(value)


def announced(params) -> bool:
  try:
    return bool(params.get(ANNOUNCED_PARAM, return_default=True))
  except Exception:   # unknown key (params library not rebuilt), unreadable file
    return False


def prepare(cp, params):
  want = requested(params)
  if want and cp.carFingerprint == CAR.HONDA_CLARITY and not angle_image(cp) and not announced(params):
    want = False   # no angle-capable EPS announced: a stock or torque PTM image keeps torque mode (no 0x6A4 interlock fault)
  return apply_angle_mode(cp, want)


class AngleAnnouncement:
  """card: saves HondaAngleEpsAnnounced from the car's EpsCalStatus (the 0x6A4 interlock runs on a modified Clarity in angle
  or torque mode alike, so the announcement is seen whatever the Angle Mode setting says).
  Set: the first valid 0x6A4 layout-4 frame with a build in meps.protocol.V3_BUILDS (EpsCalStatus.angle_capable).
  Cleared: after CLEAR_AFTER_DRIVE_S of driving (valid CAN, above CLEAR_MIN_SPEED) in one car start with no such frame; the
  EPS being flashed back to a stock or torque PTM image. Seeing the announcement again in that start cancels the count."""

  def __init__(self, params, clock=time.monotonic):
    self.params = params
    self.clock = clock
    self.saved = announced(params)
    self.drive_s = 0.0
    self.last = None

  @classmethod
  def create(cls, cp, params):
    return cls(params) if modified_eps(cp) and cp.carFingerprint == CAR.HONDA_CLARITY else None

  def update(self, eps_cal_status, v_ego: float, can_valid: bool) -> None:
    now = self.clock()
    dt = 0.0 if self.last is None else min(max(now - self.last, 0.0), 0.1)
    self.last = now
    if not getattr(eps_cal_status, "enabled", False):
      return
    if eps_cal_status.angle_capable:
      self.drive_s = 0.0
      if not self.saved:
        self._save(True)
    elif self.saved and can_valid and v_ego > CLEAR_MIN_SPEED:
      self.drive_s += dt
      if self.drive_s >= CLEAR_AFTER_DRIVE_S:
        self._save(False)

  def _save(self, value: bool) -> None:
    try:
      self.params.put_bool(ANNOUNCED_PARAM, value)
      self.saved = value
    except Exception:   # unreadable params: retry on the next frame
      pass
