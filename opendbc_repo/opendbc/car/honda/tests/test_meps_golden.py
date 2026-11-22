"""Golden frames: every 0xE4 byte the Clarity angle-mode CarController sends in scripted scenarios, recorded from the
post-parity v1 behaviour (personal branch 562952a102) before the protocol-v2 change, and replayed byte for byte.
Protocol v2 (meps/) must leave every v1 scenario identical; v2 scenarios are recorded separately once v2 exists.

Regenerate (only after a deliberate behaviour change, and review the diff): MEPS_GOLDEN_REGEN=1 pytest test_meps_golden.py
(v1 and v2) or MEPS_GOLDEN_REGEN=v2 (v2 only, leaves the v1 recording untouched).
"""
import dataclasses
import json
import os

import pytest

from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
from opendbc.car.honda.tests import test_clarity_angle_mode as T
from opendbc.car.honda.tests.test_eps_cal_status import Feed

GOLDEN = os.path.join(os.path.dirname(__file__), "meps_golden_frames.json")


def _settings(ci, **kw):
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, **kw)})()


def _start(build=0x0A, status=None, **settings):
  T.ANGLE[0] = True
  ci = T.clarity()
  if settings:
    _settings(ci, **settings)
  f = Feed(ci)
  f.run(status or [T.v3(build=build, counter=k % 4) for k in range(8)])
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


def scenario_curve_at_limit_mode3():
  ci, _ = _start()
  return _frames(ci, [(False, 0.0, 0.0, 15.0, False)] + [(True, 80.0, 0.0, 15.0, False)] * 300)


def scenario_curve_at_limit_mode4():
  status3 = [T.v3(build=0x0A, counter=k % 4) for k in range(8)]
  ci, f = _start(status=status3, angle_cap3=True)
  T.e4(ci, False, 0.0, 0.0, v=15.0)                       # lateral off: the profile switch to mode 4 is requested
  f.run([T.v3(active=4, requested=4, build=0x0A, counter=k % 4) for k in range(8)])
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
  f.run([T.v3(build=0x0A, running=False, counter=k % 4) for k in range(8, 14)])
  out += _frames(ci, [(True, 0.0, 0.0, 10.0, False)] * 5)
  f.run([T.v3(build=0x0A, running=False, counter=k % 4) for k in range(2, 4)])
  out += _frames(ci, [(True, 0.0, 0.0, 10.0, False)] * 5)
  return out


def _start_v2(**settings):
  from opendbc.car.honda.tests.test_meps_v2 import v4
  return _start(status=[v4(counter=k % 4) for k in range(8)], **settings)


def v2scenario_engage_straight():
  ci, _ = _start_v2()
  return _frames(ci, [(False, 0.0, 0.0, 20.0, False)] + [(True, 2.0, 0.0, 20.0, False)] * 200)


def v2scenario_curve_at_limit():
  ci, _ = _start_v2()
  return _frames(ci, [(False, 0.0, 0.0, 15.0, False)] + [(True, 80.0, 0.0, 15.0, False)] * 300)


def v2scenario_override_plan_target_and_ramp_back():
  ci, _ = _start_v2()
  steps = [(False, 0.0, 0.0, 20.0, False)] + [(True, 5.0, 0.0, 20.0, False)] * 150
  steps += [(True, 5.0, -8.0, 20.0, True)] * 80 + [(True, 5.0, -8.0, 20.0, False)] * 160
  return _frames(ci, steps)


def v2scenario_engage_beyond_limit_waits():
  ci, _ = _start_v2()
  steps = [(False, 0.0, 40.0, 30.0, False)] + [(True, 5.0, 40.0, 30.0, False)] * 30
  steps += [(True, 5.0, 40.0 - k, 30.0, False) for k in range(1, 35)] + [(True, 5.0, 5.0, 30.0, False)] * 40
  return _frames(ci, steps)


SCENARIOS = {name[len("scenario_"):]: fn for name, fn in globals().items() if name.startswith("scenario_")}
V2_SCENARIOS = {name[len("v2scenario_"):]: fn for name, fn in globals().items() if name.startswith("v2scenario_")}


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


def test_v1_golden_frames_unchanged():
  frames = record()
  if os.environ.get("MEPS_GOLDEN_REGEN") == "1":
    data = json.load(open(GOLDEN)) if os.path.exists(GOLDEN) else {}
    data.update({"source": "personal branch 562952a102 (post-parity v1), recorded before protocol v2", "v1": frames})
    with open(GOLDEN, "w") as f:
      json.dump(data, f, indent=0)
    pytest.skip("regenerated")
  _compare(json.load(open(GOLDEN))["v1"], frames)


def test_v2_golden_frames_unchanged():
  frames = record(V2_SCENARIOS)
  if os.environ.get("MEPS_GOLDEN_REGEN") in ("1", "v2"):
    data = json.load(open(GOLDEN))
    data.update({"v2_source": "protocol v2 (0x6A4 layout 4, build 0x0B), meps/protocol.py", "v2": frames})
    with open(GOLDEN, "w") as f:
      json.dump(data, f, indent=0)
    pytest.skip("regenerated")
  _compare(json.load(open(GOLDEN))["v2"], frames)


def test_v2_golden_frames_follow_the_wire_rules():
  for name, frames in json.load(open(GOLDEN))["v2"].items():
    for h in frames:
      b = bytes.fromhex(h)
      mode, reserved, request, payload = b[3] & 3, (b[3] >> 2) & 3, bool(b[2] & 0x80), bool(b[2] & 0x20)
      assert mode == 1 and reserved == 0 and payload == request, (name, h)


def test_golden_scenarios_exercise_what_they_claim():
  golden = json.load(open(GOLDEN))["v1"]

  def active(h):
    return (int(h[4:6], 16) & 0xA0) == 0xA0
  assert not any(active(h) for h in golden["inactive"])
  assert all(active(h) for h in golden["engage_straight"][1:])
  assert {h[6:8] for h in golden["curve_at_limit_mode4"][1:]} & {"09", "f9"}          # mode 4 byte 3
  assert any(h[6] == "f" for h in golden["override_plan_target_and_ramp_back"][151:231])   # cut 15 while pressed
  assert not any(active(h) for h in golden["engage_beyond_limit_waits"][1:31])         # waits beyond the limit
  assert any(active(h) for h in golden["engage_beyond_limit_waits"][-40:])
  assert not any(active(h) for h in golden["loop_not_running_fault"][2:7])


def test_v2_differs_from_v1_only_in_byte3():
  # same scenario, same sender: bytes 0-2 identical frame by frame; byte 3 = MODE 1 | AUTH with AUTH = 15 - v1's CUT
  data = json.load(open(GOLDEN))
  pairs = {"engage_straight": "engage_straight", "curve_at_limit_mode3": "curve_at_limit",
           "override_plan_target_and_ramp_back": "override_plan_target_and_ramp_back",
           "engage_beyond_limit_waits": "engage_beyond_limit_waits"}
  for v1_name, v2_name in pairs.items():
    v1, v2 = data["v1"][v1_name], data["v2"][v2_name]
    assert len(v1) == len(v2), v1_name
    for i, (a, b) in enumerate(zip(v1, v2, strict=True)):
      a, b = bytes.fromhex(a), bytes.fromhex(b)
      assert a[0:3] == b[0:3], (v1_name, i)
      assert a[3] & 0x0F == 0x07 and b[3] == ((15 - (a[3] >> 4)) << 4) | 0x01, (v1_name, i, a.hex(), b.hex())
