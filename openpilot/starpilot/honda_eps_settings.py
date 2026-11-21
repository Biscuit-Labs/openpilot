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
  "HondaClarityAngleMode", "HondaClarityAngleCap3", "HondaClarityAngleHoldOverride", "HondaOverrideFadeUpReset125",
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


FADE_UP_RESET_KEY = "HondaOverrideFadeUpReset125"


def reset_override_fade_up_once(params) -> bool:
  """Once per device: clear the saved Override Fade Up so the 1.25 s default applies (11-20: the default moved from
  0.5 s, and a saved 0 used to mean a hidden 1.25 s authority climb; 0 now means at once). Returns True if it cleared."""
  if params.get_bool(FADE_UP_RESET_KEY):
    return False
  cleared = params.get("HondaOverrideFadeUpSecs") is not None
  params.remove("HondaOverrideFadeUpSecs")
  params.put_bool(FADE_UP_RESET_KEY, True, block=True)
  return cleared
