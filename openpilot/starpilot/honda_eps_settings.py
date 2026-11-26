"""Honda EPS settings that carry across StarPilot 7.0's first start.

7.0's first start (state_migration.prepare_manager_start) archives every saved setting outside OPERATIONAL_KEYS and
starts fresh. The Honda EPS tuning below is kept instead: it is per-car calibration, not a StarPilot preference.
DisableSeatbeltCheck rides along: it is the driver's standing choice, and losing it silently would bring the check back.
Settings saved under vfn's older names are renamed first, as vfn's manager does, so they are not lost as unknown
keys.
"""
from pathlib import Path

# old name -> current name, as vfn's manager renamed them. The old names are the literal keys still saved on cars, so
# they stay spelled exactly as they were.
HONDA_EPS_KEY_RENAMES = {
  "NrdrLatAngleRateLimit": "HondaEpsAngleRateLimit",
  "NrdrMinSteerSpeed": "HondaMinSteerSpeed",
}

# The single Driver Override Threshold (2026-11-26: split in two). Angle mode scaled it 0.78 near centre and ended a press
# under 0.4 of that, so a saved value X becomes Override Start Torque 0.78 X and Override End Torque 0.312 X: the same
# levels near centre, and the same 1.0 X / 0.4 X from 45 deg (opendbc modified_eps.ANGLE_THRESHOLD_SCALE 1.28).
OLD_OVERRIDE_THRESHOLD_KEYS = ("HondaDriverOverrideThreshold", "NrdrDriverOverrideThreshold")   # current name first
OVERRIDE_START_KEY, OVERRIDE_END_KEY = "HondaOverrideStartTorque", "HondaOverrideEndTorque"
OVERRIDE_START_FRACTION, OVERRIDE_END_FRACTION = 0.78, 0.312

# Retired settings (2026-11-24): nothing reads them any more and no settings page showed them, so their saved files are
# deleted at start, under vfn's old names and their later names alike. The values they held were the defaults now
# fixed in code (torque output low-pass on, 0.07/0.05/0.01 s; PID trims 1/1/1, 0.2/1/0, 1/1/1; delta limiter off).
RETIRED_HONDA_EPS_KEYS = (
  "HondaTorqueLowPassFilter", "HondaLpfTauLowSpeed", "HondaLpfTauStandard", "HondaLpfTauHighway", "NrdrLatUseFirmwareVgr",
  "HondaTorqueOutputLowPassFilter", "HondaTorqueOutputLpfTauLowSpeed", "HondaTorqueOutputLpfTauStandard",
  "HondaTorqueOutputLpfTauHighway", "HondaEpsFirmwareVgr", "HondaClarityAngleCap3",
  "HondaSteerDeltaLimiter", "HondaSteerDeltaUp", "HondaSteerDeltaDown",
  *(f"Lat{gain}Scale{band}" for gain in "PIF" for band in ("LowSpeed", "Standard", "Highway")),
  # 2026-11-26: protocol v3 always yields through an override (no setting); the single override threshold became
  # Override Start / End Torque (migrated first, migrate_override_threshold)
  "HondaClarityAngleHoldOverride", *OLD_OVERRIDE_THRESHOLD_KEYS,
)

HONDA_EPS_PRESERVED_KEYS = frozenset({
  "HondaEpsAngleRateLimit", "HondaOverrideFadeUpSecs",
  "HondaOverrideStartTorque", "HondaOverrideEndTorque",
  "HondaMinSteerSpeed", "HondaOverrideFadeDownSecs", "HondaOverrideTorqueScale",
  "HondaDriverAssistDuringOverride",
  "HondaClarityAngleMode", "HondaAngleDefaultsReset",
  "DisableSeatbeltCheck",
})


def migrate_honda_eps_param_names(params) -> list[str]:
  """Move each old-name value to its current name unless that is already set, then remove the old file."""
  renamed = []
  for old_key, new_key in HONDA_EPS_KEY_RENAMES.items():
    old_path = Path(params.get_param_path(old_key))
    try:
      raw = old_path.read_bytes()
    except OSError:
      continue
    if raw and params.get(new_key) is None:
      try:
        params.put(new_key, params.cpp2python(new_key, raw), block=True)
        renamed.append(f"{old_key}->{new_key}")
      except (TypeError, ValueError, UnicodeError):
        pass
    try:
      old_path.unlink()
    except OSError:
      pass
  renamed += migrate_override_threshold(params)
  for key in RETIRED_HONDA_EPS_KEYS:
    try:
      Path(params.get_param_path(key)).unlink()
    except OSError:
      pass
  return renamed


def migrate_override_threshold(params) -> list[str]:
  """A saved single override threshold -> Override Start / End Torque, unless either is already set. The old files are
  deleted with the retired keys."""
  for old_key in OLD_OVERRIDE_THRESHOLD_KEYS:
    try:
      raw = Path(params.get_param_path(old_key)).read_bytes()
    except OSError:
      continue
    try:
      value = float(raw.decode().strip())
    except (UnicodeError, ValueError):
      return []
    if value <= 0 or params.get(OVERRIDE_START_KEY) is not None or params.get(OVERRIDE_END_KEY) is not None:
      return []
    params.put(OVERRIDE_START_KEY, int(round(OVERRIDE_START_FRACTION * value)), block=True)
    params.put(OVERRIDE_END_KEY, int(round(OVERRIDE_END_FRACTION * value)), block=True)
    return [f"{old_key}->{OVERRIDE_START_KEY},{OVERRIDE_END_KEY}"]
  return []


ANGLE_DEFAULTS_RESET_KEY = "HondaAngleDefaultsReset"
# the override settings angle mode was tuned with (Override Fade Up 1.25 s, Fade Down 0.0 s, Override Start / End Torque
# 1560 / 624): clearing a saved value brings back the registered default (params_keys.h)
ANGLE_DEFAULT_KEYS = ("HondaOverrideFadeUpSecs", "HondaOverrideFadeDownSecs", OVERRIDE_START_KEY, OVERRIDE_END_KEY)


def reset_angle_defaults_once(params) -> list[str]:
  """Once per device: clear the saved override settings so the angle-hold defaults apply. A value set afterwards is kept.
  Returns the keys that held a saved value."""
  if params.get_bool(ANGLE_DEFAULTS_RESET_KEY):
    return []
  cleared = [key for key in ANGLE_DEFAULT_KEYS if params.get(key) is not None]
  for key in ANGLE_DEFAULT_KEYS:
    params.remove(key)
  params.put_bool(ANGLE_DEFAULTS_RESET_KEY, True, block=True)
  return cleared
