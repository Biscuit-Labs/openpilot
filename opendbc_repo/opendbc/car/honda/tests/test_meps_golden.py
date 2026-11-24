"""Golden frames: every 0xE4 byte the Clarity angle-mode CarController sends in scripted scenarios, protocol v2 (0x6A4
layout 4, build 0x0B), replayed byte for byte.

History: the v2 recording was made when v1 and v2 coexisted, and v2 had been checked against the post-parity v1
recording (personal branch 562952a102): bytes 0-2 identical frame by frame, byte 3 = MODE 1 | AUTH with AUTH = 15 - CUT.
When v1 was removed, the scenarios only v1 had (inactive, engage_wheel_moving, loop_not_running_fault) were added to v2
after the same check against the v1 recording, and the v1 recording was dropped.

Regenerate (only after a deliberate behaviour change, and review the diff): MEPS_GOLDEN_REGEN=1 pytest test_meps_golden.py
"""
import dataclasses
import json
import os

import pytest

from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
from opendbc.car.honda.tests import test_clarity_angle_mode as T
from opendbc.car.honda.tests.test_eps_cal_status import Feed, v4

GOLDEN = os.path.join(os.path.dirname(__file__), "meps_golden_frames.json")


def _settings(ci, **kw):
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, **kw)})()


def _start(status=None, **settings):
  T.ANGLE[0] = True
  ci = T.clarity()
  if settings:
    _settings(ci, **settings)
  f = Feed(ci)
  f.run(status or [v4(counter=k % 4) for k in range(8)])
  return ci, f


def _frames(ci, steps):
  """steps: (lat, desired, measured, v, pressed); returns the 0xE4 frames as hex."""
  return [T.e4(ci, lat, des, meas, v=v, pressed=pressed)[1].hex() for lat, des, meas, v, pressed in steps]


def scenario_inactive():
  ci, _ = _start()
  return _frames(ci, [(False, 0.0, 0.0, 10.0, False)] * 20)


def scenario_engage_straight():
  ci, _ = _start()
  return _frames(ci, [(False, 0.0, 0.0, 20.0, False)] + [(True, 2.0, 0.0, 20.0, False)] * 200)


def scenario_curve_at_limit():
  ci, _ = _start()
  return _frames(ci, [(False, 0.0, 0.0, 15.0, False)] + [(True, 80.0, 0.0, 15.0, False)] * 300)


def scenario_override_plan_target_and_ramp_back():
  ci, _ = _start()
  steps = [(False, 0.0, 0.0, 20.0, False)] + [(True, 5.0, 0.0, 20.0, False)] * 150
  steps += [(True, 5.0, -8.0, 20.0, True)] * 80 + [(True, 5.0, -8.0, 20.0, False)] * 160
  return _frames(ci, steps)


def scenario_engage_wheel_moving():
  ci, _ = _start()
  steps = [(False, 0.0, 0.0, 20.0, False)]
  steps += [(True, 3.0, 0.6 * k, 20.0, False) for k in range(30)] + [(True, 3.0, 18.0, 20.0, False)] * 70
  return _frames(ci, steps)


def scenario_engage_beyond_limit_waits():
  ci, _ = _start()
  steps = [(False, 0.0, 40.0, 30.0, False)] + [(True, 5.0, 40.0, 30.0, False)] * 30
  steps += [(True, 5.0, 40.0 - k, 30.0, False) for k in range(1, 35)] + [(True, 5.0, 5.0, 30.0, False)] * 40
  return _frames(ci, steps)


def scenario_loop_not_running_fault():
  ci, f = _start()
  out = _frames(ci, [(False, 0.0, 0.0, 10.0, False), (True, 0.0, 0.0, 10.0, False)])
  f.run([v4(steering=False, reason=1, counter=k % 4) for k in range(8, 14)])
  out += _frames(ci, [(True, 0.0, 0.0, 10.0, False)] * 5)
  f.run([v4(steering=False, reason=1, counter=k % 4) for k in range(2, 4)])
  out += _frames(ci, [(True, 0.0, 0.0, 10.0, False)] * 5)
  return out


SCENARIOS = {name[len("scenario_"):]: fn for name, fn in globals().items() if name.startswith("scenario_")}


def record(scenarios=None):
  try:
    return {name: fn() for name, fn in (scenarios or SCENARIOS).items()}
  finally:
    T.ANGLE[0] = False


def _compare(golden, frames):
  assert set(golden) == set(frames)
  for name in golden:
    assert len(frames[name]) == len(golden[name]), name
    for i, (got, want) in enumerate(zip(frames[name], golden[name], strict=True)):
      assert got == want, f"{name} frame {i}: {got} != {want}"


def test_golden_frames_unchanged():
  frames = record()
  if os.environ.get("MEPS_GOLDEN_REGEN") == "1":
    with open(GOLDEN, "w") as f:
      json.dump({"source": "protocol v2 (0x6A4 layout 4, build 0x0B), meps/protocol.py; see the module docstring", "v2": frames}, f, indent=0)
    pytest.skip("regenerated")
  _compare(json.load(open(GOLDEN))["v2"], frames)


def test_golden_frames_follow_the_wire_rules():
  for name, frames in json.load(open(GOLDEN))["v2"].items():
    for h in frames:
      b = bytes.fromhex(h)
      mode, reserved, request, payload = b[3] & 3, (b[3] >> 2) & 3, bool(b[2] & 0x80), bool(b[2] & 0x20)
      assert mode == 1 and reserved == 0 and payload == request, (name, h)


def test_golden_scenarios_exercise_what_they_claim():
  golden = json.load(open(GOLDEN))["v2"]

  def active(h):
    return (int(h[4:6], 16) & 0xA0) == 0xA0
  assert not any(active(h) for h in golden["inactive"])
  assert all(active(h) for h in golden["engage_straight"][1:])
  assert any(h[6] == "0" for h in golden["override_plan_target_and_ramp_back"][151:231])   # AUTH 0 while pressed
  assert not any(active(h) for h in golden["engage_beyond_limit_waits"][1:31])         # waits beyond the limit
  assert any(active(h) for h in golden["engage_beyond_limit_waits"][-40:])
  assert not any(active(h) for h in golden["loop_not_running_fault"][2:7])
