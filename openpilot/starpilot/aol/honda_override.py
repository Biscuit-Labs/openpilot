"""Night Star port: a hard driver override on Honda stock AOL keeps the latch through the EPS temporary fault (card)."""

def _qualified_override(cp, cs) -> bool:
  if cp.brand != 'honda' or not cs.steeringPressed:
    return False
  from opendbc.car.honda.stock_aol import qualified as honda_stock_qualified
  return bool(honda_stock_qualified(cp, marked_only=True))


def honda_override_shield(owner, cp, cs, latched) -> bool:
  """card: True while a qualified Honda override that raised the temporary EPS fault with AOL latched goes on. The
  transport tracker and the native-withdrawal check each see that fault in their own way, and either one clearing the
  latch left lateral waiting for an LKAS press after the takeover (Clarity 00000067--95d8a118bd seg 19 1152.3 s: one
  fault frame, 50 ms clear, second rise). While the shield is up card feeds neither into the latch; it drops when the
  driver lets go. Native rejection, disabling events, a permanent fault, CAN invalid or timeout, an ACC fault and the
  driver's own buttons still clear the latch, and the panda still refuses torque during the fault."""
  if not _qualified_override(cp, cs) or cs.steerFaultPermanent or not cs.canValid or cs.canTimeout or cs.accFaulted:
    owner.honda_override_shielded = False
  elif cs.steerFaultTemporary and latched:
    owner.honda_override_shielded = True
  return bool(getattr(owner, 'honda_override_shielded', False))


# Arrival-order grace. The stock EPS raises STEER_STATUS 2 on a hard takeover; panda sees that frame and drops lateralAllowed (requested 1 / allowed 0) and card sees the
# same frame as carState.steerFaultTemporary, but the two reach card in either order (rlog, Clarity 00000135: +-20 ms apart). The shield above rises only once
# steerFaultTemporary is seen, so a denial that arrives first was treated as a real one and cleared the latch (301.6 s, aol.latchClear disarming_fault; lateral waited for an
# LKAS press). While a latched Honda sees a denial and no temporary fault yet, the denial-driven disarm is deferred for HONDA_DENIAL_GRACE_NS; if the fault arrives inside
# the window the shield takes over (a pause: the latch stays and lateral resumes by itself when the fault clears), otherwise the disarm happens exactly as before, at most the
# window late. 100 ms = 5x the measured skew, half of native_observation's own 200 ms pending timeout. The window never opens on a permanent fault, CAN loss, an ACC
# fault, or while a cancel / brake source is pending (card passes those through unchanged). It feeds card's transport tracker and lost-grant check only; the native-rejection path (immediate by contract, test_stock_aol) is untouched.
HONDA_DENIAL_GRACE_NS = 100_000_000


def honda_denial_grace(owner, cp, cs, *, native_denied, latched, now_ns) -> bool:
  from opendbc.car.honda.stock_aol import qualified as honda_stock_qualified
  if (cp.brand != 'honda' or not latched or not native_denied or cs.steerFaultTemporary or cs.steerFaultPermanent or
      not cs.canValid or cs.canTimeout or cs.accFaulted or not honda_stock_qualified(cp, marked_only=True)):
    owner.honda_denial_since_ns = None
    return False
  since = getattr(owner, 'honda_denial_since_ns', None)
  if since is None:
    since = owner.honda_denial_since_ns = now_ns
  return now_ns - since < HONDA_DENIAL_GRACE_NS
