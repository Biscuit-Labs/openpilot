"""Golden frames: every 0xE4 byte the Clarity angle-mode CarController sends in scripted scenarios, protocol v3 (0x6A4
layout 4, build 0x0E; byte 2 = DRIVE 0x4C / YIELD 0x0C / STANDBY 0x0D, byte 3 = 0), replayed byte for byte.

History: the first recording was protocol v2 (build 0x0B: request + payload bit, byte 3 = MODE | AUTH), checked frame by
frame against the post-parity v1 recording. v2 was then removed. The v3 recording of 2026-11-26 was regenerated with the
documented path below. It is NOT byte-identical to the v2 recording in the target bytes: v3 sends no authority ramp, so
the engage is the sender's effort fade over Override Fade Up (the target walks in from the wheel over about a second
instead of at the trajectory rate), the scenarios run on the linear angle (fresh 0x6A2, so the linear limits: 50.8 deg
vs 51.8 deg at 15 m/s), and the override scenario now YIELDs with the target following the wheel instead of holding the
plan. Only the scenarios with nothing to send (inactive, the waits, the fault stand-by frames) agree in bytes 0-1. The
behaviour itself is covered by test_clarity_angle_mode.py and test_meps_v3.py; this file pins it against change.

Regenerate (only after a deliberate behaviour change, and review the diff): MEPS_GOLDEN_REGEN=1 pytest test_meps_golden.py
"""
import dataclasses
import json
import os

import pytest

from opendbc.car.honda.modified_eps import DEFAULT_SETTINGS
from opendbc.car.honda.tests import test_clarity_angle_mode as T
from opendbc.car.honda.tests.test_eps_cal_status import v4

GOLDEN = os.path.join(os.path.dirname(__file__), "meps_golden_frames.json")


def _settings(ci, **kw):
  ci.CC.modified_eps_settings = type("S", (), {"current": lambda self: dataclasses.replace(DEFAULT_SETTINGS, **kw)})()


def _start(status=None, **settings):
  T.ANGLE[0] = True
  ci = T.clarity()
  if settings:
    _settings(ci, **settings)
  f = T.ready(ci)     # 0x0E status frames and fresh 0x6A2 linear-angle frames
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
  for k in range(8, 14):
    T.run_status(ci, f, v4(steering=False, reason=1, counter=k % 4), k)
  out += _frames(ci, [(True, 0.0, 0.0, 10.0, False)] * 5)
  for k in range(14, 16):
    T.run_status(ci, f, v4(steering=False, reason=1, counter=k % 4), k)
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
      json.dump({"source": "protocol v3 (0x6A4 layout 4, build 0x0E), meps/protocol.py; see the module docstring", "v3": frames}, f, indent=0)
    pytest.skip("regenerated")
  _compare(json.load(open(GOLDEN))["v3"], frames)


def test_golden_frames_follow_the_wire_rules():
  from opendbc.car.honda.meps import protocol as P
  for name, frames in json.load(open(GOLDEN))["v3"].items():
    for h in frames:
      b = bytes.fromhex(h)
      assert len(b) == 5 and b[3] == 0 and not b[2] & 0x80, (name, h)
      assert P.is_v3_angle(b[2]) or (b[2] == P.V3_STANDBY and b[0:2] == bytes(2)), (name, h)


def test_golden_scenarios_exercise_what_they_claim():
  from opendbc.car.honda.meps import protocol as P
  golden = json.load(open(GOLDEN))["v3"]

  def active(h):
    return P.is_v3_angle(int(h[4:6], 16))

  def yielding(h):
    return int(h[4:6], 16) == P.v3_byte2(False)
  assert not any(active(h) for h in golden["inactive"])
  assert all(active(h) for h in golden["engage_straight"][1:])
  ov = golden["override_plan_target_and_ramp_back"]
  assert all(yielding(h) for h in ov[151:231]) and not any(yielding(h) for h in ov[:151] + ov[231:])   # YIELD while pressed
  assert all(active(h) for h in ov[1:])                                                 # the loop frame never drops
  assert not any(active(h) for h in golden["engage_beyond_limit_waits"][1:31])         # waits beyond the limit
  assert any(active(h) for h in golden["engage_beyond_limit_waits"][-40:])
  assert not any(active(h) for h in golden["loop_not_running_fault"][2:7])
