"""Saved B-CAN turn signal toggle for the Honda car controller (opendbc/car/honda/bcan_blinker.py), refreshed once a second."""
import time

REFRESH_NS = 1_000_000_000


def _flag(params, key, fallback):
  try:
    value = params.get(key, return_default=True)
  except (TypeError, ValueError, RuntimeError):
    return fallback
  return fallback if value is None else bool(value)


class BcanTurnSignalsPreference:
  def __init__(self, params, clock=time.monotonic_ns):
    self.params = params
    self.clock = clock
    self.enabled = _flag(params, "HondaBcanTurnSignals", False)
    self.read_ns = clock()

  def current(self) -> bool:
    now = self.clock()
    if now - self.read_ns >= REFRESH_NS:
      self.enabled = _flag(self.params, "HondaBcanTurnSignals", False)
      self.read_ns = now
    return self.enabled
