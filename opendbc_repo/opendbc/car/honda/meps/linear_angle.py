"""Linear-angle EPS (build 0x0C on): 0x6A2 EPS_LINEAR_ANGLE carries the rack-linear angle (the EPS raw angle minus its
reference, before the firmware VGR map) next to the published 0x14A angle of the same pass, at 100 Hz. On such an EPS
0xE4 bytes 0-1 are a target in those linear units, panda checks against them (honda.h, latched by the first valid 0x6A2),
and openpilot steers in them: carState.steeringAngleDeg is the linear angle and the lateral controller uses a plain
vehicle model with paramsd's single steer ratio (no VGR table, no rack map). VSR stays in the EPS.

Same latch as panda: the first valid 0x6A2 (CANParser checks checksum and counter) latches linear mode until restart; a
stale 0x6A2 after that is a temporary steering fault, never a silent switch back to the published angle."""
from opendbc.car.honda.meps.protocol import LINEAR_ANGLE_BUILDS

MSG = "EPS_LINEAR_ANGLE"
STALE_FRAMES = 5   # carState updates (100 Hz): 50 ms, panda's measured-angle timeout
# carState updates without a new 0x6A2 after which CarController stops sending the angle request: 30 ms, two 100 Hz
# frames inside panda's 50 ms block (carState sees the bus 10-20 ms after panda does), so openpilot drops the request
# before panda would block a frame; the fault (STALE_FRAMES) follows and disengages
SEND_FRAMES = 3


class LinearAngle:
  """required: a profile car (angle_profiles.py), linear from the start: until the first valid 0x6A2 it never steers,
  whatever build 0x6A4 reports (panda: 0x6A2 is its RX check)."""
  def __init__(self, enabled: bool, required: bool = False):
    self.enabled = enabled
    self.required = enabled and required
    self.latched = False
    self.angle_deg = 0.0        # rack-linear angle (carState sign: left positive)
    self.published_deg = 0.0    # the 0x14A angle of the same pass
    self.frames_since = 0
    self.last_ts = 0
    self.build_id = -1
    self.fault_reason = ""
    self.ref_latched = True     # 0x6A2 byte 6 bit 1 (REF_LATCHED), where the platform DBC has it

  @property
  def steer_ok(self) -> bool:
    """CarController may send an angle request: 0x6A2 not needed (0x0B), or latched and fresh. A linear-angle build
    (or a profile car) without a fresh 0x6A2 never gets a request, whatever 0x6A4 says."""
    if not self.enabled:
      return True
    if self.latched:
      return self.ref_latched and self.frames_since <= SEND_FRAMES
    return not self.required and self.build_id not in LINEAR_ANGLE_BUILDS

  def update(self, cp, build_id: int) -> str:
    """Returns a fault reason ("" = OK)."""
    self.fault_reason = self._update(cp, build_id)
    return self.fault_reason

  def _update(self, cp, build_id: int) -> str:
    if not self.enabled:
      return ""
    self.build_id = build_id
    ts = cp.ts_nanos[MSG]["COUNTER"]
    if ts and ts != self.last_ts:
      self.last_ts, self.frames_since, self.latched = ts, 0, True
      self.angle_deg = float(cp.vl[MSG]["LINEAR_ANGLE"])
      self.published_deg = float(cp.vl[MSG]["PUBLISHED_ANGLE"])
      # an EPS that latches its reference from an external SAS (TJB, T5R, V850) sends the published SAS with REF_LATCHED
      # 0 until the latch: a sane angle, but not the linear one, and the EPS refuses to steer. Platform DBCs without the
      # signal (the Clarity's: its reference is its own) are always latched.
      self.ref_latched = bool(cp.vl[MSG].get("REF_LATCHED", 1))
    else:
      self.frames_since += 1
    if self.latched and self.frames_since > STALE_FRAMES:
      return "linear_angle_lost"
    if self.latched and not self.ref_latched:
      return "linear_angle_not_aligned"   # not ready: a temporary fault until the EPS latches its reference
    if not self.latched and (self.required or build_id in LINEAR_ANGLE_BUILDS):
      return "no_linear_angle"     # a linear-angle build that does not send 0x6A2: never steer
    return ""
