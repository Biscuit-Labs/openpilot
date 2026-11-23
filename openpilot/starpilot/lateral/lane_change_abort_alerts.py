"""Blindspot-abort presentation. The aborted alert urgently asks the driver to take control because the car may keep
moving; it never changes lane-change or control authority."""

from openpilot.selfdrive.selfdrived.events import Alert, AlertSize, AlertStatus, AudibleAlert, Priority, VisualAlert
from openpilot.starpilot.lateral.lane_change_status_wire import Phase


ABORTED_ALERT_TYPE = "laneChangeAbortedBlindspot/warning"
ABORTED_EVENT_TYPE = "laneChangeAbortedBlindspot"


def lane_change_abort_alert(status, now_ns):
  """The abort warning and the late blindspot warning, bounded by the wire's valid_until."""
  if status is None or type(status.phase) is not Phase:
    return None
  if not (0 < status.observed_mono_time_ns <= now_ns <= status.valid_until_mono_time_ns):
    return None
  if status.phase == Phase.ABORTED_BLINDSPOT:
    alert = Alert("Take Control", "Lane Change Aborted: Vehicle in Blind Spot", AlertStatus.userPrompt, AlertSize.mid,
                  Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1)
    alert.alert_type, alert.event_type = ABORTED_ALERT_TYPE, ABORTED_EVENT_TYPE
    return alert
  return None
