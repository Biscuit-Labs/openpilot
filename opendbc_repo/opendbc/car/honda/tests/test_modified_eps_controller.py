import pytest

from opendbc.car import structs
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.tests.test_modified_eps import KNOWN_CASES, FLEET_CASES, eps, params
from opendbc.car.honda.values import CAR


@pytest.mark.parametrize("identity,firmware", KNOWN_CASES + FLEET_CASES)
def test_actual_modified_factory_controller_consumes_separate_lookup(identity, firmware):
  cp = params(identity, [eps(firmware)])
  ci = CarInterface(cp)
  ci.update([])
  ci.CS.out = structs.CarState(vEgo=15.0).as_reader()   # above HondaMinSteerSpeed, which zeroes torque below 1 mph
  cc = structs.CarControl(latActive=True)
  cc.actuators.torque = 1.0
  emitted = []
  for tick in range(250):   # the engage fade-in takes HondaOverrideFadeUpSecs (0.5 s)
    actuators, frames = ci.apply(cc.as_reader(), 1_000_000_000 + tick * 10_000_000)
    assert frames
    emitted.append(actuators.torqueOutputCan)
  expected_max = ci.CC.params.STEER_LOOKUP_V[-1]  # the map's output cap (modified-EPS maps have no 3840 knee)
  assert max(abs(value) for value in emitted) <= expected_max
  assert abs(emitted[-1]) >= expected_max - 1
  assert ci.CC.modified_eps_steering is not None   # every modified-EPS Honda, not only the Civic Bosch


def test_actual_modified_driver_override_and_inactive_reset():
  # the shared modified-EPS override detector and fade replaced 7.0's Civic Bosch-only filter
  cp = params(CAR.HONDA_CIVIC_BOSCH, [eps(b'39990-TGG,A020\x00\x00')])
  ci = CarInterface(cp)
  ci.update([])
  cc = structs.CarControl(latActive=True)
  cc.actuators.torque = 0.8
  for tick in range(20):
    ci.CS.out = structs.CarState(vEgo=15.0, steeringPressed=True, steeringTorque=-1.0).as_reader()
    ci.apply(cc.as_reader(), 1_000_000_000 + tick * 10_000_000)
  steering = ci.CC.modified_eps_steering
  assert steering.steering_pressed_prev
  assert steering.last_torque == 0.0   # pressed against the command from the first frame: no torque
  cc.latActive = False
  ci.apply(cc.as_reader(), 1_200_000_000)
  assert steering.steering_pressed_filter_s == 0.0
  assert not steering.steering_pressed_prev


def test_ordinary_civic_has_no_modified_steering_stage():
  ci = CarInterface(params(CAR.HONDA_CIVIC_BOSCH, [eps(b'39990-TBA-C120\x00\x00')]))
  assert ci.CC.modified_eps_steering is None
