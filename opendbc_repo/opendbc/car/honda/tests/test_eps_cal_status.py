"""0x6A4 EPS_CAL_STATUS interlock (eps_cal_status.py), protocol v3 only: layout-4 frames (build 0x0E on). v1 frames
(MM 0x02 layout 2, angle builds 0x04-0x0A layout 3) fault "unsupported_build"; the v2 builds 0x0B-0x0D "unknown_build".
Angle-mode behaviour on layout 4 is in test_meps_v3.py and test_clarity_angle_mode.py."""
import pytest

from opendbc.car.honda.eps_cal_status import STATUS_TIMEOUT_FRAMES
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.values import CAR

ADDR = 0x6A4


def honda_checksum(b, addr=ADDR):
  s = sum((x >> 4) + (x & 0xF) for x in b[:-1]) + (b[-1] >> 4) + sum((addr >> (4 * k)) & 0xF for k in range(3))
  return (8 - s) & 0xF


def v4(mode=1, steering=True, fault=False, clamp=False, lkas=2, build=0x0E, reason=0, gain=15, ref=0, out=0, counter=0):
  """A layout-4 status frame (meps/protocol.py)."""
  b = bytearray(8)
  b[0] = 0x80 | (0x40 if fault else 0) | (0x20 if steering else 0) | (0x10 if clamp else 0) | ((lkas & 3) << 2) | (mode & 3)
  b[1] = build
  b[2] = ((gain & 0xF) << 4) | (reason & 0xF)
  b[3:5] = (ref & 0xFFFF).to_bytes(2, "big")
  b[5:7] = (out & 0xFFFF).to_bytes(2, "big")
  b[7] = (counter & 3) << 4
  b[7] |= honda_checksum(bytes(b))
  return bytes(b)


def v1(active=1, requested=1, build=0x02, counter=0, b0_extra=0):
  """A v1 status frame (layout 2/3: requested mode in byte 0 bits 7:4, never bit 7)."""
  b = bytearray([(requested << 4) | active | b0_extra, build, 0, 0, 0, 0, 0, counter << 4])
  b[7] |= honda_checksum(bytes(b))
  return bytes(b)


def clarity(fw=b'39990-TRW,A020\x00\x00'):
  ci = CarInterface(params(CAR.HONDA_CLARITY, [eps(fw)]))
  return ci


class Feed:
  """carState at 100 Hz; 0x6A4 at 50 Hz (every other update), like the car."""
  def __init__(self, ci):
    self.ci, self.t = ci, 1_000_000_000

  def step(self, data=None):
    self.t += 10_000_000
    cs = self.ci.update([(self.t, [(ADDR, data, 0)] if data is not None else [])])
    return cs

  def run(self, datas):
    out = []
    for d in datas:
      out.append(self.step(d))
      out.append(self.step())
    return out


@pytest.mark.parametrize("active,requested,build,running", [(1, 1, 0x02, 0), (0, 0, 0x02, 0), (3, 3, 0x0A, 8), (4, 4, 0x05, 8)],
                         ids=["MM02_mode1", "MM02_stock", "0x0A_angle", "0x05_mode4"])
def test_v1_builds_are_unsupported_in_torque_mode(active, requested, build, running):
  ci = clarity(); f = Feed(ci)
  states = f.run([v1(active, requested, build, counter=k % 4, b0_extra=running) for k in range(10)])
  assert states[-1].steerFaultTemporary and ci.CS.eps_cal_status.fault == "unsupported_build"
  assert ci.CS.eps_cal_status.build_id == build


def test_torque_mode_on_an_angle_eps_is_not_built():
  # an angle build has no torque PTM mode: openpilot's PTM torque tune on the EPS's stock tables must not steer
  ci = clarity(); f = Feed(ci)
  states = f.run([v4(mode=0, steering=False, reason=1, counter=k % 4) for k in range(10)])
  assert states[-1].steerFaultTemporary and ci.CS.eps_cal_status.fault == "mode_not_built"


def test_0x0F_is_a_known_v3_build():
  ci = clarity(); f = Feed(ci)
  f.run([v4(build=0x0F, counter=k % 4) for k in range(10)])
  assert ci.CS.eps_cal_status.fault != "unknown_build" and ci.CS.eps_cal_status.build_id == 0x0F and ci.CS.eps_cal_status.protocol == 3


@pytest.mark.parametrize("build", [0x0B, 0x0C, 0x0D])
def test_v2_builds_are_unknown(build):
  # protocol v2 is retired: a 0x0B-0x0D EPS faults and never steers until it is flashed to a v3 build
  ci = clarity(); f = Feed(ci)
  states = f.run([v4(build=build, counter=k % 4) for k in range(10)])
  assert states[-1].steerFaultTemporary and ci.CS.eps_cal_status.fault == "unknown_build"
  assert ci.CS.eps_cal_status.protocol is None


def test_status_lost_after_timeout_then_recovers():
  ci = clarity(); f = Feed(ci)
  f.run([v1(counter=k % 4) for k in range(10)])
  assert ci.CS.eps_cal_status.fault == "unsupported_build"
  states = [f.step() for _ in range(STATUS_TIMEOUT_FRAMES + 2)]
  assert states[-1].steerFaultTemporary and ci.CS.eps_cal_status.fault == "lost"
  f.run([v1(counter=k % 4) for k in range(10, 14)])
  assert ci.CS.eps_cal_status.fault == "unsupported_build"


def test_no_status_frame_is_cleanptm_behaviour():
  ci = clarity(); f = Feed(ci)
  assert not any(s.steerFaultTemporary for s in f.run([None] * 200))
  assert ci.CS.eps_cal_status.enabled and not ci.CS.eps_cal_status.announced


def test_bad_checksum_frames_are_ignored():
  ci = clarity(); f = Feed(ci)
  bad = [v4(counter=k % 4)[:7] + bytes([v4(counter=k % 4)[7] ^ 0x01]) for k in range(40)]
  assert not any(s.steerFaultTemporary for s in f.run(bad))
  assert not ci.CS.eps_cal_status.announced


def test_stock_fw_clarity_and_other_cars_ignore_the_frame():
  ci = clarity(b'39990-TRW-A020\x00\x00'); f = Feed(ci)
  assert not ci.CS.eps_cal_status.enabled
  assert not any(s.steerFaultTemporary for s in f.run([v1(active=0, counter=k % 4) for k in range(20)]))


@pytest.mark.parametrize("frame,capable", [
  (lambda k: v1(counter=k % 4), False),                          # layout 1 (v1 build): not angle-capable
  (lambda k: v4(build=0x0D, counter=k % 4), False),              # v2 build: layout 4 but not in V3_BUILDS
  (lambda k: v4(build=0x0E, counter=k % 4), True),
  (lambda k: v4(build=0x10, mode=0, steering=False, reason=1, counter=k % 4), True),   # announces whatever the active mode
], ids=["v1", "v2_0x0D", "v3_0x0E", "v3_0x10_stock_mode"])
def test_angle_capable_only_for_a_v3_layout4_build(frame, capable):
  ci = clarity()
  f = Feed(ci)
  assert not ci.CS.eps_cal_status.angle_capable
  f.run([frame(k) for k in range(10)])
  assert ci.CS.eps_cal_status.angle_capable is capable


def test_no_status_frame_is_never_angle_capable():
  ci = clarity()
  f = Feed(ci)
  f.run([None] * 200)
  assert not ci.CS.eps_cal_status.angle_capable
