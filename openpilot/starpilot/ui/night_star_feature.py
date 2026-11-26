"""The Night Star settings page: the fork's own settings, edited live (onroad too).

Every row here is read again while driving (the EPS rows once a second, the controller rows each refresh), except Angle
Mode (Clarity and the angle-profile cars), which picks the steering type and so applies at the next car start, and Steering Prediction Time
(Clarity only), which modeld reads when it starts and so is editable only while parked. Every calibrated EPS image
steers with LatControlHondaEps, so the controller has no row. The output low-pass bands are fixed by design and have no
row.
"""
import math

from openpilot.starpilot.saved_document import commit_exact
from openpilot.starpilot.saved_source import read_saved
from openpilot.starpilot.ui.feature_settings_state import FeatureRow

SEATBELT_KEY = "DisableSeatbeltCheck"
GRADED_KEY = "HondaGradedOverride"   # angle mode only, live with the EPS rows
ANGLE_MODE_KEY = "HondaClarityAngleMode"
LOOKAHEAD_KEY = "NrdrClarityAngleLookaheadMs"   # nrdr's name and semantics (selfdrive/modeld/clarity_lookahead.py)
OFFROAD_ONLY = frozenset((LOOKAHEAD_KEY,))
CLARITY = "HONDA_CLARITY"


def _angle_image(cp) -> bool:
  """The vehicle runs an angle image ('+' in both separator slots, EPS build 0x0C on) on a car that can steer by angle: the
  Clarity, or a car with an angle profile (opendbc angle_profiles.py). Torque-PTM images (',') never get Angle Mode."""
  from opendbc.car.honda.angle_profiles import ANGLE_PROFILES
  from opendbc.car.honda.values import is_angle_image
  if not (str(cp.carFingerprint) == CLARITY or str(cp.carFingerprint) in {str(c) for c in ANGLE_PROFILES}):
    return False
  return any(str(fw.ecu) == "eps" and is_angle_image(bytes(fw.fwVersion)) for fw in cp.carFw)

# key -> (label, reason)
BOOL_ROWS = {
  "HondaDriverAssistDuringOverride": ("Assist During Override",
                                      "Keep steering assist active while you override the wheel."),
  ANGLE_MODE_KEY: ("Angle Mode",
                   ("Steers by wheel angle through the EPS's own angle loop. Needs an angle-mode EPS image " +
                    "(39990+XXX+YYY, '+' in the part number); a torque PTM image keeps torque mode. On a Clarity with any " +
                    'other EPS firmware steering stays unavailable, so turn this off. Applies at the next start.')),
  GRADED_KEY: ("Graded Override",
               ("Angle mode: between 80 % of Override Start Torque and the Start Torque, openpilot steers more gently as "
                "your torque rises instead of keeping full strength until it lets go; at the Start Torque it lets go as "
                "before. Off by default.")),
  SEATBELT_KEY: ("Disable Seatbelt Check", "Allow engaging and staying engaged with the driver's seatbelt unlatched."),
}
# key -> (label, reason, minimum, maximum, step, unit, integer)
NUMBER_ROWS = {
  "HondaEpsAngleRateLimit": ("Steering Angle Rate Limit", "Ceiling on how fast the desired wheel angle may move. 0 turns it off.",
                             0.0, 1000.0, 10.0, "deg/s", True),
  "HondaOverrideStartTorque": ("Override Start Torque",
                               ("Driver torque that starts an override (1200 = stock; a modified EPS needs more). Angle mode: " +
                                "the straight-road value, rising to 1.28 x in sharp turns (from 45 deg)."),
                               1000.0, 3000.0, 20.0, "", True),
  "HondaOverrideEndTorque": ("Override End Torque",
                             ("The override ends once your torque stays under this for 0.1 s. Keep it well below the start " +
                              "torque. Angle mode: rises in sharp turns like the start torque."),
                             200.0, 2000.0, 20.0, "", True),
  "HondaMinSteerSpeed": ("Minimum Steer Speed", "Sends no steering torque below this speed. 0 steers down to a stop.", 0.0, 25.0, 1.0, "mph", True),
  LOOKAHEAD_KEY: ("Steering Prediction Time",
                  ("Angle mode only: how far ahead the driving model's steering action is taken, in place of the learned delay. " +
                   "0 keeps the previous timing. Only models with a timed action output use it. Change it while parked; " +
                   "applies at the next start."),
                  0.0, 400.0, 5.0, "ms", True),
  "HondaOverrideTorqueScale": ("Torque During Override", "Share of the steering command kept while you override.",
                               0.0, 100.0, 5.0, "%", True),
  # the car controller clamps both fades to 0-10 s (starpilot/car/honda/modified_eps.py)
  "HondaOverrideFadeDownSecs": ("Override Fade Down",
                                "Time to ease the steering command out when you override. 0 cuts it at once.",
                                0.0, 10.0, 0.1, "s", False),
  "HondaOverrideFadeUpSecs": ("Override Fade Up", "Time to bring the steering command back after you let go of the wheel.",
                              0.0, 10.0, 0.1, "s", False),
}
# in the order a press runs: what counts as one, the fade out, what is kept during it, the fade back in
EPS_KEYS = ("HondaOverrideStartTorque", "HondaOverrideEndTorque", "HondaOverrideFadeDownSecs", "HondaOverrideTorqueScale",
            "HondaOverrideFadeUpSecs", "HondaDriverAssistDuringOverride", "HondaMinSteerSpeed")
