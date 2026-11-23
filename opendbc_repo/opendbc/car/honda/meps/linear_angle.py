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


class LinearAngle:
  def __init__(self, enabled: bool):
    self.enabled = enabled
    self.latched = False
    self.angle_deg = 0.0        # rack-linear angle (carState sign: left positive)
    self.published_deg = 0.0    # the 0x14A angle of the same pass
    self.frames_since = 0
    self.last_ts = 0

  def update(self, cp, build_id: int) -> str:
    """Returns a fault reason ("" = OK)."""
    if not self.enabled:
      return ""
    ts = cp.ts_nanos[MSG]["COUNTER"]
    if ts and ts != self.last_ts:
      self.last_ts, self.frames_since, self.latched = ts, 0, True
      self.angle_deg = float(cp.vl[MSG]["LINEAR_ANGLE"])
      self.published_deg = float(cp.vl[MSG]["PUBLISHED_ANGLE"])
    else:
      self.frames_since += 1
    if self.latched and self.frames_since > STALE_FRAMES:
      return "linear_angle_lost"
    if not self.latched and build_id in LINEAR_ANGLE_BUILDS:
      return "no_linear_angle"     # a linear-angle build that does not send 0x6A2: never steer
    return ""
