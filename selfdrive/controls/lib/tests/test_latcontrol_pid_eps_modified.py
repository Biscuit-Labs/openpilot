"""Honda modified-EPS tuning and exact-firmware VGR profile selection."""
from types import SimpleNamespace

import pytest

from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.steer_ratio import (
  HONDA_VGR_INVERSE_BY_PROFILE,
)
from opendbc.car.honda.values import CAR, HondaFlags
from opendbc.car import structs
from openpilot.common.pid import PIDController
from openpilot.selfdrive.controls.lib.latcontrol_pid import (
  NRDR_MODIFIED_EPS_KF_SPEED_BP,
  NRDR_MODIFIED_EPS_KF_V,
  HONDA_SR_CURVE_BY_FP,
  LatControlPID,
  _clarity_eps_pid_output_scale,
  get_nrdr_modified_eps_kf,
)

CarParams = structs.CarParams

TOGGLES = SimpleNamespace(force_torque_controller=False, nnff=False, nnff_lite=False)

# a comma in the eps fw version is what marks a modified EPS
# A part number with no firmware VGR table (every PTM image now has one), so these exercise the road-curve and
# fixed-ratio paths; the comma marks the modified image.
MODIFIED_FW = b'39990-TBA,A010\x00\x00'
STOCK_FW = b'39990-TBA-A010\x00\x00'

# LatControlPID only reaches into CI for the feedforward function
STUB_CI = SimpleNamespace(get_steer_feedforward_function=lambda: (lambda angle, v_ego: angle))

# Every Honda that can carry a linear-max RWD image. Civic Bosch is included: NRDR keeps modified-EPS
# cars on the angle-space PID controller, as nrdr-nightly does.
MODIFIED_EPS_CARS = [CAR.HONDA_CLARITY, CAR.HONDA_CRV_5G, CAR.HONDA_INSIGHT, CAR.HONDA_CIVIC, CAR.HONDA_CIVIC_BOSCH,
                     CAR.ACURA_RDX_3G, CAR.ACURA_RDX_3G_MMR]


def _params(candidate, fw_version):
  car_fw = [CarParams.CarFw(ecu=CarParams.Ecu.eps, fwVersion=fw_version, address=0x18DA30F1, subAddress=0)]
  return CarInterface.get_params(candidate, {0: {}, 1: {}, 2: {}}, car_fw, False, False, False, TOGGLES)


def _controller(candidate, fw_version):
  return LatControlPID(_params(candidate, fw_version), STUB_CI, 0.01)


# All of these must land on LatControlPID, including Civic Bosch -- except the modified-EPS Clarity, which
# controlsd hands to LatControlHondaEps, as it does the other PTM cars once
# HondaEpsController is on (test_honda_eps_firmware_ff.py).

@pytest.mark.parametrize("candidate", MODIFIED_EPS_CARS)
def test_modified_eps_hondas_select_the_pid_controller(candidate):
  # controlsd dispatches on lateralTuning.which(); anything but "pid" never reaches LatControlPID.
  assert _params(candidate, MODIFIED_FW).lateralTuning.which() == "pid"


@pytest.mark.parametrize("candidate", MODIFIED_EPS_CARS)
def test_modified_eps_hondas_get_the_nrdr_live_tune(candidate):
  lat = _controller(candidate, MODIFIED_FW)
  assert lat.is_eps_modified, f"{candidate} should run the NRDR live tune on a modified EPS"


# A stock RDX 3G (either platform) runs the torque controller, so it has no LatControlPID to build; its stock
# tune is checked in test_stock_rdx_3g_uses_the_torque_controller.
@pytest.mark.parametrize("candidate", [c for c in MODIFIED_EPS_CARS if c not in (CAR.ACURA_RDX_3G, CAR.ACURA_RDX_3G_MMR)])
def test_stock_eps_hondas_do_not_get_the_nrdr_live_tune(candidate):
  lat = _controller(candidate, STOCK_FW)
  assert not lat.is_eps_modified, f"{candidate} must keep stock behaviour on an unmodified EPS"


@pytest.mark.parametrize("candidate, fw_version, profile", [
  (CAR.HONDA_CLARITY, b'39990-TRW,A020\x00\x00', "clarity_trw_a020"),
  (CAR.HONDA_CIVIC_BOSCH, b'39990-TBA,C020\x00\x00', "civic_tba_c020"),
  (CAR.HONDA_INSIGHT, b'39990-TXM,A040\x00\x00', "insight_txm_a040"),
])
def test_road_measured_curve_defaults_over_exact_firmware_profile(candidate, fw_version, profile):
  car_params = _params(candidate, fw_version)
  lat = LatControlPID(car_params, STUB_CI, 0.01)
  assert profile in HONDA_VGR_INVERSE_BY_PROFILE
  assert lat.sr_curve is HONDA_SR_CURVE_BY_FP[str(candidate)]
  # The road curve is the default, but retain the exact firmware inverse for the
  # runtime VGR A/B setting instead of discarding a valid traced profile at init.
  assert not lat.use_firmware_vgr
  assert lat.vgr_inverse is HONDA_VGR_INVERSE_BY_PROFILE[profile]


