"""Clarity modified EPS: the 0x6A4 EPS_CAL_STATUS interlock, protocol v2 only (build 0x0B on; meps/protocol.py, spec
rwd-xray lab/audit_fable_20261121/v2/PROTOCOL_V2.md). The v1 builds (MM 0x02, angle 0x04-0x0A, 0x6A4 layouts 2/3) are
no longer supported: any non-layout-4 status faults "unsupported_build".

On a Clarity with modified EPS firmware the interlock is enabled:
  - no 0x6A4 ever seen: torque mode (CleanPTM, P1) nothing changes; angle mode faults "no_status"
  - 0x6A4 seen, then silent for more than STATUS_TIMEOUT_FRAMES: fault "lost" (as for missing EPS frames)
  - a frame that is not layout 4 (byte 0 bit 7 clear, a v1 build): "unsupported_build"
  - a layout-4 build that is not in V2_BUILDS: "unknown_build"
  - torque mode on a v2 EPS (v2 has no torque PTM mode, the EPS runs stock tables): "mode_not_built"
  - active MODE != 1 (angle): "inactive_mode" (the EPS switches at the next LKAS idle, which the fault brings about)
  - FAULT (byte 0 bit 6): "angle_fault (<reason>)"; it drops the request and so clears it
  - an angle request for more than LOOP_START_FRAMES with STEERING (byte 0 bit 5: loop running, no fault, stock LKAS
    engaged) clear: "loop_not_running (<reason>)". STEERING stays set at AUTH 0 (reason AUTHORITY_ZERO), so a driver
    override with the request held does not trip it. Without this a request that never reaches the loop is a silent
    no-steer (audit 11-21 S-4); the fault drops the request, so it retries at the next engage.
A fault sets carState.steerFaultTemporary. Only checksum- and counter-valid frames count (CANParser drops the others).
angle_ready is True only when nothing faults; CarController sends angle payloads only then.
"""
from opendbc.car.carlog import carlog
from opendbc.car.honda.clarity_angle_mode import angle_mode
from opendbc.car.honda.meps.protocol import V2_BUILDS, V2_MODE_ANGLE, decode_layout4, is_layout4
from opendbc.car.honda.modified_eps import modified_eps
from opendbc.car.honda.values import CAR

STATUS_TIMEOUT_FRAMES = 50   # carState updates (100 Hz): 0.5 s, 25 periods of the 50 Hz frame
# carState updates (100 Hz) an angle request may go without the EPS reporting its loop running: 100 ms. Owner's 0x09 drives
# (56 engages): first 0x6A4 with the loop running 14 ms after the request rose (median), 34 ms at most.
LOOP_START_FRAMES = 10
MSG = "EPS_CAL_STATUS"


def interlock_enabled(CP) -> bool:
  """A Clarity on modified EPS firmware: the 0x6A4 interlock applies (angle or torque mode)."""
  return bool(modified_eps(CP) and CP.carFingerprint == CAR.HONDA_CLARITY)


class EpsCalStatus:
  def __init__(self, CP):
    self.enabled = interlock_enabled(CP)
    self.angle = self.enabled and angle_mode(CP)   # angle mode chosen at startup
    self.announced = False      # a valid 0x6A4 seen since start: this EPS is switch-capable
    self.frames_since = 0
    self.last_ts = 0
    self.active_mode = -1
    self.build_id = -1
    self.fault = ""             # "" = OK, else the reason
    self.loop_running = False   # STEERING (byte 0 bit 5)
    self.angle_ref_deg = 0.0
    self.angle_out = 0
    self.request_sent = False   # the angle request bit CarController sent last frame (note_angle_request)
    self.not_running_frames = 0
    self.reason = ""            # the EPS's REASON for not steering (layout 4 byte 2)
    self.clamp = False          # the EPS lateral-accel clamp is acting

  def update(self, cp) -> str:
    if not self.enabled:
      return ""
    ts = cp.ts_nanos[MSG]["COUNTER"]
    if ts and ts != self.last_ts:
      self.last_ts, self.frames_since, self.announced = ts, 0, True
    else:
      self.frames_since += 1
    if self.announced:
      fault = self._check(cp.vl[MSG])
    else:
      fault = "no_status" if self.angle else ""
    if fault != self.fault:
      carlog.warning(f"EPS_CAL_STATUS: {fault or 'ok'} (active mode {self.active_mode}, angle {self.angle}, build {self.build_id:#04x})")
      self.fault = fault
    return fault

  def _check(self, vl) -> str:
    if self.frames_since > STATUS_TIMEOUT_FRAMES:
      return "lost"
    if not is_layout4(vl):
      self.build_id = int(vl["BUILD_ID"])
      return "unsupported_build"
    return self._check_v2(vl)

  def _check_v2(self, vl) -> str:
    s = decode_layout4(vl)
    self.build_id, self.active_mode = s["build"], s["mode"]
    self.reason, self.clamp = s["reason_name"], s["clamp"]
    if self.build_id not in V2_BUILDS:
      return "unknown_build"
    if not self.angle:
      return "mode_not_built"
    if self.active_mode != V2_MODE_ANGLE:
      return "inactive_mode"
    self.loop_running = s["steering"]
    self.angle_ref_deg, self.angle_out = float(vl["ANGLE_REF"]), int(vl["ANGLE_OUT"])
    self.not_running_frames = self.not_running_frames + 1 if (self.request_sent and not self.loop_running) else 0
    if s["fault"]:
      return f"angle_fault ({self.reason})"
    if self.not_running_frames > LOOP_START_FRAMES:
      return f"loop_not_running ({self.reason})"
    return ""

  def note_angle_request(self, sent: bool) -> None:
    """CarController, every frame in angle mode: whether the 0xE4 it just built carries the angle request."""
    self.request_sent = bool(sent)
    if not self.request_sent:
      self.not_running_frames = 0

  @property
  def authority_ready(self) -> bool:
    """Every v2 build takes AUTH in byte 3 bits 7:4, so openpilot may hold the request through an override at low
    authority instead of dropping it."""
    return self.angle_ready

  @property
  def angle_ready(self) -> bool:
    """Angle mode only: a v2 EPS runs MODE 1, reports no fault, and is not lost."""
    return self.angle and self.announced and self.fault == ""
