"""Optional blindspot-abort presentation; never changes lane-change or control authority."""

from openpilot.selfdrive.selfdrived.events import Alert, AlertSize, AlertStatus, AudibleAlert, Priority, VisualAlert
from openpilot.starpilot.lateral.lane_change_status_wire import Phase


ABORTED_ALERT_TYPE = "laneChangeAbortedBlindspot/warning"
ABORTED_EVENT_TYPE = "laneChangeAbortedBlindspot"
LATE_ALERT_TYPE = "laneChangeLateBlindspot/warning"
LATE_EVENT_TYPE = "laneChangeLateBlindspot"


def lane_change_abort_alert(status, now_ns):
  """The abort warning and the late blindspot warning, bounded by the wire's valid_until."""
  if status is None or type(status.phase) is not Phase:
    return None
  if not (0 < status.observed_mono_time_ns <= now_ns <= status.valid_until_mono_time_ns):
    return None
  if status.phase == Phase.ABORTED_BLINDSPOT:
    alert = Alert("Lane Change Aborted", "Vehicle in Blind Spot", AlertStatus.userPrompt, AlertSize.mid,
                  Priority.MID, VisualAlert.none, AudibleAlert.prompt, .1)
    alert.alert_type, alert.event_type = ABORTED_ALERT_TYPE, ABORTED_EVENT_TYPE
    return alert
  if status.phase == Phase.LATE_BLINDSPOT:
    alert = Alert("Vehicle in Blind Spot", "", AlertStatus.userPrompt, AlertSize.small,
                  Priority.MID, VisualAlert.none, AudibleAlert.warningSoft, .1)
    alert.alert_type, alert.event_type = LATE_ALERT_TYPE, LATE_EVENT_TYPE
    return alert
  return None
