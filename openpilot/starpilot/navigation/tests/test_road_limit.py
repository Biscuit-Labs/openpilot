from unittest.mock import Mock

from openpilot.starpilot.navigation.road_limit import MIN_SPEED, RoadLimit

SETTINGS = {'token': 'pk.test'}
NOW = 1_000_000_000


def make_road_limit():
  executor = Mock()
  return RoadLimit(Mock(), lambda settings: True, executor=executor), executor


def fix(speed, index=0):
  # ~110 m apart per index, well past TRACE_SPACING, so each update adds a trace point
  return 1000 + index, (-71.0, 42.0 + 0.001 * index), speed, 90.


def test_unknown_gps_speed_does_not_crash_or_request():
  # location() reports speed=None when the GPS speed is not finite (NaN/inf).
  road_limit, executor = make_road_limit()
  for index in range(4):
    result = road_limit.update(NOW + index, SETTINGS, fix(None, index), drive_id=1)
    assert result == {'locationMonoTime': 1000 + index, 'speedLimit': 0., 'controlValid': False}
  executor.submit.assert_not_called()


def test_moving_with_a_full_trace_requests_a_limit():
  road_limit, executor = make_road_limit()
  for index in range(3):
    road_limit.update(NOW + index, SETTINGS, fix(MIN_SPEED, index), drive_id=1)
  executor.submit.assert_called_once()


def test_below_minimum_speed_does_not_request():
  road_limit, executor = make_road_limit()
  for index in range(4):
    road_limit.update(NOW + index, SETTINGS, fix(MIN_SPEED - 0.1, index), drive_id=1)
  executor.submit.assert_not_called()