@pytest.mark.parametrize("candidate", [CAR.HONDA_CLARITY, CAR.HONDA_CIVIC_BOSCH, CAR.HONDA_INSIGHT, CAR.HONDA_CRV_5G])
def test_road_measured_curve_does_not_depend_on_eps_firmware(candidate):
  lat = _controller(candidate, STOCK_FW)
  assert lat.sr_curve is HONDA_SR_CURVE_BY_FP[str(candidate)]
  assert lat.vgr_inverse is None


def test_unmapped_unknown_eps_firmware_keeps_fixed_vehicle_model_ratio():
  lat = _controller(CAR.HONDA_CIVIC_BOSCH_DIESEL, STOCK_FW)
  assert lat.sr_curve is None
  assert lat.vgr_inverse is None


def test_modified_eps_runtime_scales_match_defaults():
  # P/F defaults are neutral, while the requested I defaults reduce low-speed correction
  # to 20% and disable highway integration.
  expected_scales = (1.0, 1.0, 1.0, 0.2, 1.0, 0.0, 1.0, 1.0, 1.0)
  clarity = _controller(CAR.HONDA_CLARITY, MODIFIED_FW)
  clarity_scales = (clarity.lat_p_scale_low, clarity.lat_p_scale_standard, clarity.lat_p_scale_highway,
                    clarity.lat_i_scale_low, clarity.lat_i_scale_standard, clarity.lat_i_scale_highway,
                    clarity.lat_f_scale_low, clarity.lat_f_scale_standard, clarity.lat_f_scale_highway)
  assert clarity_scales == expected_scales

  for candidate in (CAR.HONDA_CRV_5G, CAR.HONDA_INSIGHT, CAR.HONDA_CIVIC, CAR.HONDA_CIVIC_BOSCH):
    lat = _controller(candidate, MODIFIED_FW)
    scales = (lat.lat_p_scale_low, lat.lat_p_scale_standard, lat.lat_p_scale_highway,
              lat.lat_i_scale_low, lat.lat_i_scale_standard, lat.lat_i_scale_highway,
              lat.lat_f_scale_low, lat.lat_f_scale_standard, lat.lat_f_scale_highway)
    assert scales == expected_scales, f"{candidate} should use the configured band scales, got {scales}"


def test_non_honda_never_takes_the_eps_modified_path():
  CP = _params(CAR.HONDA_CLARITY, MODIFIED_FW)
  CP.brand = "toyota"
  assert not LatControlPID(CP, STUB_CI, 0.01).is_eps_modified


def test_clarity_and_c020_share_the_current_feedforward_curve():
  low_max = 25.0 * 0.44704
  assert NRDR_MODIFIED_EPS_KF_SPEED_BP == pytest.approx([0.0, low_max - 1e-3, low_max, 50.0 * 0.44704])
  assert NRDR_MODIFIED_EPS_KF_V == pytest.approx([2.4e-6, 1.8e-6, 3.6e-6, 6.0e-6])
  assert get_nrdr_modified_eps_kf(0.0) == pytest.approx(2.4e-6)
  assert get_nrdr_modified_eps_kf(low_max - 1e-3) == pytest.approx(1.8e-6)
  assert get_nrdr_modified_eps_kf(low_max) == pytest.approx(3.6e-6)
  assert get_nrdr_modified_eps_kf(50.0 * 0.44704) == pytest.approx(6.0e-6)

  clarity = _controller(CAR.HONDA_CLARITY, MODIFIED_FW)
  c020 = _controller(CAR.HONDA_CIVIC_BOSCH, MODIFIED_FW)
  assert clarity.is_modified_eps_kf_car
  assert c020.is_modified_eps_kf_car
  assert c020.is_civic_bosch_modified
  assert clarity.ff_factor == pytest.approx(3.6e-6)
  assert c020.ff_factor == pytest.approx(3.6e-6)


@pytest.mark.parametrize(("desired_angle", "expected"), [
  (-24.0, 1.07438),
  (24.0, 1.07438),
])
def test_modified_eps_output_scale_is_direction_neutral(desired_angle, expected):
  # The shared modified-EPS scale is direction-neutral. Directional authority belongs
  # in the PID, not in a multiplier on its complete P/I/F output.
  assert _clarity_eps_pid_output_scale(desired_angle, 10.0) == pytest.approx(expected)


