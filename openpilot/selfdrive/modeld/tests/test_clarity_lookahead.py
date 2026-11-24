"""Steering Prediction Time (NrdrClarityAngleLookaheadMs, port of nrdr 25f309ef). Exercises modeld's actual frame-input
block (extracted from main() by AST) without a GPU or a vehicle: with the setting off, on any other car, in torque
mode, or on a plan-only model, every model input must equal what the runner built before the port (the block with its
original lat_action_t line restored)."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from openpilot.selfdrive.modeld.clarity_lookahead import KEY, clarity_manual_lookahead, lateral_model_times, timed_action_head

MODELD = Path(__file__).resolve().parents[1] / "modeld.py"
NEW_LINE = "lat_delay, lat_action_t = lateral_model_times(manual_lookahead, timed_action_head(model), lat_delay, frame_delay, action_delay)"
OLD_LINE = "lat_action_t = lat_delay + frame_delay + action_delay"


class Params(dict):
  def get(self, key, return_default=False):
    return super().get(key)

  def get_bool(self, key):
    return bool(self.get(key))


class MissingKeyParams(Params):
  def get(self, key, return_default=False):
    raise KeyError(key)   # a params library built before the key: UnknownKeyName


CLARITY_ANGLE = NS(brand="honda", carFingerprint="HONDA_CLARITY", steerControlType="angle")


@pytest.mark.parametrize("ms", [0, None, -5, 1, 7, True, 405, 5, 225, 400, 5.0, "225"])
def test_horizon_only_for_a_valid_setting_on_an_angle_clarity(ms):
  params = Params({KEY: ms})
  assert clarity_manual_lookahead(params, CLARITY_ANGLE) == (ms / 1000 if type(ms) is int and ms in (5, 225, 400) else None)
  for field, value in (("brand", "toyota"), ("carFingerprint", "HONDA_CIVIC"), ("steerControlType", "torque")):
    assert clarity_manual_lookahead(params, NS(**(vars(CLARITY_ANGLE) | {field: value}))) is None


def test_unknown_key_is_off():
  assert clarity_manual_lookahead(MissingKeyParams(), CLARITY_ANGLE) is None


def test_timed_action_head():
  assert timed_action_head(NS(output_slices={"action": 0, "plan": 1}, npy={"action_t": 0}))
  assert not timed_action_head(NS(output_slices={"plan": 1}, npy={"action_t": 0}))        # plan-only model
  assert not timed_action_head(NS(output_slices={"action": 0}, npy={"desire": 0}))        # no action_t input
  assert not timed_action_head(NS())                                                      # unknown runner


def _frame_block(source: str):
  tree = ast.parse(source)
  main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")

  def assigned(n, key):
    return isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == key

  loop, = [n for n in ast.walk(main) if isinstance(n, ast.While) and any(assigned(s, "frame_delay") for s in n.body)]
  start = next(i for i, n in enumerate(loop.body) if assigned(n, "frame_delay"))
  end = next(i for i, n in enumerate(loop.body[start:], start) if assigned(n, "model.frame_drop_ratio"))
  return compile(ast.Module(loop.body[start:end + 1], type_ignores=[]), str(MODELD), "exec")


class Catalog(NS):
  pass


def _run(block, model, manual, cls_catalog, jetlink):
  prev_action = NS(desiredCurvature=0.01, desiredAcceleration=0.2)
  sm = {"carControl": NS(latActive=True), "controlsState": NS(curvature=0.02)}
  ctx = {"np": np, "DT_MDL": 0.05, "CatalogModelState": cls_catalog, "jetlink_model": jetlink, "model": model, "sm": sm,
         "prev_action": prev_action, "lat_delay": 0.15, "long_delay": 0.5, "v_ego": 12.0, "vec_desire": np.zeros(8),
         "traffic_convention": np.array([1., 0.]), "frame_drop_ratio": 0.0, "manual_lookahead": manual,
         "lateral_model_times": lateral_model_times, "timed_action_head": timed_action_head}
  exec(block, ctx)
  return ctx


def test_frame_inputs_unchanged_unless_the_horizon_applies():
  source = MODELD.read_text()
  assert source.count(NEW_LINE) == 1
  new_block, old_block = _frame_block(source), _frame_block(source.replace(NEW_LINE, OLD_LINE))
  timed = {"output_slices": {"action": 0, "plan": 1}, "npy": {"action_t": 0}}
  plan = {"output_slices": {"plan": 1}, "npy": {"action_t": 0}}
  cases = []
  for kind, attrs in (("timed", timed), ("plan", plan)):
    for runner in ("bundled", "catalog", "jetlink"):
      for manual in (None, 0.3):
        cases.append((kind, attrs, runner, manual))
  checked = applied = 0
  for kind, attrs, runner, manual in cases:
    outs = []
    for block in (new_block, old_block):
      model = (Catalog if runner == "catalog" else NS)(**attrs)
      outs.append(_run(block, model, manual, Catalog, model if runner == "jetlink" else object()))
    new, old = outs
    applies = manual is not None and kind == "timed"
    if not applies:
      # setting off / not an angle Clarity (manual None), or a plan-only model: every input and the action horizon equal
      assert new["inputs"].keys() == old["inputs"].keys()
      for k in old["inputs"]:
        np.testing.assert_array_equal(new["inputs"][k], old["inputs"][k], err_msg=f"{kind} {runner} {manual} {k}")
      assert new["lat_action_t"] == old["lat_action_t"] and new["model"].lat_delay == old["model"].lat_delay
      checked += 1
    else:
      # the knob: action_t's lateral horizon and lateral_control_params' delay become the manual value
      assert new["inputs"]["action_t"] == pytest.approx([0.3, 0.575])
      assert old["inputs"]["action_t"] == pytest.approx([0.225, 0.575])   # 0.15 + 0.05 + 0.025
      assert new["model"].lat_delay == pytest.approx(0.3) and old["model"].lat_delay == pytest.approx(0.15)
      if runner != "bundled":
        assert new["inputs"]["lateral_control_params"] == pytest.approx([12.0, 0.3])
        assert old["inputs"]["lateral_control_params"] == pytest.approx([12.0, 0.15])
      applied += 1
  assert checked == 9 and applied == 3


@pytest.mark.parametrize("ms", [5, 100, 400])
def test_horizon_moves_action_t_and_lateral_control_params(ms):
  block = _frame_block(MODELD.read_text())
  model = Catalog(output_slices={"action": 0}, npy={"action_t": 0})
  ctx = _run(block, model, ms / 1000, Catalog, object())
  assert ctx["inputs"]["action_t"] == pytest.approx([ms / 1000, 0.575])
  assert ctx["inputs"]["lateral_control_params"] == pytest.approx([12.0, ms / 1000])
  assert ctx["lat_action_t"] == pytest.approx(ms / 1000)
