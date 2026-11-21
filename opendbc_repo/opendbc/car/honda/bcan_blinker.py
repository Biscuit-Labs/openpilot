"""B-CAN turn signal (BCM) command state machine for Honda body harnesses.

The body BCM drives the real turn signal lamps from a 29-bit KWP command on
B-CAN, which a body-harness gateway forwards to comma bus 0:

  start left  = 30 0a DD 00 00 00 00 00
  start right = 30 0b DD 00 00 00 00 00
  cancel      = 20 00 00 00 00 00 00 00

DD is the blink duration in seconds; the BCM stops the lamp on its own when it
expires, so the start is renewed while the desired side persists. The BCM
answers 0x16F1F018: byte0 0x70 = start accepted, 0x60 = stop accepted,
0x7F = unsupported (lock out for the rest of the drive).

Pure logic: no CANPacker/opendbc.can imports, so it unit-tests without the
compiled CAN stack. The car controller calls update() once per control loop
(100 Hz, DT_CTRL) with the toggle state and the current car state.
"""
from opendbc.car.can_definitions import CanData
from opendbc.car.carlog import carlog

ADDR = 0x16F118F0
BUS = 0

BLINK_HOLD_BYTE = 0x03  # DD: seconds of blinking one start command grants
RENEW_S = 1.0           # resend the start while the desired side persists
MIN_FRAME_PERIOD_S = 0.1
SIDE_CHANGE_DELAY_S = 0.1  # the new side starts no sooner than this after a cancel
CANCEL_REPEAT_S = 0.2      # the cancel is repeated this apart
CANCEL_MAX = 3             # ... up to this many times unless a 0x60 reply arrives

RESP_STOP = 0x60
RESP_NEGATIVE = 0x7F

LEFT = "left"
RIGHT = "right"


def _start_dat(side: str) -> bytes:
  return bytes((0x30, 0x0A if side == LEFT else 0x0B, BLINK_HOLD_BYTE, 0, 0, 0, 0, 0))


CANCEL = bytes((0x20, 0, 0, 0, 0, 0, 0, 0))


def _elapsed(now, ts, period):
  # 1e-6 s tolerance: exact 0.1/0.2 s steps (0.3 - 0.1, 0.7 - 0.5) must not lose to float error
  return ts is None or now - ts >= period - 1e-6


class BcanBlinker:
  def __init__(self):
    self.side = None          # side of the active start command
    self.cancelling = False   # cancel sent, waiting for the stop to be accepted
    self.cancel_count = 0
    self.opposed = False      # driver stalk is against us; no restart until desired goes none
    self.locked = False       # 0x7F reply: no more frames for the rest of the drive
    self.last_frame_ts = None
    self.last_start_ts = None
    self.last_cancel_ts = None

  def update(self, CC, CS, enabled, now):
    """One 100 Hz step. CC/CS are duck-typed: CC.leftBlinker/rightBlinker/latActive,
    CS.hazard_on/left_stalk_raw/right_stalk_raw/bcm_kwp_resp. now is in seconds.
    Returns the frames to send (usually zero or one)."""
    frames = []
    if not enabled or self.locked:
      return frames

    resp = CS.bcm_kwp_resp
    if resp == RESP_NEGATIVE:
      self.locked = True
      carlog.warning("BcanBlinker: BCM reply 0x7F, B-CAN turn signals disabled for the rest of this drive")
      return frames
    if resp == RESP_STOP and self.cancelling:
      self.cancelling = False
      self.cancel_count = 0
      self.side = None

    if CC.leftBlinker and not CC.rightBlinker:
      desired = LEFT
    elif CC.rightBlinker and not CC.leftBlinker:
      desired = RIGHT
    else:
      desired = None
    if desired is None:
      self.opposed = False

    can_send = _elapsed(now, self.last_frame_ts, MIN_FRAME_PERIOD_S)

    def send(dat):
      nonlocal can_send
      frames.append(CanData(ADDR, dat, BUS))
      self.last_frame_ts = now
      can_send = False

    # driver stalk against our active side: cancel, and do not restart until the signal is back to none
    if self.side is not None and not self.cancelling and not CS.hazard_on:
      if (self.side == LEFT and CS.right_stalk_raw) or (self.side == RIGHT and CS.left_stalk_raw):
        self.opposed = True
        self.cancelling = True
        self.cancel_count = 0

    if self.cancelling:
      # repeat the cancel until the stop is accepted (0x60)
      if self.cancel_count < CANCEL_MAX:
        if can_send and _elapsed(now, self.last_cancel_ts, CANCEL_REPEAT_S):
          send(CANCEL)
          self.cancel_count += 1
          self.last_cancel_ts = now
      elif _elapsed(now, self.last_cancel_ts, CANCEL_REPEAT_S):
        # no 0x60 reply: give up, the lamp expires on its own within BLINK_HOLD_BYTE seconds
        self.cancelling = False
        self.side = None
      return frames

    if self.side is not None:
      # active: renew the start while the same side is desired; a hazard pauses renewals
      # and we do not send a cancel, the lamp expires on its own
      if desired == self.side and CC.latActive and not CS.hazard_on:
        if _elapsed(now, self.last_start_ts, RENEW_S):
          send(_start_dat(self.side))
          self.last_start_ts = now
      elif not CS.hazard_on and (desired != self.side or not CC.latActive):
        self.cancelling = True
        self.cancel_count = 0
      return frames

    # nothing active: start the desired side
    if desired is not None and CC.latActive and not CS.hazard_on and not self.opposed and can_send:
      if not _elapsed(now, self.last_cancel_ts, SIDE_CHANGE_DELAY_S):
        return frames  # side change: give the cancel a beat before starting the new side
      send(_start_dat(desired))
      self.side = desired
      self.last_start_ts = now
    return frames
