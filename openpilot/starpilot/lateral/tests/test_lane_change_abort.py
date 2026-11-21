import json
from dataclasses import replace

from openpilot.starpilot.lateral.lane_change_preferences import LaneChangePolicy, decode, to_value
from openpilot.starpilot.lateral.lane_change_status_wire import Direction, LaneChangeStatus, Phase, decode as wire_decode, \
  encode as wire_encode
from openpilot.starpilot.lateral.lane_change_abort_alerts import (
  ABORTED_ALERT_TYPE, ABORTED_EVENT_TYPE, lane_change_abort_alert,
)


def test_abort_field_roundtrips_and_default_document_unchanged():
  policy = replace(LaneChangePolicy(), abort_on_blindspot=True)
  raw = json.dumps(to_value(policy)).encode()
  document = json.loads(raw)
  assert document["version"] == 6 and document["abortOnBlindspot"] is True
  assert decode(raw) == policy
  default = to_value(LaneChangePolicy())
  assert "abortOnBlindspot" not in default  # existing documents stay byte-identical
  assert decode(json.dumps(default).encode()) == LaneChangePolicy()
  # a pre-existing version 6 document without the field decodes with the abort off
  dom = to_value(replace(LaneChangePolicy(), auto_requires_cruise=True))
  assert "abortOnBlindspot" not in dom
  assert decode(json.dumps(dom).encode()).abort_on_blindspot is False


def test_abort_field_rejects_non_bool():
  base = to_value(LaneChangePolicy())
  for value in (1, 0, "true", None, ["true"]):
    assert decode(json.dumps({**base, "abortOnBlindspot": value}).encode()) is None
  # an unknown field in an older version document is still rejected
  v5 = {key: item for key, item in base.items() if key != "autoRequiresCruise"}
  assert decode(json.dumps({**v5, "version": 5, "turnSignalGuidance": True, "abortOnBlindspot": True}).encode()) is None


def test_wire_roundtrips_the_new_phases():
  assert not hasattr(Phase, "LATE_BLINDSPOT")  # the late phase is gone; the numbering is stable
  assert int(Phase.ABORTED_BLINDSPOT) == 4
  for phase, direction in ((Phase.MANUAL_REQUIRED, Direction.NONE), (Phase.WAITING_FOR_DELAY, Direction.LEFT),
                           (Phase.LANE_UNAVAILABLE, Direction.RIGHT), (Phase.BLINDSPOT_BLOCKED, Direction.LEFT),
                           (Phase.ABORTED_BLINDSPOT, Direction.NONE)):
    status = LaneChangeStatus("s", 3, 9, 10, 20, 30, phase, direction, False, True)
    raw = wire_encode(status)
    assert wire_decode(raw) == status
    assert wire_decode(raw).phase is phase


def test_abort_alert_module_maps_phases_and_honours_valid_until():
  from opendbc.car.structs import car
  from openpilot.selfdrive.selfdrived.events import AlertSize, AlertStatus, AudibleAlert, Priority
  aborted = LaneChangeStatus("s", 3, 9, 10, 20, 30, Phase.ABORTED_BLINDSPOT, Direction.NONE, False, True)
  alert = lane_change_abort_alert(aborted, 25)
  assert (alert.alert_text_1, alert.alert_text_2) == ("Take Control", "Lane Change Aborted: Vehicle in Blind Spot")
  assert (alert.alert_status, alert.alert_size) == (AlertStatus.userPrompt, AlertSize.mid)
  assert (alert.priority, alert.visual_alert, alert.audible_alert) == \
    (Priority.HIGH, car.CarControl.HUDControl.VisualAlert.steerRequired, AudibleAlert.warningImmediate)
  assert (alert.alert_type, alert.event_type) == (ABORTED_ALERT_TYPE, ABORTED_EVENT_TYPE)
  assert lane_change_abort_alert(aborted, 31) is None  # past valid_until
  assert lane_change_abort_alert(None, 25) is None
  for phase in (Phase.MANUAL_REQUIRED, Phase.WAITING_FOR_DELAY, Phase.LANE_UNAVAILABLE, Phase.BLINDSPOT_BLOCKED):
    assert lane_change_abort_alert(LaneChangeStatus("s", 3, 9, 10, 20, 30, phase, Direction.NONE, False, True), 25) is None
