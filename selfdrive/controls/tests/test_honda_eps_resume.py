"""Peter's resume-ramp regressions against the canonical Honda EPS controller (fb1d1cd51d)."""
from types import SimpleNamespace

import numpy as np
import pytest

from cereal import car, log
from opendbc.car.honda.values import CAR
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib import latcontrol_honda_eps as honda_eps
from openpilot.selfdrive.controls.tests.test_honda_eps_firmware_ff import _drive, _Params, _params


def _controller(monkeypatch, values=None):
  settings = {"HondaEpsController": "1", **(values or {})}
  monkeypatch.setattr(honda_eps, "Params", lambda: _Params(settings))
  cp = _params(b"39990-TBA,C020\0\0", CAR.HONDA_CIVIC_BOSCH)
  return honda_eps.LatControlHondaEps(cp, None, DT_CTRL), VehicleModel(cp), cp


# --- resume ramp (HondaEpsResumeRamp) ---------------------------------------------------------------------

def _pull_away(monkeypatch, ramp, aol=True, wheel=70.0, v_end=3.0, pressed_frames=(), blinker_frames=(), toggles=None):
  """Stopped with the wheel turned, model asking for straight, then pulling away. With aol lateral stays active
  through the stop (the car controller cuts torque below NrdrMinSteerSpeed); without it lateral is off below 2 mph."""
  values = {"NrdrMinSteerSpeed": "2", "HondaEpsResumeRamp": "1" if ramp else "0"}
  lac, VM, _ = _controller(monkeypatch, values)
  CS = car.CarState.new_message()
  params = log.LiveParametersData.new_message()
  params.steerRatio, params.stiffnessFactor = 16.0, 1.0
  rows = []
  for k in range(400):
    CS.vEgo = 0.0 if k < 100 else min(v_end, (k - 100) * 0.01)
    CS.steeringAngleDeg = wheel
    CS.steeringPressed = k in pressed_frames
    CS.leftBlinker = k in blinker_frames
    torque = CS.vEgo >= 2.0 * 0.44704
    active = aol or torque
    out, angle_des, _ = lac.update(active, CS, VM, params, False, 0.0, False, 0.2, None, None,
                                   toggles if toggles is not None else SimpleNamespace())
    rows.append((torque, out, angle_des))
  return rows


def _first_torque(rows):
  return next(k for k, r in enumerate(rows) if r[0])


@pytest.mark.parametrize("aol", [True, False])
def test_resume_ramp_takes_over_from_the_wheel(monkeypatch, aol):
  rows = _pull_away(monkeypatch, ramp=True, aol=aol)
  k0 = _first_torque(rows)
  assert all(r[2] == pytest.approx(70.0) for r in rows[:k0])                 # held at the wheel while no torque
  assert all(abs(r[1]) < 1e-6 for r in rows[:k0])                              # nothing wound up for the resume
  des = [r[2] for r in rows[k0:k0 + 110]]
  assert des[0] == pytest.approx(70.0, abs=0.5)
  assert all(b <= a + 1e-9 for a, b in zip(des, des[1:], strict=False))        # moves one way, to the model
  assert des[25] > 55.0                                                        # a quarter second in: ~12 of the 70 deg
  assert abs(des[105]) < 1.0                                                   # on the model after ~1 s


@pytest.mark.parametrize("aol", [True, False])
def test_without_the_ramp_the_target_snaps_to_the_model(monkeypatch, aol):
  rows = _pull_away(monkeypatch, ramp=False, aol=aol)
  k0 = _first_torque(rows)
  assert abs(rows[k0 + 25][2]) < 1.0                                           # 70 deg in a quarter second (300 deg/s)


def test_resume_ramp_output_starts_from_zero(monkeypatch):
  on, off = _pull_away(monkeypatch, ramp=True), _pull_away(monkeypatch, ramp=False)
  k0 = _first_torque(on)
  assert max(abs(r[1]) for r in on[k0:k0 + 10]) < 0.5 * max(abs(r[1]) for r in off[k0:k0 + 10])


