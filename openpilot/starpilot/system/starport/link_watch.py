"""Link watchers and lease stand-ins for the Android Auto supervisor (split out of supervisor.py for the 120 KiB lint limit)."""

from __future__ import annotations

import os
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path

from openpilot.starpilot.system.starport import link_probe

LINK_CHECK_INTERVAL = 1.0    # how often the link watcher asks whether the car's Wi-Fi is still up
LINK_CHECK_SLOW = 1.0        # a link check slower than this is logged (NetworkManager answers over D-Bus)
RADIO_CHECK_INTERVAL = 0.5   # how often the comma's own Wi-Fi is checked for a join or roam (a sysfs read)
RADIO_CHANGE_WINDOW = 15.0   # a join or roam this recent can still stall the car (11-02: stall came 7.5 s after a roam)


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


class SharedRadioWatch:
  """Notices the comma's own Wi-Fi joining or roaming while the car is on aa0; both share one radio.

  The link going down or up bumps carrier_changes, a plain sysfs read. The network's name is never read or logged.
  """

  def __init__(self, log: Callable[..., None], interface: str = "wlan0", interval: float = RADIO_CHECK_INTERVAL,
               counter: Path | None = None, carrier: Path | None = None, on_down: Callable[[], None] | None = None,
               on_stall: Callable[[], None] | None = None):
    self.log, self.interface, self.interval = log, interface, interval
    self.counter = counter or Path(f"/sys/class/net/{interface}/carrier_changes")
    self.carrier = carrier or Path(f"/sys/class/net/{interface}/carrier")
    self.on_down = on_down  # the other network was lost, not just roamed
    self.on_stall = on_stall  # the car's acks stopped after a change
    self.changed_at: float | None = None
    self._stop = threading.Event()
    self._thread = threading.Thread(target=self._run, name="aa_radio_watch", daemon=True)

  def start(self) -> SharedRadioWatch:
    self._thread.start()
    return self

  def stop(self) -> None:
    self._stop.set()

  def recent(self, now: float | None = None) -> bool:
    """Whether the other network joined or roamed within RADIO_CHANGE_WINDOW."""
    changed_at = self.changed_at
    now = time.monotonic() if now is None else now
    return changed_at is not None and now - changed_at <= RADIO_CHANGE_WINDOW

  def _read(self) -> str | None:
    try:
      return self.counter.read_text().strip()
    except OSError:
      return None

  def _run(self) -> None:
    last = self._read()
    while not self._stop.wait(self.interval):
      current = self._read()
      if current is None or current == last:
        continue
      last = current
      self.changed_at = time.monotonic()
      self.log("other_wifi_changed", interface=self.interface)
      if self.on_down is not None and not self._carrier():
        try:
          self.on_down()
        except Exception as error:
          self.log("other_wifi_hold_failed", error=str(error) or type(error).__name__)

  def stalled(self) -> None:
    if self.on_stall is not None:
      self.on_stall()

  def _carrier(self) -> bool:
    try:
      return self.carrier.read_text().strip() == "1"
    except OSError:
      return False  # reading carrier of a down interface fails with EINVAL
