import os
from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.selfdrive.selfdrived import events as ev
from opendbc.car.honda.eps_fault_text import FaultTextPublisher, read_fault_text

EventName = log.OnroadEvent.EventName
GENERIC = ("Steering Assist Temporarily Unavailable", "Steering Temporarily Unavailable")


def texts(alert):
  return {alert.alert_text_1, alert.alert_text_2}


def build(kind, soft_disable_time=300):
  return ev.EVENTS[EventName.steerTempUnavailable][kind](None, None, None, False, soft_disable_time, None)


def test_generic_text_without_a_published_fault(monkeypatch, tmp_path):
  path = str(tmp_path / "fault")
  monkeypatch.setattr(ev, "_eps_fault_text", lambda: read_fault_text(path))
  assert GENERIC[0] in texts(build(ev.ET.SOFT_DISABLE)) and GENERIC[1] in texts(build(ev.ET.NO_ENTRY))


def test_named_fault_reaches_both_alerts(monkeypatch, tmp_path):
  path = str(tmp_path / "fault")
  monkeypatch.setattr(ev, "_eps_fault_text", lambda: read_fault_text(path))
  pub = FaultTextPublisher(path)
  pub.update(SimpleNamespace(fault="unknown_build", build_id=0x0B, enabled=True))
  for kind in (ev.ET.SOFT_DISABLE, ev.ET.NO_ENTRY):
    t = texts(build(kind))
    assert any("not protocol v3" in x for x in t), t
    assert not (set(GENERIC) & t)


def test_cleared_fault_and_stale_file_go_back_to_generic(monkeypatch, tmp_path):
  path = str(tmp_path / "fault")
  monkeypatch.setattr(ev, "_eps_fault_text", lambda: read_fault_text(path))
  pub = FaultTextPublisher(path)
  pub.update(SimpleNamespace(fault="lost", build_id=0x11, enabled=True))
  assert any("status lost" in x for x in texts(build(ev.ET.NO_ENTRY)))
  pub.update(SimpleNamespace(fault="", build_id=0x11, enabled=True))
  assert GENERIC[1] in texts(build(ev.ET.NO_ENTRY))
  pub.update(SimpleNamespace(fault="lost", build_id=0x11, enabled=True))
  old = os.stat(path).st_mtime - 10
  os.utime(path, (old, old))                                # a dead card: the file is older than MAX_AGE_S
  assert GENERIC[1] in texts(build(ev.ET.NO_ENTRY))


def test_soft_disable_keeps_its_two_stages(monkeypatch, tmp_path):
  path = str(tmp_path / "fault")
  monkeypatch.setattr(ev, "_eps_fault_text", lambda: read_fault_text(path))
  FaultTextPublisher(path).update(SimpleNamespace(fault="lost", build_id=0x11, enabled=True))
  assert isinstance(build(ev.ET.SOFT_DISABLE, 300), ev.SoftDisableAlert)
  assert isinstance(build(ev.ET.SOFT_DISABLE, 10), ev.ImmediateDisableAlert)