def test_resume_ramp_restarts_from_where_the_driver_leaves_the_wheel(monkeypatch):
  base = _pull_away(monkeypatch, ramp=True)
  k0 = _first_torque(base)
  rows = _pull_away(monkeypatch, ramp=True, pressed_frames=range(k0, k0 + 50))
  assert rows[k0 + 50][2] == pytest.approx(70.0, abs=0.5)                      # still at the wheel while pressed
  assert rows[k0 + 80][2] > base[k0 + 80][2] + 20.0                           # the ramp started again


def test_resume_ramp_is_off_by_default_and_at_speed(monkeypatch):
  lac, _, _ = _controller(monkeypatch, )
  assert not lac.resume_ramp
  assert lac.min_steer_speed == pytest.approx(1.0 * 0.44704)                   # the car controller's default
  assert np.interp(9.0, *honda_eps.RESUME_RAMP_S) == 0.0                     # no ramp from 20 mph


def test_resume_ramp_torque_slews_in_and_ends_without_a_step(monkeypatch):
  rows = _pull_away(monkeypatch, ramp=True)
  k0 = _first_torque(rows)
  outs = [r[1] for r in rows[k0 - 1:]]
  assert max(abs(b - a) for a, b in zip(outs, outs[1:], strict=False)) <= honda_eps.RESUME_TORQUE_RATE * DT_CTRL + 1e-9


def test_toggle_off_leaves_the_controller_as_it_was(monkeypatch):
  lac, VM, _ = _controller(monkeypatch, {"NrdrMinSteerSpeed": "2"})
  ref, _, _ = _controller(monkeypatch, )
  assert [r[1:3] for r in _drive(lac, VM)] == [r[1:3] for r in _drive(ref, VM)]


TURN_DESIRES_ON = SimpleNamespace(use_turn_desires=True, minimum_lane_change_speed=20.0 * 0.44704)


@pytest.mark.parametrize("aol", [True, False])
def test_no_ramp_while_a_turn_desire_is_active(monkeypatch, aol):
  blinker = range(400)
  rows = _pull_away(monkeypatch, ramp=True, aol=aol, blinker_frames=blinker, toggles=TURN_DESIRES_ON)
  base = _pull_away(monkeypatch, ramp=False, aol=aol, blinker_frames=blinker, toggles=TURN_DESIRES_ON)
  k0 = _first_torque(rows)
  des = [r[2] for r in rows[k0:k0 + 110]]
  assert des[0] == pytest.approx(70.0, abs=4.0)                                # starts from the wheel
  assert abs(des[25]) < 1.0                                                    # at the angle-rate ceiling, not 1 s
  assert any(abs(r[1]) > 0.5 for r in rows[k0:k0 + 10])                        # no torque slew
  # same as without the ramp once the held stop has washed out of the filter (with AOL the toggle-off target is not
  # held at the wheel while stopped, so the first ~1 s differs by a few hundredths)
  assert [r[1] for r in rows[k0 + 30:]] == pytest.approx([r[1] for r in base[k0 + 30:]], abs=0.02)


def test_blinker_without_force_turn_desires_keeps_the_ramp(monkeypatch):
  off = SimpleNamespace(use_turn_desires=False, minimum_lane_change_speed=20.0 * 0.44704)
  rows = _pull_away(monkeypatch, ramp=True, blinker_frames=range(400), toggles=off)
  k0 = _first_torque(rows)
  assert rows[k0 + 25][2] > 55.0


def test_turn_desire_mid_ramp_ends_it(monkeypatch):
  plain = _pull_away(monkeypatch, ramp=True)
  k0 = _first_torque(plain)
  rows = _pull_away(monkeypatch, ramp=True, blinker_frames=range(k0 + 20, 400), toggles=TURN_DESIRES_ON)
  assert rows[k0 + 19][2] == pytest.approx(plain[k0 + 19][2])                  # ramping until the blinker
  assert abs(rows[k0 + 40][2]) < 1.0 < abs(plain[k0 + 40][2])                  # then straight to the model
