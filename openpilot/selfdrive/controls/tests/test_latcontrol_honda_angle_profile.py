"""Angle-profile cars (opendbc car/honda/angle_profiles.py, RDX 3G first): angle mode on the 0x0C angle PTM image selects
LatControlHondaAngle, and on the linear angle (starpilotCarState.steeringAngleLinear) the desired angle is the plain
vehicle model with paramsd's ratio, starting at the profile's on-center ratio: no VGR table, no rack map."""
import math

import pytest

from opendbc.car import structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda.angle_profiles import OWN_GEOMETRY
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.values import CAR
from opendbc.car.vehicle_model import VehicleModel
from openpilot.selfdrive.controls.lib.lateral_controller_factory import create_lateral_controller
from openpilot.selfdrive.controls.lib.latcontrol_honda_angle import LatControlHondaAngle


def rdx_cp(fw=b'39990+TJB+A220\x00\x00', angle=True, candidate=CAR.ACURA_RDX_3G):
  from opendbc.car import gen_empty_fingerprint
  from opendbc.car.honda.hondacan import CanBus
  car_fw = [structs.CarParams.CarFw(ecu=structs.CarParams.Ecu.eps, address=0x18DA30F1, subAddress=0, fwVersion=fw, brand="honda")]
  fingerprint = gen_empty_fingerprint()
  fingerprint[CanBus(CarInterface.get_params(candidate, fingerprint, [], False, False, False)).pt][0x1A3] = 8
  cp = CarInterface.get_params(candidate, fingerprint, car_fw, False, False, False)
  cp.carFw = car_fw
  return cam.apply_angle_mode(cp, angle).as_reader()


# (platform, its 0x0C angle PTM image): the RDX, and the SH-2A family (one image per platform; test_sh2a_angle_mode.py has all)
ANGLE_CARS = [(CAR.ACURA_RDX_3G, b'39990+TJB+A220\x00\x00'), (CAR.ACURA_RDX_3G_MMR, b'39990+TJB+A220\x00\x00'),
              (CAR.HONDA_CIVIC, b'39990+TEG+A010\x00\x00'), (CAR.HONDA_CIVIC_BOSCH, b'39990+TGG+A120\x00\x00'),
              (CAR.HONDA_CRV_5G, b'39990+TLA+A220\x00\x00'), (CAR.HONDA_INSIGHT, b'39990+TXM+A040\x00\x00')]


@pytest.mark.parametrize("candidate,fw", ANGLE_CARS)
def test_angle_profile_car_uses_the_plain_vehicle_model_when_linear(candidate, fw):
  cp = rdx_cp(fw=fw, candidate=candidate)
  assert cp.steerControlType == structs.CarParams.SteerControlType.angle
  lac = create_lateral_controller(cp, CarInterface(cp), 0.01, mode=None)
  assert isinstance(lac, LatControlHondaAngle)
  vm = VehicleModel(cp)
  assert vm.sR == pytest.approx(OWN_GEOMETRY[candidate].steer_ratio)    # paramsd starts at the on-center ratio
  lac.linear = True
  for v, k in ((5., 0.02), (15., 0.004), (30., -0.001)):
    want = math.degrees(vm.get_steer_from_curvature(-k, v, 0.))
    assert lac.desired_angle_no_offset(k, v, 0., vm) == pytest.approx(want)
  # paramsd's live ratio carries straight through (the VM it updates is the one passed in)
  vm.update_params(1.0, 17.0)
  assert lac.desired_angle_no_offset(0.004, 15., 0., vm) == pytest.approx(math.degrees(vm.get_steer_from_curvature(-0.004, 15., 0.)))


def test_torque_ptm_image_keeps_its_torque_controller():
  cp = rdx_cp(fw=b'39990-TJB,A220\x00\x00')
  assert cp.steerControlType == structs.CarParams.SteerControlType.torque
  assert not isinstance(create_lateral_controller(cp, CarInterface(cp), 0.01, mode=None), LatControlHondaAngle)
