"""DisableSeatbeltCheck: the driver's own choice to drive with the seatbelt check off, refreshed once a second.

card clears carState.seatbeltUnlatched while it is on. 7.0 reads that field in many places (the alert, AOL availability,
longitudinal gating, the stock-AOL cancel), so clearing it at the source turns the check off everywhere at once.
"""
import time

REFRESH_NS = 1_000_000_000


class SeatbeltCheck:
  def __init__(self, params, clock=time.monotonic_ns):
    self.params = params
    self.clock = clock
    self.read_ns = clock()
    self.value = self._read()

  def _read(self) -> bool:
    try:
      return bool(self.params.get_bool("DisableSeatbeltCheck"))
    except Exception:
      return False

  def disabled(self) -> bool:
    now = self.clock()
    if now - self.read_ns >= REFRESH_NS:
      self.value = self._read()
      self.read_ns = now
    return self.value

  def apply(self, CS) -> None:
    if self.disabled():
      CS.seatbeltUnlatched = False
