"""Honda modified-EPS wire protocol v3 (build 0x0E on), one place. Earlier protocols (v1 builds 0x04-0x0A, v2 builds
0x0B-0x0D) are no longer supported: eps_cal_status faults them and nothing steers.

Spec: rwd-xray lab/PROTOCOL_V3_20261125.md.

0xE4 (openpilot -> EPS): an angle frame is marked by byte 2 bits 3:2 = 3 with the request bit 0, a value no camera or radar
  ever sends with its own torque and inert on any other firmware (request 0). Byte 2 bit 6 = DRIVE (1) / YIELD (0, loop
  authority 0 at once); bytes 0-1 the plain target; byte 3 0 (a stock-ACC Bosch radar re-packs 0xE4 and drops byte 3 and
  byte 2 bits 5:4). STANDBY (byte 2 = 0x0D, target 0) while not steering lets the EPS select its angle table set at LKAS
  idle. Any other frame is a torque frame with stock meaning (the EPS runs its stock tables).
0x6A4 EPS_CAL_STATUS (EPS -> openpilot, 50 Hz), layout 4:
  byte 0 layout (7) | FAULT (6) | STEERING (5) | CLAMP (4) | stock LKAS state (3:2) | active MODE (1:0);
  byte 1 build ID; byte 2 gain (7:4) | REASON (3:0); bytes 3-6 reference and output.
  Layout 4 is told apart by byte 0 bit 7 (a v1 layout-3 frame never sets it; eps_cal_status faults those
  "unsupported_build"). It is decoded from the layout-3 DBC signals, which cover byte 0 and byte 2 bits 4:0.
"""
from enum import IntEnum

V3_BUILDS = {0x0E}  # build IDs that speak protocol v3 (0x6A4 layout 4); any other layout-4 build never steers
KNOWN_BUILDS = V3_BUILDS
MODE_ANGLE = 1      # 0x6A4 active MODE: 0 stock tables, 1 angle tables
LINEAR_ANGLE_BUILDS = {0x0E}  # builds that send 0x6A2 EPS_LINEAR_ANGLE (100 Hz): the rack-linear angle next to the published one


class Reason(IntEnum):
  STEERING = 0
  NO_REQUEST = 1
  MODE_SWITCH_PENDING = 2
  PROTOCOL = 3
  JUMP = 4
  STALE = 5
  ANGLE_INVALID = 6
  AUTHORITY_ZERO = 7
  STOCK_LKAS_NOT_ENGAGED = 8


V3_ANGLE = 0x0C      # byte 2: bits 3:2 = 3, request (bit 7) = 0
V3_DRIVE = 0x40      # byte 2 bit 6 in an angle frame: 1 = drive (authority slews to full), 0 = yield (authority 0 at once)
V3_STANDBY = 0x0D    # byte 2 while not steering: angle marker + bits 1:0 = 01, target 0


def v3_byte2(drive: bool) -> int:
  return V3_ANGLE | (V3_DRIVE if drive else 0)


def is_v3_angle(b2: int) -> bool:
  """Byte 2 of an angle frame (drive or yield): bits 3:2 = 3, request 0, bits 5:4 and 1:0 = 0."""
  return (b2 & 0xBF) == V3_ANGLE


def protocol_of(build_id: int) -> int | None:
  return 3 if build_id in V3_BUILDS else None


def is_layout4(vl) -> bool:
  return (int(vl["REQUESTED_MODE"]) & 0x8) != 0


def decode_layout4(vl) -> dict:
  """Layout-4 fields from the layout-3 DBC signals of the same bytes."""
  hi = int(vl["REQUESTED_MODE"])                                   # byte 0 bits 7:4 = layout, FAULT, STEERING, CLAMP
  b0_low = (int(vl["ANGLE_LOOP_RUNNING"]) << 3) | int(vl["ACTIVE_MODE"])   # byte 0 bits 3:0
  reason = (int(vl["ANGLE_TARGET_HELD"]) << 3) | (int(vl["ANGLE_FAULT_WHY"]) << 1) | int(vl["ANGLE_FAULT"])
  try:
    reason_name = Reason(reason).name
  except ValueError:
    reason_name = f"REASON_{reason}"
  return dict(fault=bool(hi & 0x4), steering=bool(hi & 0x2), clamp=bool(hi & 0x1), lkas=(b0_low >> 2) & 0x3,
              mode=b0_low & 0x3, build=int(vl["BUILD_ID"]), reason=reason, reason_name=reason_name)
