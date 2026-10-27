"""V-ASM must read current speed/blinkers from the message card actually publishes."""
from types import SimpleNamespace

from cereal import car, custom, log
from openpilot.selfdrive.car.card import Car


def test_card_publishes_current_vasm_fields_instead_of_stale_mirror():
  sent = {}
  stub = SimpleNamespace(
    CI=SimpleNamespace(CS=SimpleNamespace()),
    _last_car_gps_received_monotonic=0.0,
    sm=SimpleNamespace(frame=1, all_checks=lambda _: True),
    pm=SimpleNamespace(send=lambda topic, message: sent.__setitem__(topic, message.to_bytes())),
    last_actuators_output=car.CarControl.Actuators.new_message(),
    can_rcv_cum_timeout_counter=0,
    rk=SimpleNamespace(remaining=0.0),
    update_accel_log_fields=lambda _: None,
  )
  state = car.CarState.new_message(canValid=True, vEgo=17.25, leftBlinker=True, rightBlinker=False)
  stale_mirror = custom.StarPilotCarState.new_message(vEgo=99.0, leftBlinker=False, rightBlinker=True)
  Car.state_publish(stub, state, None, stale_mirror)
  with log.Event.from_bytes(sent['starpilotCarState']) as published:
    assert published.valid
    assert published.starpilotCarState.vEgo == 17.25
    assert published.starpilotCarState.leftBlinker
    assert not published.starpilotCarState.rightBlinker
