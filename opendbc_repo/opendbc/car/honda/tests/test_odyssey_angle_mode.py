"""Odyssey (THR-A020) and its linear-angle EPS build 0x0C (39990+THR+A020, rwd-xray THR_0x0C_PORTS/thr): PREPARED, NOT ENABLED.

The Odyssey has no panda angle-profile row yet: its on-center ratio is unmeasured (no routes) and on its CarSpecs model no row fits
0.90-1.00 (angle_profiles.py). Until a row exists the angle image runs its stock torque mode (apply_angle_mode clears EPS_MODIFIED)
and sends no angle frames; that is tested here. The angle-mode tests are written for the row it will get and marked
xfail(strict): when the row lands they XPASS and fail, so the marks are removed in the same change."""
import pytest

from opendbc.car import structs
from opendbc.car.honda import clarity_angle_mode as cam
from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, vm_angle_limit
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.values import CAR, HondaFlags, HondaSafetyFlags

ANGLE_FW = b'39990+THR+A020\x00\x00'
NO_ROW = "no panda angle-profile row for the Odyssey until a route measures its on-center ratio"


def odyssey(fw=ANGLE_FW, angle=True):
  cp = params(CAR.HONDA_ODYSSEY, [eps(fw)])
  cp.carFw = [eps(fw)]
  return CarInterface(cam.apply_angle_mode(cp, angle))


def test_angle_image_without_a_row_is_stock_torque_mode():
  for angle in (True, False):
    ci = odyssey(angle=angle)
    assert ci.CP.steerControlType == structs.CarParams.SteerControlType.torque
    assert not ci.CP.flags & (HondaFlags.CLARITY_ANGLE_MODE | HondaFlags.EPS_MODIFIED)
    assert not ci.CP.safetyConfigs[-1].safetyParam & (HondaSafetyFlags.CLARITY_ANGLE | 0xE000)
    assert ci.CC.angle_sender is None and ci.CC.eps_mode == 0
  assert CAR.HONDA_ODYSSEY not in ANGLE_PROFILES


@pytest.mark.xfail(strict=True, reason=NO_ROW)
def test_angle_image_selects_angle_mode():
  ci = odyssey()
  assert ci.CP.flags & HondaFlags.CLARITY_ANGLE_MODE and ci.CP.steerControlType == structs.CarParams.SteerControlType.angle
  assert ci.CP.safetyConfigs[-1].safetyParam & 0xE000


@pytest.mark.xfail(strict=True, reason=NO_ROW)
@pytest.mark.parametrize("v", [3., 20., 40.])
def test_sender_at_its_clamp_passes_panda(v):
  from opendbc.car.honda.tests.test_rdx_angle_mode import Car, request
  profile = ANGLE_PROFILES[CAR.HONDA_ODYSSEY]
  car = Car(odyssey(), v=v)
  for i in range(700):
    _, dat, ok, target = car.step(True, 1.2 * vm_angle_limit(v, profile))
    assert ok, (v, i, target)
    car.wheel = target
  assert request(dat) and abs(target) > 0.98 * vm_angle_limit(v, profile)


@pytest.mark.xfail(strict=True, reason=NO_ROW)
def test_reference_not_latched_is_not_ready():
  from opendbc.car.honda.tests.test_rdx_angle_mode import Car, request
  car = Car(odyssey(), wheel=4.0)
  car.ref_latched = 0
  for _ in range(30):
    cs, dat, ok, _ = car.step(True, 3.)
    assert ok and not request(dat)
  assert cs.steerFaultTemporary
