"""Bind the A220 inversion tables to the owner's actual RWD, not its filename."""
import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from opendbc.car.honda.steer_ratio import _CRV_TLA_A040_POSITION_X, _CRV_TLA_A040_POSITION_Y
from openpilot.selfdrive.controls.lib import nrdr_eps_firmware_ff as ff
from openpilot.tools.lateral.eps_fw import decrypt_rwd


RWD_HASH = "8f175250519130b0a8505291ef328b82f9caf543cfb76c62c3bc23e954e727a7"
RWD = Path(__file__).resolve().parents[3] / "docs/firmware_evidence/a220" / f"{RWD_HASH}.rwd"


def test_a220_calibration_matches_checksum_bound_firmware():
  start, image, raw = decrypt_rwd(RWD)
  assert hashlib.sha256(raw).hexdigest() == RWD_HASH
  assert hashlib.sha256(image).hexdigest() == "3c6019fd062c3d9c6f605efbc79edc7e30ffa9dc3ee3eadf2db7e0278495bbb6"
  assert (start, len(image)) == (0x4000, 0x6c000)

  def words(address, count):
    return list(struct.unpack_from(f">{count}H", image, address - start))

  cal = ff.CRV_5G_A220_FF45
  for row in (0, 1):
    assert words(0x11ae0 + row * 18, 9) == cal.r5_key_bp
    assert words(0x11b5e + row * 18, 9) == cal.r5_v
    assert words(0x11e2e + row * 18, 9) == cal.kp_key_bp
    assert words(0x11eac + row * 18, 9) == cal.kp_v
  assert words(0x11ade, 1) == [cal.key_clamp]
  assert words(0x11930, 9) == cal.envelope_bp
  assert words(0x119ae, 9) == cal.envelope_v
  assert words(0x11ada, 1) == [3200]
  assert words(0x42558, 1) == [1650]
  assert words(0x19c00, 1) == [3121]
  assert words(0x11374, 30) == _CRV_TLA_A040_POSITION_X
  assert words(0x11338, 30) == _CRV_TLA_A040_POSITION_Y
  # The image does NOT make all rows identical; keep the documented boundary observable.
  assert words(0x11ae0 + 2 * 18, 9) != cal.r5_key_bp


@pytest.mark.parametrize("version", [b"39990-TLA,A220\0\0", b"39990-TLA-A220\0\0"])
def test_a220_fw_selects_own_calibration(version):
  cp = SimpleNamespace(carFw=[SimpleNamespace(ecu="eps", fwVersion=version)])
  assert ff.crv_eps_firmware_calibration(cp) is ff.CRV_5G_A220_FF45
  cp.carFw[0].fwVersion = b"39990-TLA,A040\0\0"
  assert ff.crv_eps_firmware_calibration(cp) is ff.CRV_5G_A040_FF45


@pytest.mark.parametrize("load,rate", [(0, 0), (500, 0), (-1500, 0), (800, 40), (-800, -40), (300, -60)])
def test_a220_inversion_reproduces_requested_load(load, rate):
  cal = ff.CRV_5G_A220_FF45
  target = ff.r5_for_motion(load, rate, cal=cal)
  assert ff.firmware_output(target, rate, cal) == pytest.approx(load, abs=1e-6)


@pytest.mark.parametrize("target", [-26000, -10000, -1000, 0, 1000, 10000, 26000])
def test_a220_command_inverse_round_trip(target):
  cal = ff.CRV_5G_A220_FF45
  output = ff.output_from_r5(target, cal)
  assert ff.r5_from_output(output, 20.0, cal) == pytest.approx(target, abs=60)
