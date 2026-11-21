"""B-CAN turn signal state machine (opendbc/car/honda/bcan_blinker.py), without the CAN stack."""
import logging
from types import SimpleNamespace

from opendbc.car import carlog
from opendbc.car.honda.bcan_blinker import (ADDR, BLINK_HOLD_BYTE, BUS, BcanBlinker, CANCEL, RENEW_S,
                                            SIDE_CHANGE_DELAY_S)

START_LEFT = bytes([0x30, 0x0A, BLINK_HOLD_BYTE, 0, 0, 0, 0, 0])
START_RIGHT = bytes([0x30, 0x0B, BLINK_HOLD_BYTE, 0, 0, 0, 0, 0])


def make_cc(left=False, right=False, lat_active=True):
  return SimpleNamespace(leftBlinker=left, rightBlinker=right, latActive=lat_active)


def make_cs(left_stalk=False, right_stalk=False, hazard=False, resp=None):
  return SimpleNamespace(left_stalk_raw=left_stalk, right_stalk_raw=right_stalk, hazard_on=hazard, bcm_kwp_resp=resp)


def step(b, cc, cs, enabled=True, now=0.0):
  return b.update(cc, cs, enabled, now)


def test_disabled_sends_nothing():
  b = BcanBlinker()
  cc = make_cc(left=True)
  assert step(b, cc, make_cs(), enabled=False) == []


def test_no_desired_sends_nothing():
  b = BcanBlinker()
  for cc in (make_cc(), make_cc(left=True, right=True)):
    assert step(b, cc, make_cs()) == []


def test_start_left_with_hold_byte_and_renew():
  b = BcanBlinker()
  cc = make_cc(left=True)
  cs = make_cs()
  assert step(b, cc, cs, now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, cc, cs, now=0.5) == []  # no renew before 1.0 s
  assert step(b, cc, cs, now=RENEW_S) == [(ADDR, START_LEFT, BUS)]
  assert step(b, cc, cs, now=2 * RENEW_S) == [(ADDR, START_LEFT, BUS)]


def test_start_requires_lat_active_and_no_hazard():
  for cc in (make_cc(left=True, lat_active=False), make_cc(right=True, lat_active=False)):
    assert step(BcanBlinker(), cc, make_cs()) == []
  assert step(BcanBlinker(), make_cc(left=True), make_cs(hazard=True)) == []


def test_hazard_pauses_renewals_without_cancel():
  b = BcanBlinker()
  cc = make_cc(left=True)
  assert step(b, cc, make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, cc, make_cs(hazard=True), now=RENEW_S) == []  # no renew, and no cancel
  assert step(b, cc, make_cs(hazard=True), now=2 * RENEW_S) == []
  assert step(b, cc, make_cs(), now=3 * RENEW_S) == [(ADDR, START_LEFT, BUS)]  # renew resumes


def test_cancel_when_desired_gone_repeats_up_to_three_times():
  b = BcanBlinker()
  assert step(b, make_cc(left=True), make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.1) == []  # cancel starts on the next tick
  assert step(b, make_cc(), make_cs(), now=0.3) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.5) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.7) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.9) == []  # three cancels are the maximum


def test_gives_up_after_max_cancels_without_reply_and_can_start_again():
  b = BcanBlinker()
  assert step(b, make_cc(left=True), make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.1) == []
  assert step(b, make_cc(), make_cs(), now=0.3) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.5) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.7) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(), make_cs(), now=1.0) == []  # no 0x60: give up, the lamp expires on its own
  assert not b.cancelling and b.side is None
  assert step(b, make_cc(left=True), make_cs(), now=1.1) == [(ADDR, START_LEFT, BUS)]  # a new lane change starts


def test_cancel_stops_on_stop_reply():
  b = BcanBlinker()
  assert step(b, make_cc(left=True), make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, make_cc(), make_cs(), now=0.1) == []
  assert step(b, make_cc(), make_cs(), now=0.3) == [(ADDR, CANCEL, BUS)]
  # the 0x60 reply ends the cancel burst; a new desired side may start on the same tick
  assert step(b, make_cc(left=True), make_cs(resp=0x60), now=0.5) == [(ADDR, START_LEFT, BUS)]


