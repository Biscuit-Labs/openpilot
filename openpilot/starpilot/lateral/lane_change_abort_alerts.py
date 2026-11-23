"""Blindspot-abort presentation. The aborted alert is critical: dropping the desire does not steer the car back (the
model can still finish the change), so the alert is the real mitigation. It never changes lane-change or control
authority."""

from openpilot.selfdrive.selfdrived.events import Alert, AlertSize, AlertStatus, AudibleAlert, Priority, VisualAlert
from openpilot.starpilot.lateral.lane_change_status_wire import Phase


ABORTED_ALERT_TYPE = "laneChangeAbortedBlindspot/warning"
ABORTED_EVENT_TYPE = "laneChangeAbortedBlindspot"


def lane_change_abort_alert(status, now_ns):
  """The abort warning, bounded by the wire's valid_until.

  Not gated on fresh_for_model like the pre-lane-change wording: that requires the status direction to match the
  model's lane-change direction, and an abort resets both to none, so it could never pass. modeld sets valid_until
  150 ms after each status, and selfdrived also requires the service alive and valid, so the alert cannot outlive
  modeld's last abort status by more than 150 ms."""
  if status is None or type(status.phase) is not Phase:
    return None
  if not (0 < status.observed_mono_time_ns <= now_ns <= status.valid_until_mono_time_ns):
    return None
  if status.phase == Phase.ABORTED_BLINDSPOT:
    alert = Alert("Take Control", "Lane Change Aborted: Vehicle in Blind Spot", AlertStatus.critical, AlertSize.mid,
                  Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1)
    alert.alert_type, alert.event_type = ABORTED_ALERT_TYPE, ABORTED_EVENT_TYPE
    return alert
  return None