def test_modified_eps_i_scale_controls_accumulation_and_clears_zero_band_state():
  pid = PIDController(k_p=0.0, k_i=1.0, rate=100)

  pid.update(1.0, integrator_gain_scale=0.2)
  assert pid.i == pytest.approx(0.002)

  pid.update(1.0, integrator_gain_scale=0.0, reset_integrator=True)
  assert pid.i == pytest.approx(0.0)

  # Returning to a non-zero band starts clean; no hidden highway I can reappear.
  pid.update(0.0, integrator_gain_scale=1.0)
  assert pid.i == pytest.approx(0.0)

  pid.update(1.0, integrator_gain_scale=1.0)
  assert pid.i == pytest.approx(0.01)

  # The modified-EPS low-speed freeze clears I as well, so pull-away cannot revive
  # an old parking-speed correction.
  pid.update(0.0, freeze_integrator=True, reset_integrator=True)
  assert pid.i == pytest.approx(0.0)


def test_crv_5g_shares_the_clarity_modified_eps_tune():
  # CR-V 5G runs the same NRDR modified-EPS hardware as Clarity/Civic Bosch, so it should
  # get the same banded kp/ki/kf family instead of the old flat, unbanded values.
  crv_5g = _controller(CAR.HONDA_CRV_5G, MODIFIED_FW)
  assert crv_5g.is_modified_eps_kf_car
  assert crv_5g.ff_factor == pytest.approx(3.6e-6)

  low_max = 25.0 * 0.44704
  expected_bp = [0.0, low_max - 1e-3, low_max, 50.0 * 0.44704]
  cp = _params(CAR.HONDA_CRV_5G, MODIFIED_FW)
  assert list(cp.lateralTuning.pid.kpBP) == pytest.approx(expected_bp)
  assert list(cp.lateralTuning.pid.kpV) == pytest.approx([0.018, 0.024, 0.048, 0.060])
  assert list(cp.lateralTuning.pid.kiBP) == pytest.approx(expected_bp)
  assert list(cp.lateralTuning.pid.kiV) == pytest.approx([0.006, 0.008, 0.016, 0.020])



@pytest.mark.parametrize("candidate", [CAR.ACURA_RDX_3G, CAR.ACURA_RDX_3G_MMR])
def test_rdx_3g_ptm_shares_the_clarity_modified_eps_tune_on_pid(candidate):
  # Both RDX 3G platforms flash to the same 39990-TJB,A220 PTM image.
  cp = _params(candidate, b'39990-TJB,A220\x00\x00')
  clarity = _params(CAR.HONDA_CLARITY, MODIFIED_FW)
  assert cp.flags & HondaFlags.EPS_MODIFIED
  assert cp.lateralTuning.which() == "pid"
  # The PTM target map X axis ends at E4 4096, where Route A matches the Clarity's 3840 top.
  assert list(cp.lateralParams.torqueBP) == list(cp.lateralParams.torqueV) == [0, 4096]
  for field in ("kpBP", "kpV", "kiBP", "kiV"):
    assert list(getattr(cp.lateralTuning.pid, field)) == pytest.approx(list(getattr(clarity.lateralTuning.pid, field)))
  assert cp.lateralTuning.pid.kf == pytest.approx(clarity.lateralTuning.pid.kf)
  assert cp.steerAtStandstill and cp.minSteerSpeed == -1.0

  rdx = LatControlPID(cp, STUB_CI, 0.01)
  assert rdx.is_eps_modified and rdx.is_modified_eps_kf_car

  # No EPS firmware calibration for the TJB rack, so controlsd keeps it on LatControlPID.
  from openpilot.selfdrive.controls.lib.latcontrol_honda_eps import eps_firmware_calibration
  assert eps_firmware_calibration(cp, SimpleNamespace(get_bool=lambda *a, **k: True, get=lambda *a, **k: b"1")) is None


@pytest.mark.parametrize(("candidate", "fw_version", "cap"), [
  (CAR.ACURA_RDX_3G, b'39990-TJB-A030\x00\x00', 4095),
  (CAR.ACURA_RDX_3G_MMR, b'39990-TJB-A220\x00\x00', 3840),
])
def test_stock_rdx_3g_uses_the_torque_controller(candidate, fw_version, cap):
  cp = _params(candidate, fw_version)
  assert not cp.flags & HondaFlags.EPS_MODIFIED
  assert cp.lateralTuning.which() == "torque"
  assert list(cp.lateralParams.torqueBP) == list(cp.lateralParams.torqueV) == [0, cap]