def test_cancel_when_lat_active_drops():
  b = BcanBlinker()
  assert step(b, make_cc(left=True), make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, make_cc(left=True, lat_active=False), make_cs(), now=0.1) == []
  assert step(b, make_cc(left=True, lat_active=False), make_cs(), now=0.3) == [(ADDR, CANCEL, BUS)]


def test_side_change_cancels_then_starts_new_side_later():
  b = BcanBlinker()
  assert step(b, make_cc(left=True), make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, make_cc(right=True), make_cs(), now=0.1) == []  # side change: cancel first
  assert step(b, make_cc(right=True), make_cs(), now=0.3) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(right=True), make_cs(), now=0.5) == [(ADDR, CANCEL, BUS)]
  # the new side starts only after a 0x60 reply, at least SIDE_CHANGE_DELAY_S after the last cancel
  assert step(b, make_cc(right=True), make_cs(resp=0x60), now=0.6) == [(ADDR, START_RIGHT, BUS)]
  assert step(b, make_cc(right=True), make_cs(), now=0.7) == []  # no renew before RENEW_S


def test_driver_stalk_against_active_side_cancels_and_holds():
  b = BcanBlinker()
  assert step(b, make_cc(left=True), make_cs(left_stalk=True), now=0.0) == [(ADDR, START_LEFT, BUS)]
  # the driver flicks the stalk right: the cancel goes out on the same tick, and no restart while opposed
  assert step(b, make_cc(right=True), make_cs(right_stalk=True), now=0.1) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(right=True), make_cs(right_stalk=True), now=0.3) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(right=True), make_cs(right_stalk=True), now=0.5) == [(ADDR, CANCEL, BUS)]
  assert step(b, make_cc(right=True), make_cs(right_stalk=True), now=0.7) == []  # give up: no 0x60 reply
  assert step(b, make_cc(right=True), make_cs(right_stalk=True), now=0.9) == []  # opposed: no restart
  # the driver returns the stalk to center: the hold releases only once desired goes none and comes back
  assert step(b, make_cc(), make_cs(), now=1.0) == []
  assert step(b, make_cc(left=True), make_cs(left_stalk=True), now=1.1) == [(ADDR, START_LEFT, BUS)]


def test_negative_reply_locks_out_for_the_drive():
  records = []
  handler = logging.Handler()
  handler.emit = records.append
  carlog.carlog.addHandler(handler)
  try:
    b = BcanBlinker()
    assert step(b, make_cc(left=True), make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
    assert step(b, make_cc(left=True), make_cs(resp=0x7F), now=0.1) == []
    assert b.locked
    assert step(b, make_cc(left=True), make_cs(), now=0.2) == []
    assert step(b, make_cc(left=True), make_cs(), now=0.3) == []
    assert len(records) == 1  # logged once
  finally:
    carlog.carlog.removeHandler(handler)


def test_disabled_while_active_keeps_state_and_sends_nothing():
  b = BcanBlinker()
  cc = make_cc(left=True)
  assert step(b, cc, make_cs(), now=0.0) == [(ADDR, START_LEFT, BUS)]
  assert step(b, cc, make_cs(), enabled=False, now=RENEW_S) == []  # active command expires on its own
  assert step(b, cc, make_cs(), enabled=False, now=2 * RENEW_S) == []
  assert step(b, cc, make_cs(), now=3 * RENEW_S) == [(ADDR, START_LEFT, BUS)]  # state was kept


def test_never_more_than_one_frame_per_step_or_per_0p1s():
  b = BcanBlinker()
  sent_at = []
  t = 0.0
  for i in range(200):
    left = i < 60  # signal left for 0.6 s, then release
    cc = make_cc(left=left)
    for frame in step(b, cc, make_cs(), now=t):
      sent_at.append(t)
      assert len([f for f in step(b, cc, make_cs(), now=t)]) <= 1
    t += 0.01
  assert sent_at, "expected frames"
  for a, z in zip(sent_at, sent_at[1:]):
    assert z - a >= 0.1 - 1e-9
