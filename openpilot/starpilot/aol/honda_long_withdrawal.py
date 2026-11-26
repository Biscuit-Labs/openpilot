"""Honda stock-AOL lateral retention through a driver's longitudinal withdrawal (brake or CANCEL).

Split from transport_pause.py to keep it under the source size limit; the TransportPauseFeedback methods delegate here.
"""
from openpilot.starpilot.aol.runtime import AXIS_MAX_AGE_NS, SAFETY_MAX_AGE_NS


def independent_lateral_health(*args, **kwargs):
  from openpilot.starpilot.aol.transport_pause import independent_lateral_health as health
  return health(*args, **kwargs)


def long_withdrawal_lateral_current(self, sm, cp, cs, axis, now_ns, *, latched, source_ns, started, require_long_request):
  from opendbc.car.honda.stock_aol import qualified
  from opendbc.car.structs import car

  if (not qualified(cp, marked_only=True) or not latched or self.failed or self.paused or self.pending_event or
    not self.session or str(axis.sessionId) != self.session or
    not self.healthy_feedback_ns or not 0 <= now_ns - self.healthy_feedback_ns <= AXIS_MAX_AGE_NS or
    not 0 < source_ns <= now_ns or now_ns - source_ns > SAFETY_MAX_AGE_NS or
    (not started and now_ns - source_ns > AXIS_MAX_AGE_NS) or
    cs.accFaulted or cs.seatbeltUnlatched or
    cs.gearShifter not in (car.CarState.GearShifter.drive, car.CarState.GearShifter.sport,
                          car.CarState.GearShifter.low, car.CarState.GearShifter.brake) or
    str(axis.faultReason) != 'none' or not axis.desiredLateral or not axis.lateralActive or
    (not axis.nativeAcknowledged and (axis.desiredLongitudinal or axis.longitudinalActive)) or
    not 0 < axis.sourceCarStateMonoTime <= axis.observedMonoTime or
    axis.observedMonoTime - axis.sourceCarStateMonoTime > AXIS_MAX_AGE_NS):
    return None
  event_ns = int(sm.logMonoTime['onroadEvents'])
  if (not sm.seen['onroadEvents'] or not sm.valid['onroadEvents'] or not sm.alive['onroadEvents'] or
      not 0 < event_ns <= now_ns or now_ns - event_ns > 1_500_000_000 or
      any(e.immediateDisable or e.softDisable for e in sm['onroadEvents'])):
    return None
  native = independent_lateral_health(sm, cp, cs, self.session, now_ns)
  if (native is None or not native.requestedLateral or not native.lateralAllowed or
      (require_long_request and not native.requestedLongitudinal) or native.observedMonoTime < self.healthy_native_ns or
      (native.pandaSerial, tuple(p.hardwareSerial for p in native.pandaInventory)) != self.healthy_inventory):
    return None
  return native

def brake_lateral_current(self, sm, cp, cs, axis, now_ns, *, latched, brake_source_ns):
  from opendbc.car.honda.stock_aol import qualified
  from opendbc.car.structs import car

  source_ns = self.honda_brake_ns or (brake_source_ns if cs.brakePressed else 0)
  # Night Star: the panda's brake can reach pandad's native read before Card's CAN batch. A LONG-only drop
  # with controls_allowed already false waits AXIS_MAX_AGE_NS from that first read for the brake edge.
  # A CANCEL Card has already parsed is not that race: it belongs to _honda_cancel_lateral_current.
  cancel = any(e.type == car.CarState.ButtonEvent.Type.cancel and e.pressed for e in cs.buttonEvents)
  native_first = not source_ns and not cs.brakePressed and not cancel
  if native_first and latched and self.session and not self.failed and qualified(cp, marked_only=True):
    first = independent_lateral_health(sm, cp, cs, self.session, now_ns)
    if (first is not None and not first.longitudinalAllowed and first.pandaInventory and
        not any(p.controlsAllowed for p in first.pandaInventory)):
      self.honda_native_first_ns = self.honda_native_first_ns or int(first.observedMonoTime)
      source_ns = self.honda_native_first_ns
    elif first is not None and first.longitudinalAllowed:
      self.honda_native_first_ns = 0
  native = long_withdrawal_lateral_current(self, sm, cp, cs, axis, now_ns,
    latched=latched, source_ns=source_ns, started=bool(self.honda_brake_ns), require_long_request=True)
  if native is not None and not native_first:
    self.honda_brake_ns = source_ns
  return native

def cancel_lateral_current(self, sm, cp, cs, axis, now_ns, *, latched, cancel_source_ns):
  from opendbc.car.structs import car
  cancel = any(e.type == car.CarState.ButtonEvent.Type.cancel and e.pressed for e in cs.buttonEvents)
  source_ns = self.honda_cancel_ns or (cancel_source_ns if cancel else 0)
  native = long_withdrawal_lateral_current(self, sm, cp, cs, axis, now_ns,
    latched=latched, source_ns=source_ns, started=bool(self.honda_cancel_ns), require_long_request=False)
  if native is not None:
    self.honda_cancel_ns = source_ns
  return native
