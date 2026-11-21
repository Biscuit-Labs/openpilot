"""Link watchers and lease stand-ins for the Android Auto supervisor (split out of supervisor.py for the 120 KiB lint limit)."""

from __future__ import annotations

import os
import threading
import time
import traceback
from collections.abc import Callable

from openpilot.starpilot.system.starport import link_probe

LINK_CHECK_INTERVAL = 1.0    # how often the link watcher asks whether the car's Wi-Fi is still up
LINK_CHECK_SLOW = 1.0        # a link check slower than this is logged (NetworkManager answers over D-Bus)


class NoLease:
  """Wired sessions use no car Wi-Fi network."""
  local_ip = None

  def release(self, restore: bool = False) -> None:
    pass


class UsbLease:
  """The link of a wired session: the USB cable, via the accessory bridge."""
  local_ip = None
  lost = "The car's USB connection ended"

  def __init__(self, bridge):
    self.bridge = bridge

  def still_connected(self) -> bool:
    return not self.bridge.closed.is_set()


def _wifi_dbm(interface: str = "wlan0") -> int | None:
  """Signal level of the joined network from /proc/net/wireless (a plain file read, never D-Bus)."""
  try:
    with open("/proc/net/wireless") as handle:
      for line in handle:
        name, _, rest = line.partition(":")
        if name.strip() == interface:
          return int(float(rest.split()[2].rstrip(".")))
  except (OSError, ValueError, IndexError):
    pass
  return None


def _where(error: BaseException, depth: int = 4) -> list[str]:
  """The innermost frames of a failure, so a bare exception still says which call raised it."""
  frames = traceback.extract_tb(error.__traceback__)[-depth:]
  return [f"{os.path.basename(frame.filename)}:{frame.lineno} {frame.name}" for frame in frames]


class LinkWatch:
  """Checks the lease off the streaming thread.

  NetworkManager can take seconds to answer over D-Bus (a 5 s timeout ended three Toyota sessions on
  2026-10-08 before the car granted focus). A slow or failed check must neither stall video nor end the
  session; only a definite "not connected" does. The socket itself still fails fast on a real loss.
  """

  PROBE_INTERVAL = 2.0

  def __init__(self, lease, log: Callable[..., None], interval: float = LINK_CHECK_INTERVAL, sock=None):
    self.lease, self.log, self.interval = lease, log, interval
    self.sock = sock
    self.lost = ""
    self.wifi_dbm: int | None = None
    self.probe = None
    if not isinstance(lease, (NoLease, UsbLease)):
      try:
        self.probe = link_probe.LinkProbe(getattr(lease, "interface", "wlan0"))
      except Exception:
        self.probe = None
    self._next_probe = 0.0
    self._stop = threading.Event()
    self._thread = threading.Thread(target=self._run, name="aa_link_watch", daemon=True)

  def start(self) -> LinkWatch:
    self._thread.start()
    return self

  def stop(self) -> None:
    self._stop.set()  # a check stuck in D-Bus finishes on its own timeout; nothing waits for it

  def sample_probe(self) -> None:
    """One link sample for the diagnostics ring; never raises, never touches the streaming thread."""
    if self.probe is None:
      return
    try:
      self.probe.last_sock = self.sock
      sample = self.probe.sample(self.sock)
      if not self.wifi_dbm and sample.get("rssi"):
        self.wifi_dbm = sample["rssi"]
    except Exception:
      pass

  def _run(self) -> None:
    check = getattr(self.lease, "still_connected", None)
    wireless = not isinstance(self.lease, (NoLease, UsbLease))
    while not self._stop.is_set():
      if wireless:
        self.wifi_dbm = _wifi_dbm(getattr(self.lease, "interface", "wlan0"))
        if time.monotonic() >= self._next_probe:
          self._next_probe = time.monotonic() + self.PROBE_INTERVAL
          self.sample_probe()
      if check is not None:
        started = time.monotonic()
        try:
          connected = check()
        except Exception as error:
          connected = True  # unknown is not lost
          self.log("link_check_failed", error=str(error) or type(error).__name__, kind=type(error).__name__,
                   ms=round((time.monotonic() - started) * 1000), where=_where(error))
        else:
          spent = time.monotonic() - started
          if spent > LINK_CHECK_SLOW:
            self.log("link_check_slow", ms=round(spent * 1000), connected=connected)
        if not connected and not self._stop.is_set():
          self.lost = getattr(self.lease, "lost", "Lost the car's Wi-Fi network")
          self.log("link_lost", reason=self.lost, wifi_dbm=self.wifi_dbm)
          return
      self._stop.wait(self.interval)
