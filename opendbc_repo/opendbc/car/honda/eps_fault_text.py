"""Driver-facing text for a modified-EPS interlock fault (eps_cal_status.EpsCalStatus.fault).

Every interlock fault sets carState.steerFaultTemporary, which selfdrived shows as the generic "Steering Assist Temporarily
Unavailable". That says nothing about a firmware the openpilot build does not support. card publishes the specific text here
and selfdrived's steerTempUnavailable alert reads it, so the screen names the fault. No cereal, Params or native change: a
small file in /dev/shm shared by the two processes on the device. A missing, empty or stale (> MAX_AGE_S) file means the
generic text stays.

  card:       FaultTextPublisher.update(eps_cal_status)   every card cycle
  selfdrived: read_fault_text()                           when it builds the alert
"""
import os
import time

from opendbc.car.honda.meps.protocol import V3_BUILDS

FAULT_FILE = "/dev/shm/honda_eps_fault"
MAX_AGE_S = 2.0       # card refreshes while faulted every REFRESH_S; an older file is a dead card, not a live fault
REFRESH_S = 0.5


def describe(fault: str, build_id: int) -> str:
  """One short line for the alert's second row; "" for no fault."""
  if not fault:
    return ""
  name, _, rest = fault.partition(" ")
  why = rest.strip("() ")
  if name in ("unknown_build", "unsupported_build"):
    v3 = sorted(V3_BUILDS)
    if build_id < v3[0]:   # an older build (v1 / v2 telemetry): this openpilot speaks protocol v3 only
      return f"EPS firmware build {build_id:#04x} is not protocol v3: flash build {v3[0]:#04x} or newer"
    return f"EPS firmware build {build_id:#04x} is newer than this openpilot: update openpilot"
  if name == "no_status":
    return "EPS firmware is not reporting (no 0x6A4)"
  if name == "lost":
    return "EPS firmware status lost"
  if name == "mode_not_built":
    return f"EPS build {build_id:#04x} has no torque mode: turn Angle Mode on"
  if name == "inactive_mode":
    return "EPS is not in angle mode yet: re-engage"
  if name == "angle_fault":
    return f"EPS angle fault: {why.lower() or 'unknown'}"
  if name == "loop_not_running":
    return f"EPS angle loop did not start: {why.lower() or 'unknown'}"
  return f"EPS interlock: {fault}"


def read_fault_text(path: str = FAULT_FILE, now: float | None = None) -> str:
  """selfdrived: the live fault text, "" when there is none."""
  try:
    st = os.stat(path)
    with open(path) as f:
      text = f.read().strip()
  except OSError:
    return ""
  now = time.time() if now is None else now
  return text if text and 0.0 <= now - st.st_mtime <= MAX_AGE_S else ""


class FaultTextPublisher:
  """card: writes the text on a change and refreshes it while the fault lasts; clears it with the fault. Never raises."""

  def __init__(self, path: str = FAULT_FILE, clock=time.monotonic):
    self.path, self.clock = path, clock
    self.text, self.written = "", None

  def update(self, eps_cal_status) -> None:
    text = describe(getattr(eps_cal_status, "fault", "") if getattr(eps_cal_status, "enabled", False) else "",
                    int(getattr(eps_cal_status, "build_id", 0)))
    now = self.clock()
    if text == self.text and (not text or (self.written is not None and now - self.written < REFRESH_S)):
      return
    self.text = text
    self._write(text, now)

  def _write(self, text: str, now: float) -> None:
    try:
      tmp = self.path + ".tmp"
      with open(tmp, "w") as f:
        f.write(text)
      os.replace(tmp, self.path)
      self.written = now
    except OSError:
      self.written = None   # /dev/shm unavailable (tests, a read-only box): the generic alert stays