# torque mode only: angle mode always yields through a press (opendbc honda carcontroller), so these rows would do nothing
TORQUE_ONLY_KEYS = frozenset(("HondaOverrideFadeDownSecs", "HondaOverrideTorqueScale", "HondaDriverAssistDuringOverride"))
KEYS = frozenset((*BOOL_ROWS, *NUMBER_ROWS))


def _format(number: float, integer: bool) -> str:
  return str(int(round(number))) if integer else str(round(number, 3))


class NightStarFeature:
  def __init__(self, owner):
    self.params = owner.params
    self.authority = owner.authority
    self.vehicle_params = owner.vehicle_params
    self.vehicle_fingerprint = owner.vehicle_fingerprint

  def capability(self):
    """(fingerprint, flags, calibrated) for a Honda on a modified EPS; (fingerprint, flags, None) for an angle image with angle
    mode off (its torque mode is stock, so EPS_MODIFIED is cleared and only the Angle Mode row applies); else None."""
    cp = self.vehicle_params()
    if cp is None:
      return None
    from opendbc.car.honda.modified_eps import modified_eps
    try:
      if not modified_eps(cp):
        return (str(cp.carFingerprint), int(cp.flags), None) if _angle_image(cp) else None
      from openpilot.selfdrive.controls.lib.latcontrol_honda_eps import eps_firmware_calibration
      calibration = eps_firmware_calibration(cp)
    except (AttributeError, TypeError, ValueError):
      return None
    return str(cp.carFingerprint), int(cp.flags), calibration is not None

  def _keys(self, capability) -> tuple[str, ...]:
    keys = []
    if capability is not None and capability[2] is None:   # angle image, angle mode off: stock torque mode, only the switch back
      keys.append(ANGLE_MODE_KEY)
    elif capability is not None:
      _, _, calibrated = capability
      if calibrated:  # read by LatControlHondaEps (torque) and the honda CarController (Clarity angle mode)
        keys.append("HondaEpsAngleRateLimit")
      fingerprint, flags, _ = capability
      from opendbc.car.honda.values import HondaFlags
      angle = bool(flags & int(HondaFlags.CLARITY_ANGLE_MODE))
      keys.extend(k for k in EPS_KEYS if not (angle and k in TORQUE_ONLY_KEYS))
      if angle:
        keys.append(GRADED_KEY)
      # read once at car start (starpilot/car/honda/clarity_angle_mode.py): the Clarity on any modified image (its interlock
      # finds the build), a profile car only while it runs its angle image (angle mode on; with it off the branch above)
      if fingerprint == CLARITY or flags & int(HondaFlags.CLARITY_ANGLE_MODE):
        keys.append(ANGLE_MODE_KEY)
      if fingerprint == CLARITY:
        keys.append(LOOKAHEAD_KEY)    # read once when modeld starts; parked only
    keys.append(SEATBELT_KEY)
    return tuple(keys)

  def _saved_bool(self, key):
    raw, readable = read_saved(self.params, key, 8)
    if not readable or raw not in (None, b"0", b"1"):
      return None
    return (raw == b"1") if raw is not None else self._default_on(key)

  def _default_on(self, key) -> bool:
    # get_default_value is typed: True for a BOOL key whose default is "1" (no BOOL row defaulted on before Angle Mode)
    return self.params.get_default_value(key) in (True, "1", b"1")

  def _default(self, key) -> str:
    value = self.params.get_default_value(key)
    return "" if value is None else str(value)

  def _row(self, key, live, capability, parked=True) -> FeatureRow:
    raw, readable = read_saved(self.params, key, 32)
    allowed = live and (parked or key not in OFFROAD_ONLY)
    binding = {} if key == SEATBELT_KEY else {"capability": capability, "vehicle_fingerprint": self.vehicle_fingerprint()}
    if key in BOOL_ROWS:
      label, reason = BOOL_ROWS[key]
      value = self._saved_bool(key) if readable else None
      valid = value is not None
      return FeatureRow(key, label, ("On" if value else "Off") if valid else "Invalid saved choice", source=raw,
                        choices=("Off", "On") if valid else (), default_value="On" if self._default_on(key) else "Off",
                        available=allowed and valid, reason=reason if valid else "Invalid saved choice", **binding)
    label, reason, low, high, step, unit, integer = NUMBER_ROWS[key]
    try:
      number = float(raw.decode() if raw is not None else self._default(key))
      valid = readable and math.isfinite(number) and low <= number <= high
    except (ValueError, UnicodeDecodeError):
      number, valid = 0.0, False
    return FeatureRow(key, label, _format(number, integer) if valid else "Invalid saved value", source=raw,
                      step=step if valid else 0.0, minimum=low, maximum=high, unit=unit,
                      default_value=self._default(key) or None, available=allowed and valid,
                      reason=reason if valid else "Invalid saved value", **binding)

  def rows(self, parked):
    # these settings are live, except OFFROAD_ONLY (read at modeld start), editable only while parked
    capability = self.capability()
    live = self.authority("preferences")
    return tuple(self._row(key, live, capability, parked is True) for key in self._keys(capability))

  def apply(self, request):
    key = request.key
    capability = self.capability()
    if (key not in self._keys(capability) or request.dependencies or request.related_source is not None or
        request.display_unit or request.direction):
      return False
    if key != SEATBELT_KEY and (request.capability is None or request.capability != capability or
                                not request.vehicle_fingerprint or self.vehicle_fingerprint() != request.vehicle_fingerprint):
      return False
    if key in BOOL_ROWS:
      if request.value not in ("Off", "On") or request.expected not in (None, b"0", b"1"):
        return False
      raw = b"1" if request.value == "On" else b"0"
    else:
      _, _, low, high, _, _, integer = NUMBER_ROWS[key]
      try:
        number = float(request.value)
      except ValueError:
        return False
      if not math.isfinite(number) or not low <= number <= high:   # off-grid is fine: the Clarity saved 219 deg/s
        return False
      if key == LOOKAHEAD_KEY and int(number) % 5 != 0:   # 0 or 5-400 ms in steps of 5, as nrdr
        return False
      raw = _format(number, integer).encode()

    if key in OFFROAD_ONLY and not self.params.get_bool("IsOffroad"):
      return False

    def authorized():
      return (self.authority("preferences") and self.capability() == capability and
              (key == SEATBELT_KEY or self.vehicle_fingerprint() == request.vehicle_fingerprint))

    result = commit_exact(self.params, key=key, max_bytes=32, expected=request.expected, raw=raw,
                          authorized=authorized, temp_prefix=".night-star-")
    return result.committed and result.verified
