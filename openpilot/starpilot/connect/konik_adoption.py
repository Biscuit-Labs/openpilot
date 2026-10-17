"""Carry a vfn device's Konik identity into 7.0's cloud-provider state, once, before 7.0's first start.

vfn registered with Konik using the factory key in /persist/comma and kept the Konik dongle id in KonikDongleId (and
the comma one in StockDongleId), switching DongleId between them. 7.0 keeps each provider's identity apart and makes
Konik a NEW key, so without this a vfn device would register with Konik again as a different device and lose its
drive history. Konik already trusts the factory public key for that dongle id, so it is reused for Konik here.

Runs before state_migration archives vfn's keys (KonikDongleId, StockDongleId and UseKonikServer are not in 7.0's
registry), so it reads their files directly. It does nothing once 7.0 provider state exists.
"""
import base64
import re
from pathlib import Path

from openpilot.common.hardware.hw import Paths
from openpilot.starpilot.connect.provider import (DEFAULT_CONFIGURATION, DEFAULT_PROVIDER, STATE_KEYS, _exclusive,
                                                  _read, _write, root_path)

DONGLE = re.compile(r'[a-f0-9]{16}')


def _saved_dongle(params, key) -> str | None:
  try:
    value = Path(params.get_param_path(key)).read_bytes().decode().strip()
  except (OSError, UnicodeError):
    return None
  return value if DONGLE.fullmatch(value) else None


def _factory(persist: Path, name: str) -> str | None:
  try:
    return (persist / 'comma' / name).read_text()
  except (OSError, UnicodeError):
    return None


def adopt_vfn_konik_identity(params, *, root=None, persist=None) -> str:
  """Returns what it did, for the log: 'existing' (7.0 state already there), 'adopted' or 'fresh'."""
  root = root or root_path()
  persist = Path(persist or Paths.persist_root())
  if (root / 'provider.json').exists() or (root / 'switch.json').exists():
    return 'existing'

  konik = _saved_dongle(params, 'KonikDongleId')
  current = _saved_dongle(params, 'DongleId')
  comma = _saved_dongle(params, 'StockDongleId') or (_factory(persist, 'dongle_id') or '').strip() or None
  if comma is not None and not DONGLE.fullmatch(comma):
    comma = None
  if comma is None and current is not None and current != konik:
    comma = current
  private, public = _factory(persist, 'id_rsa'), _factory(persist, 'id_rsa.pub')
  adopt = konik is not None and private is not None and public is not None

  with _exclusive(root):
    # comma's identity, kept for the Galaxy device id (galaxy_device_id reads it from here while Konik is active)
    comma_state = dict.fromkeys(STATE_KEYS)
    if comma is not None:
      comma_state['DongleId'] = base64.b64encode(comma.encode()).decode()
    _write(root / 'comma' / 'params.json', comma_state)
    if adopt and _read(root / 'konik' / 'identity.json') is None:
      _write(root / 'konik' / 'identity.json', {'private': private, 'public': public})
    _write(root / 'provider.json', dict(DEFAULT_CONFIGURATION))

  # DongleId now belongs to Konik: the adopted id, or none so that registration makes one (a comma id, or a Konik id
  # we cannot sign for, must not be sent to Konik)
  if adopt:
    params.put('DongleId', konik, block=True)
  else:
    params.remove('DongleId')
  for key in ('PrimeType', 'PairingProvider', 'PairingEmail', 'AccessToken'):   # comma account state
    params.remove(key)
  params.put('ConnectProvider', DEFAULT_PROVIDER, block=True)
  return 'adopted' if adopt else 'fresh'
