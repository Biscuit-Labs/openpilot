#!/usr/bin/env python3
import datetime
import os
import subprocess
import time
from typing import NoReturn

import openpilot.cereal.messaging as messaging
from openpilot.common.hardware import PC
from openpilot.common.hardware.hw import Paths
from openpilot.common.time_helpers import min_date, MAX_DATE, system_time_valid
from openpilot.common.swaglog import cloudlog
from openpilot.common.params import Params
from openpilot.common.gps import get_gps_location_service

GPS_EPOCH = 315964800  # 1980-01-06 UTC
GPS_LEAP_SECONDS = 18
GPS_WEEK = 604800
STATE_DIR = os.path.join(Paths.comma_home(), "starpilot") if PC else "/data/starpilot"
LAST_TIME_FILE = os.path.join(STATE_DIR, "last-valid-time")
# Without this file the satellite time is only logged next to the fix it would have preceded (shadow mode).
FAST_TIME_LIVE_FILE = os.path.join(STATE_DIR, "fast-gps-time-live")


def _utc_timestamp(value: datetime.datetime) -> float:
  return value.replace(tzinfo=datetime.UTC).timestamp()


def read_last_valid_time() -> float | None:
  try:
    with open(LAST_TIME_FILE) as f:
      value = float(f.read().strip())
  except (OSError, ValueError):
    return None
  return value if _utc_timestamp(min_date()) <= value < _utc_timestamp(MAX_DATE) else None


def save_last_valid_time(value: float) -> None:
  try:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = LAST_TIME_FILE + ".tmp"
    with open(tmp, "w") as f:
      f.write(f"{int(value)}\n")
    os.replace(tmp, LAST_TIME_FILE)
  except OSError:
    cloudlog.exception("timed.failed_saving_last_valid_time")


class SatelliteTime:
  """The time from the first GPS satellite the modem decodes, a minute or more before its position fix.

  Until it has the ephemeris, the modem knows the time of week but not the week (65535). The week then comes from the
  last valid time saved on the device, which is right whenever it was off for less than a week.
  """
  AGREEING_REPORTS = 3
  MAX_SPREAD = 0.05

  def __init__(self, last_valid: float | None):
    self.last_valid = last_valid
    self.offsets: list[tuple[float, bool]] = []

  def update(self, report, mono: float) -> tuple[float, bool] | None:
    """Feeds one measurement report; returns (UTC minus monotonic seconds, week confirmed) once reports agree."""
    if str(report.source) != 'gps' or not 0 <= report.milliseconds < GPS_WEEK * 1000:
      return None
    if not any(sv.measurementStatus.satelliteTimeIsKnown for sv in report.sv):
      return None
    tow = report.milliseconds / 1000.
    confirmed = 1000 < report.gpsWeek < 65535
    if confirmed:
      gps_seconds = report.gpsWeek * GPS_WEEK + tow
    elif self.last_valid is not None:
      last = self.last_valid - GPS_EPOCH + GPS_LEAP_SECONDS
      gps_seconds = (last // GPS_WEEK) * GPS_WEEK + tow
      if gps_seconds < last - 60:
        gps_seconds += GPS_WEEK
    else:
      return None
    utc = gps_seconds + GPS_EPOCH - GPS_LEAP_SECONDS
    if self.last_valid is not None and utc < self.last_valid - 60:
      return None
    self.offsets = (self.offsets + [(utc - mono, confirmed)])[-self.AGREEING_REPORTS:]
    values = [offset for offset, _ in self.offsets]
    if (len(self.offsets) < self.AGREEING_REPORTS or max(values) - min(values) > self.MAX_SPREAD or
        any(c != confirmed for _, c in self.offsets)):
      return None
    return sum(values) / len(values), confirmed


def set_time(new_time):
  diff = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - new_time
  if abs(diff) < datetime.timedelta(seconds=10):
    cloudlog.debug(f"Time diff too small: {diff}")
    return

  cloudlog.debug(f"Setting time to {new_time}")
  try:
    subprocess.run(f"TZ=UTC date -s '{new_time}'", shell=True, check=True)
  except subprocess.CalledProcessError:
    cloudlog.exception("timed.failed_setting_time")


def clock_message():
  msg = messaging.new_message('clocks')
  msg.valid = system_time_valid()
  mono = time.monotonic_ns()
  boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
  if time.monotonic_ns() - mono <= 1_000_000:
    # Retain the existing wire fields for replay's clock pair, independently of wall-clock corrections.
    msg.logMonoTime = mono
    msg.clocks.deprecated.monotonicNanos = mono
    msg.clocks.deprecated.bootTimeNanos = boot
  msg.clocks.wallTimeNanos = time.time_ns()
  return msg


def main() -> NoReturn:
  """
    timed has two responsibilities:
    - getting the current time from GPS
    - publishing the time in the logs

    AGNOS will also use NTP to update the time.
  """

  params = Params()
  gps_location_service = get_gps_location_service(params)

  pm = messaging.PubMaster(['clocks'])
  sm = messaging.SubMaster([gps_location_service])
  qcom = messaging.sub_sock('qcomGnss', conflate=False)
  satellite = SatelliteTime(read_last_valid_time())
  fast = None  # (UTC minus monotonic, week confirmed, monotonic when ready)
  provisional = False  # the clock rests on a guessed week: don't save it as the last valid time
  checked = False
  last_saved = float('-inf')
  while True:
    sm.update(1000)

    pm.send('clocks', clock_message())

    now = time.monotonic()
    valid = system_time_valid()
    for event in messaging.drain_sock(qcom):
      if valid or event.qcomGnss.which() != 'measurementReport':
        continue
      result = satellite.update(event.qcomGnss.measurementReport, event.logMonoTime / 1e9)
      if result is None or (fast is not None and (fast[1] or not result[1])):
        continue
      fast = (*result, now if fast is None else fast[2])
      live = os.path.exists(FAST_TIME_LIVE_FILE)
      cloudlog.event("timed.fast_gps_time", mode="live" if live else "shadow", time=round(result[0] + now, 3),
                     week_confirmed=result[1], boot_seconds=round(time.clock_gettime(time.CLOCK_BOOTTIME), 1))
      if live:
        set_time(datetime.datetime.fromtimestamp(result[0] + time.monotonic(), datetime.UTC).replace(tzinfo=None))
        provisional = not result[1]
        valid = system_time_valid()

    if valid and not provisional and now - last_saved >= 60:
      save_last_valid_time(time.time_ns() / 1e9)
      last_saved = now

    gps = sm[gps_location_service]
    gps_time = datetime.datetime.fromtimestamp(gps.unixTimestampMillis / 1000., datetime.UTC).replace(tzinfo=None)
    if not sm.updated[gps_location_service] or (time.monotonic() - sm.logMonoTime[gps_location_service] / 1e9) > 2.0:
      continue
    if not gps.hasFix:
      continue
    if gps_time < min_date() or gps_time > MAX_DATE:
      continue

    if fast is not None and not checked:
      fix_mono = sm.logMonoTime[gps_location_service] / 1e9
      cloudlog.event("timed.fast_gps_time_check", error=round(fast[0] + fix_mono - gps.unixTimestampMillis / 1000., 3),
                     week_confirmed=fast[1], seconds_before_fix=round(fix_mono - fast[2], 1))
    checked = True
    provisional = False
    set_time(gps_time)
    time.sleep(10)

if __name__ == "__main__":
  main()
