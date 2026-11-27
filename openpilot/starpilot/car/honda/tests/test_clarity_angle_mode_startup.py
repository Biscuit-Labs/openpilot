from opendbc.car import structs
from opendbc.car.honda.values import CAR, HondaFlags
from opendbc.car.honda.tests.test_modified_eps import eps, params
from opendbc.car.honda.tests.test_clarity_angle_mode import MODIFIED
from openpilot.starpilot.car.honda import clarity_angle_mode as startup


class Params:
  def __init__(self, value=None, error=None, announced=True):
    self.value, self.error, self.announced = value, error, announced

  def get(self, key, return_default=False):
    assert return_default
    if key == "HondaAngleEpsAnnounced":
      return self.announced
    assert key == "HondaClarityAngleMode"
    if self.error:
      raise self.error
    return self.value


ANGLE = structs.CarParams.SteerControlType.angle


def angle(cp):
  return bool(cp.flags & HondaFlags.CLARITY_ANGLE_MODE) and cp.steerControlType == ANGLE


def test_setting_on_picks_angle_mode_on_a_modified_clarity():
  assert angle(startup.prepare(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), Params(True)))


def test_setting_off_keeps_torque():
  assert not angle(startup.prepare(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), Params(False)))


def test_unreadable_or_unknown_setting_uses_the_default_on():
  assert startup.DEFAULT is True
  assert angle(startup.prepare(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), Params(None)))
  assert angle(startup.prepare(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), Params(error=KeyError("unknown"))))


def test_stock_eps_clarity_is_never_switched():
  assert not angle(startup.prepare(params(CAR.HONDA_CLARITY, [eps(b'39990-TRW-A020\x00\x00')]), Params(True)))


def test_unannounced_clarity_keeps_torque_mode_whatever_the_setting_says():
  # the default "on" must not put a stock / torque PTM Clarity (no 0x6A4, so "no_status") into angle mode
  for value in (True, None):
    cp = startup.prepare(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), Params(value, announced=False))
    assert not angle(cp) and cp.flags & HondaFlags.EPS_MODIFIED


def test_unannounced_clarity_on_an_angle_image_still_picks_angle_mode():
  # a '+' part number is the proof itself: it must reach angle mode to see its first 0x6A4
  fw = [eps(b'39990+TRW+A020\x00\x00')]
  cp = params(CAR.HONDA_CLARITY, fw)
  cp.carFw = fw   # car_helpers sets it before the startup hook
  assert angle(startup.prepare(cp, Params(True, announced=False)))


def test_unreadable_announcement_counts_as_not_announced():
  p = Params(True)
  p.get = lambda key, return_default=False: (_ for _ in ()).throw(KeyError("unknown")) if key == "HondaAngleEpsAnnounced" else True
  assert not angle(startup.prepare(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), p))


class Saved:
  def __init__(self, value=False):
    self.values = {startup.ANNOUNCED_PARAM: value}
    self.writes = []

  def get(self, key, return_default=False):
    return self.values[key]

  def put_bool(self, key, value):
    self.values[key] = value
    self.writes.append(value)


class Status:
  enabled = True
  angle_capable = False


class Clock:
  t = 0.0

  def __call__(self):
    self.t += 0.01
    return self.t


def test_announcement_is_saved_once_when_a_v3_build_reports():
  saved, status = Saved(False), Status()
  a = startup.AngleAnnouncement(saved, Clock())
  for _ in range(100):
    a.update(status, 0.0, True)
  assert saved.writes == []
  status.angle_capable = True
  for _ in range(100):
    a.update(status, 0.0, True)
  assert saved.writes == [True] and saved.values[startup.ANNOUNCED_PARAM] is True


def test_announcement_clears_after_a_drive_without_any_0x6A4():
  saved, status = Saved(True), Status()
  a = startup.AngleAnnouncement(saved, Clock())
  n = int(startup.CLEAR_AFTER_DRIVE_S / 0.01)
  for _ in range(n - 100):
    a.update(status, 20.0, True)
  assert saved.writes == []                       # not yet a full drive
  for _ in range(200):
    a.update(status, 20.0, True)
  assert saved.writes == [False]


def test_announcement_survives_parking_bad_can_and_a_late_frame():
  saved, status = Saved(True), Status()
  a = startup.AngleAnnouncement(saved, Clock())
  n = int(startup.CLEAR_AFTER_DRIVE_S / 0.01) + 500
  for _ in range(n):
    a.update(status, 0.0, True)                    # parked: not a drive
  for _ in range(n):
    a.update(status, 20.0, False)                  # CAN invalid: EPS presence not established
  assert saved.writes == []
  for _ in range(n // 2):
    a.update(status, 20.0, True)
  status.angle_capable = True                      # the frame arrives: the count restarts
  a.update(status, 20.0, True)
  status.angle_capable = False
  for _ in range(n // 2):
    a.update(status, 20.0, True)
  assert saved.writes == []


def test_announcement_only_runs_on_a_modified_clarity():
  assert startup.AngleAnnouncement.create(params(CAR.HONDA_CLARITY, [eps(MODIFIED)]), Saved()) is not None
  assert startup.AngleAnnouncement.create(params(CAR.HONDA_CLARITY, [eps(b'39990-TRW-A020\x00\x00')]), Saved()) is None
  assert startup.AngleAnnouncement.create(params(CAR.ACURA_RDX_3G, [eps(b'39990+TJB+A220\x00\x00')]), Saved()) is None
