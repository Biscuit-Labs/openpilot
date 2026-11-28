import os
import tempfile
from types import SimpleNamespace

from opendbc.car.honda.eps_fault_text import FaultTextPublisher, MAX_AGE_S, describe, read_fault_text


def status(fault="", build=0x11, enabled=True):
  return SimpleNamespace(fault=fault, build_id=build, enabled=enabled)


def test_describe_names_every_interlock_fault():
  assert describe("", 0x11) == ""
  assert "0x11" in describe("unknown_build", 0x11) and "not supported" in describe("unknown_build", 0x11)
  assert "not supported" in describe("unsupported_build", 0x04)
  assert "not reporting" in describe("no_status", 0)
  assert "lost" in describe("lost", 0x11)
  assert "angle mode" in describe("inactive_mode", 0x11).lower()
  assert "authority_zero" in describe("loop_not_running (AUTHORITY_ZERO)", 0x11)
  assert "target_held" in describe("angle_fault (TARGET_HELD)", 0x11)
  assert describe("something_new", 1).startswith("EPS interlock")


def test_publish_read_clear_and_staleness():
  with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "fault")
    t = [100.0]
    pub = FaultTextPublisher(path, clock=lambda: t[0])
    assert read_fault_text(path) == ""                       # nothing yet: generic alert
    pub.update(status("unknown_build"))
    now = os.stat(path).st_mtime
    assert "not supported" in read_fault_text(path, now)
    assert read_fault_text(path, now + MAX_AGE_S + 1) == ""  # dead card: stale, generic alert
    pub.update(status(""))                                   # fault cleared
    assert read_fault_text(path, os.stat(path).st_mtime) == ""
    pub.update(status("unknown_build", enabled=False))       # interlock off: never publishes a fault
    assert read_fault_text(path, os.stat(path).st_mtime) == ""


def test_refresh_while_faulted_and_no_write_when_idle():
  with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "fault")
    t = [0.0]
    pub = FaultTextPublisher(path, clock=lambda: t[0])
    pub.update(status(""))
    assert not os.path.exists(path)                          # a healthy car writes nothing
    pub.update(status("lost"))
    m0 = os.stat(path).st_mtime_ns
    t[0] = 0.1
    pub.update(status("lost"))
    assert os.stat(path).st_mtime_ns == m0                   # no churn inside the refresh window
    t[0] = 1.0
    pub.update(status("lost"))
    assert os.stat(path).st_mtime_ns >= m0                   # refreshed so selfdrived keeps seeing it


def test_unwritable_path_is_silent():
  pub = FaultTextPublisher("/nonexistent-dir/fault")
  pub.update(status("unknown_build"))                        # must not raise
