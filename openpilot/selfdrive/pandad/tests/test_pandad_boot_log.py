from unittest import mock

import pytest

from openpilot.selfdrive.pandad import pandad


class _Reset(BaseException):
  pass


class _FakePanda:
  def __init__(self, serial, internal=True):
    self.internal = internal

  def __enter__(self):
    return self

  def __exit__(self, *args):
    return False

  def is_internal(self):
    return self.internal

  def health(self):
    return {"uptime": 21600, "voltage": 12600, "ignition_line": True, "power_save_enabled": True, "heartbeat_lost": False}


def test_internal_panda_uptime_is_logged_before_the_reset():
  events = []
  panda_cls = mock.Mock(side_effect=_FakePanda)
  panda_cls.list.return_value = ["internal"]
  with (
    mock.patch.object(pandad, "wait_for_internal_panda", return_value=True),
    mock.patch.object(pandad, "Panda", panda_cls),
    mock.patch.object(pandad.cloudlog, "event", side_effect=lambda name, **kw: events.append((name, kw))),
    mock.patch.object(pandad.HARDWARE, "reset_internal_panda", side_effect=_Reset),
    mock.patch.object(pandad.signal, "signal"),
  ):
    with pytest.raises(_Reset):
      pandad.main()

  names = [name for name, _ in events]
  assert names.index("pandad.internal_panda_before_reset") < names.index("pandad.flash_and_connect")
  logged = dict(events)["pandad.internal_panda_before_reset"]
  assert logged["panda_uptime"] == 21600
  assert logged["voltage"] == 12600
  assert logged["boot_time"] > 0
