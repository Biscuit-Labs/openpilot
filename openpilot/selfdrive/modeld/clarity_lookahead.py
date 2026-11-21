"""Steering Prediction Time (port of nrdr/openpilot 25f309ef "modeld: allow an absolute steering horizon on angle PTM
Clarity"): an absolute lateral action horizon for a Clarity in angle mode, in place of the runner's timing.

Setting NrdrClarityAngleLookaheadMs (INT, default 0 = "Previous": the runner's own timing), 5-400 ms in steps of 5, the
same name and semantics as nrdr so the two forks stay portable. Read once when modeld starts (offroad-only).

Applies only when all of these hold, otherwise every model input is exactly what it was:
  - the car is a Honda Clarity steering by angle (Angle Mode on, modified EPS firmware)
  - the setting is a valid value (5..400, step 5)
  - the running model has a timed action head: it outputs an action and takes an action_t input (a plan-only model
    reads its plan at lat_action_t and is left alone)
Then lateral_model_times returns (manual, manual): action_t's lateral horizon and the delay in lateral_control_params
both become the manual value (nrdr's modeld_v2 variant). nrdr gates on LagdToggle off (no live delay learning); this
branch has no such toggle: in Clarity angle mode the model's lateral delay is always lagd's learned delay
(latcontrol_honda_eps.lateral_delay_schedule is None there), so a non-zero setting is the choice to replace it.
"""
KEY = "NrdrClarityAngleLookaheadMs"
VALID_MS = range(5, 401, 5)


def clarity_manual_lookahead(params, CP) -> float | None:
  """Final lateral action horizon in seconds, or None to retain the runner's timing."""
  if CP.brand != "honda" or CP.carFingerprint != "HONDA_CLARITY" or CP.steerControlType != "angle":
    return None
  try:
    ms = params.get(KEY, return_default=True)
  except Exception:   # a params library built before this key: the setting does not exist, so it is off
    return None
  return ms / 1000 if type(ms) is int and ms in VALID_MS else None


def timed_action_head(model) -> bool:
  """The model outputs an action and takes an action_t input (bundled, catalog and Jetlink runners alike)."""
  slices = getattr(model, "output_slices", None)
  npy = getattr(model, "npy", None)
  return isinstance(slices, dict) and "action" in slices and isinstance(npy, dict) and "action_t" in npy


def lateral_model_times(manual: float | None, timed_head: bool, lat_delay: float,
                        frame_delay: float, action_delay: float) -> tuple[float, float]:
  """(lateral delay for lateral_control_params and model.lat_delay, action_t lateral horizon) for this frame."""
  if manual is not None and timed_head:
    return manual, manual
  return lat_delay, lat_delay + frame_delay + action_delay
