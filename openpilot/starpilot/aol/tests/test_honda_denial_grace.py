"""Clarity route 00000135 (build 0x12), t=301.6 s: a hard takeover cleared the Honda AOL latch (cloudlog aol.latchClear reason disarming_fault at 301627.8 ms) and lateral waited for
an LKAS press, while 45 other takeovers in the route kept it. rlog order at the two (route-relative ms):
  301.6 (cleared): press since 301.36 | panda requested/allowed 1/1 -> 1/0 at 301619.5 | latch cleared 301627.8 | 0x18F STEER_STATUS 2 at 301629.2 | carState.steerFaultTemporary 1 at 301633.5
                   (the denial reaches card 14 ms BEFORE the fault flag) | fault 0 at 301653.6 | 1 at 301713.6 | panda 1/0 -> 0/0 at 301719.4
  392.5 (kept):    status 2 at 392498.6 | steerFaultTemporary 1 at 392503.1 | panda 1/1 -> 0/0 at 392519.8   (the denial reaches card 17 ms AFTER the fault flag)
card.py ORs honda_denial_grace into honda_override_shield's result (honda_shield): while it is true the transport tracker, the lost-grant check and the native-rejection check are not fed.
Each test below drives both with card's per-cycle inputs (10 ms cycles) and asserts `held = shield or grace`."""
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from openpilot.starpilot.aol.honda_override import HONDA_DENIAL_GRACE_NS, honda_denial_grace, honda_override_shield

HONDA = NS(brand="honda")
MS = 1_000_000


def cs(**kw):
  base = {'steeringPressed': True, 'steerFaultTemporary': False, 'steerFaultPermanent': False, 'canValid': True, 'canTimeout': False, 'accFaulted': False}
  return NS(**(base | kw))


@pytest.fixture(autouse=True)
def qualified():
  with patch("opendbc.car.honda.stock_aol.qualified", return_value=True):
    yield


class Card:
  """The two per-cycle calls card.py makes (shield first, then the grace, held = either)."""
  def __init__(self, latched=True):
    self.owner, self.latched = NS(), latched

  def cycle(self, t_ms, *, fault=False, denied=False, pressed=True, **cs_kw):
    state = cs(steerFaultTemporary=fault, steeringPressed=pressed, **cs_kw)
    shield = honda_override_shield(self.owner, HONDA, state, self.latched)
    grace = honda_denial_grace(self.owner, HONDA, state, native_denied=denied, latched=self.latched, now_ns=int(t_ms * MS))
    return bool(shield or grace)


def timeline(card, events, t0, t1, step=10):
  """events: list of (t_ms, dict(fault=?, denied=?, pressed=?)) state changes; returns {t: held}."""
  state, held, i = dict(fault=False, denied=False, pressed=True), {}, 0
  for t in range(t0, t1 + 1, step):
    while i < len(events) and events[i][0] <= t:
      state.update(events[i][1]); i += 1
    held[t] = card.cycle(t, **state)
  return held


def test_window_is_five_times_the_measured_skew():
  assert HONDA_DENIAL_GRACE_NS == 100 * MS


def test_301_6_denial_before_the_fault_flag_keeps_the_latch():
  # denial at 0, fault flag +14 ms (rounded to the next 10 ms cycle: 20), flickers 0 at +34 and 1 again at +94, panda 0/0 at +100
  card = Card()
  held = timeline(card, [(0, dict(denied=True)), (20, dict(fault=True)), (40, dict(fault=False)), (100, dict(fault=True, denied=False))], 0, 400)
  assert all(held.values()), [t for t, v in held.items() if not v]       # never a cycle without the hold: no disarm


def test_392_5_fault_before_the_denial_keeps_the_latch():
  card = Card()
  held = timeline(card, [(-20, dict(fault=True)), (0, dict(denied=False))], -20, 300)    # the 0/0 that follows is not a denial
  assert all(held.values())


def test_denial_with_no_temporary_fault_ever_disarms_after_the_window():
  for pressed in (True, False):
    card = Card()
    held = timeline(card, [(0, dict(denied=True, pressed=pressed))], 0, 300)
    assert all(held[t] for t in range(0, 100, 10))                        # delayed...
    assert not any(held[t] for t in range(100, 301, 10))                  # ...then the disarm path is fed exactly as before, and the window does not reopen


def test_fault_just_after_the_window_disarms_documented_limit():
  # temporary fault 110 ms after the denial: the denial was already treated as real at 100 ms (latch cleared); the shield rising later does not undo that
  card = Card()
  held = timeline(card, [(0, dict(denied=True)), (110, dict(fault=True))], 0, 100)
  assert held[90] and not held[100]


def test_fault_inside_the_window_is_a_pause_and_lateral_resumes_without_a_button():
  card = Card()
  held = timeline(card, [(0, dict(denied=True)), (14, dict(fault=True)), (100, dict(denied=False)),
                         (200, dict(fault=False)),                         # EPS fault clears, press goes on
                         (300, dict(pressed=False))], 0, 500)
  assert all(held[t] for t in range(0, 300, 10))                           # held through the whole fault and the rest of the press: no disarm was ever fed
  assert not held[300] and not held[400]                                    # driver lets go: nothing held, nothing to disarm, the latch is intact for lateral to resume


def test_a_new_denial_opens_a_new_window_after_the_old_one_closed():
  card = Card()
  held = timeline(card, [(0, dict(denied=True)), (150, dict(denied=False)), (200, dict(denied=True))], 0, 400)
  assert not held[120] and not held[140] and not held[150]
  assert held[200] and held[290] and not held[300]


@pytest.mark.parametrize("bad", [{'steerFaultPermanent': True}, {'canValid': False}, {'canTimeout': True}, {'accFaulted': True}])
def test_real_faults_never_get_the_grace(bad):
  card = Card()
  assert not card.cycle(0, denied=True, **bad)
  assert not card.cycle(10, denied=True, **bad)


def test_needs_the_latch_a_honda_and_a_denial(qualified=None):
  assert not Card(latched=False).cycle(0, denied=True)
  assert not honda_denial_grace(NS(), NS(brand="toyota"), cs(), native_denied=True, latched=True, now_ns=0)
  assert not honda_denial_grace(NS(), HONDA, cs(), native_denied=False, latched=True, now_ns=0)


def test_not_qualified_honda_never_gets_the_grace():
  with patch("opendbc.car.honda.stock_aol.qualified", return_value=False):
    assert not honda_denial_grace(NS(), HONDA, cs(), native_denied=True, latched=True, now_ns=0)
