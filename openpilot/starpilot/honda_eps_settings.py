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
  "HondaTorqueLowPassFilter": "HondaTorqueOutputLowPassFilter",
  "HondaLpfTauLowSpeed": "HondaTorqueOutputLpfTauLowSpeed",
  "HondaLpfTauStandard": "HondaTorqueOutputLpfTauStandard",
  "HondaLpfTauHighway": "HondaTorqueOutputLpfTauHighway",
  "NrdrLatUseFirmwareVgr": "HondaEpsFirmwareVgr",
  "NrdrLatAngleRateLimit": "HondaEpsAngleRateLimit",
  "NrdrDriverOverrideThreshold": "HondaDriverOverrideThreshold",
  "NrdrMinSteerSpeed": "HondaMinSteerSpeed",
}

HONDA_EPS_PRESERVED_KEYS = frozenset({
  "HondaEpsAngleRateLimit", "HondaEpsFirmwareVgr", "HondaOverrideFadeUpSecs",
  "HondaTorqueOutputLowPassFilter", "HondaTorqueOutputLpfTauLowSpeed", "HondaTorqueOutputLpfTauStandard",
  "HondaTorqueOutputLpfTauHighway",
  "LatPScaleLowSpeed", "LatPScaleStandard", "LatPScaleHighway",
  "LatIScaleLowSpeed", "LatIScaleStandard", "LatIScaleHighway",
  "LatFScaleLowSpeed", "LatFScaleStandard", "LatFScaleHighway",
  "HondaDriverOverrideThreshold", "HondaMinSteerSpeed", "HondaOverrideFadeDownSecs", "HondaOverrideTorqueScale",
  "HondaDriverAssistDuringOverride", "HondaSteerDeltaLimiter", "HondaSteerDeltaUp", "HondaSteerDeltaDown",
  "HondaClarityAngleMode", "HondaClarityAngleCap3", "HondaClarityAngleHoldOverride", "HondaAngleDefaultsReset",
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
  return renamed


ANGLE_DEFAULTS_RESET_KEY = "HondaAngleDefaultsReset"
# the override settings the angle hold was tuned with (Override Fade Up 1.25 s, Fade Down 0.0 s, Override Threshold 2000):
# clearing a saved value brings back the registered default (params_keys.h)
ANGLE_DEFAULT_KEYS = ("HondaOverrideFadeUpSecs", "HondaOverrideFadeDownSecs", "HondaDriverOverrideThreshold")


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
