from types import SimpleNamespace

from openpilot.system import timed

# Route 0000008e (11-04 22:56 UTC): the modem decoded its first satellite's time 15 s after the GPS came on, with the
# week still unknown (65535); the time of week alone was 0.7 s from the true clock.
TRUE_UTC = 1_793_919_389.0
MONO = 38.3


def report(utc=TRUE_UTC, week=65535, known=True, source='gps'):
  gps = utc - timed.GPS_EPOCH + timed.GPS_LEAP_SECONDS
  status = SimpleNamespace(satelliteTimeIsKnown=known)
  return SimpleNamespace(source=source, gpsWeek=week, milliseconds=int(round((gps % timed.GPS_WEEK) * 1000)),
                         sv=[SimpleNamespace(measurementStatus=status)])


def feed(satellite, reports):
  result = None
  for n, r in enumerate(reports):
    result = satellite.update(r, MONO + n)
  return result


def test_week_comes_from_the_last_valid_time():
  satellite = timed.SatelliteTime(TRUE_UTC - 3 * 86400)
  offset, confirmed = feed(satellite, [report(TRUE_UTC + n) for n in range(3)])
  assert not confirmed
  assert abs(offset + MONO - TRUE_UTC) < 1e-3


def test_week_rolls_over_when_the_last_time_was_late_in_the_previous_week():
  last = TRUE_UTC - 2 * 3600
  gps_last = last - timed.GPS_EPOCH + timed.GPS_LEAP_SECONDS
  now = last + (timed.GPS_WEEK - gps_last % timed.GPS_WEEK) + 600  # ten minutes into the next GPS week
  satellite = timed.SatelliteTime(last)
  offset, _ = feed(satellite, [report(now + n) for n in range(3)])
  assert abs(offset + MONO - now) < 1e-3


def test_confirmed_week_needs_no_saved_time():
  gps = TRUE_UTC - timed.GPS_EPOCH + timed.GPS_LEAP_SECONDS
  satellite = timed.SatelliteTime(None)
  offset, confirmed = feed(satellite, [report(TRUE_UTC + n, week=int(gps // timed.GPS_WEEK)) for n in range(3)])
  assert confirmed
  assert abs(offset + MONO - TRUE_UTC) < 1e-3


def test_nothing_without_a_week_or_a_saved_time():
  assert feed(timed.SatelliteTime(None), [report(TRUE_UTC + n) for n in range(5)]) is None


def test_nothing_until_a_satellite_time_is_known_or_from_glonass():
  satellite = timed.SatelliteTime(TRUE_UTC - 86400)
  assert feed(satellite, [report(TRUE_UTC + n, known=False) for n in range(5)]) is None
  assert feed(satellite, [report(TRUE_UTC + n, source='glonass') for n in range(5)]) is None


def test_reports_must_agree():
  satellite = timed.SatelliteTime(TRUE_UTC - 86400)
  assert feed(satellite, [report(TRUE_UTC), report(TRUE_UTC + 1), report(TRUE_UTC + 2.5)]) is None


def test_never_earlier_than_the_last_valid_time():
  gps = TRUE_UTC - timed.GPS_EPOCH + timed.GPS_LEAP_SECONDS
  satellite = timed.SatelliteTime(TRUE_UTC + 86400)
  assert feed(satellite, [report(TRUE_UTC + n, week=int(gps // timed.GPS_WEEK)) for n in range(3)]) is None


def test_last_valid_time_round_trip(tmp_path, monkeypatch):
  monkeypatch.setattr(timed, 'STATE_DIR', str(tmp_path))
  monkeypatch.setattr(timed, 'LAST_TIME_FILE', str(tmp_path / 'last-valid-time'))
  assert timed.read_last_valid_time() is None
  timed.save_last_valid_time(TRUE_UTC)
  assert timed.read_last_valid_time() == int(TRUE_UTC)
  (tmp_path / 'last-valid-time').write_text('1600000000\n')  # before min_date(): written by an unset clock
  assert timed.read_last_valid_time() is None
