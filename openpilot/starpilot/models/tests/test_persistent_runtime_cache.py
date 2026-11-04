"""Persistent startup cache selection; not GPU or road qualification."""
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import pytest

from openpilot.starpilot.models import manager
from openpilot.starpilot.models.runtime_bridge import native, runtime


@pytest.mark.parametrize("family", ["legacy9d", "native02e"])
@pytest.mark.parametrize("role", ["driving", "monitoring"])
def test_inference_cache_survives_reboot_without_changing_role_isolation(role, family):
  selected = {"role": role}
  plan = SimpleNamespace(family=family)
  with (patch("openpilot.common.hardware.AGNOS", True),
        patch.object(runtime, "_selection", None),
        patch.object(runtime, "_plan", None),
        patch.object(manager, "freeze_runtime", return_value=plan) as freeze,
        patch.object(native, "prepare", return_value=selected) as native_prepare,
        patch.object(runtime, "_verify_policy") as verify,
        patch.object(runtime, "activate", return_value=selected) as activate):
    assert runtime.prepare(role) is selected
    if role == "driving":
      freeze.assert_called_once_with(recovery_small_only=False)
    else:
      freeze.assert_not_called()
    if role == "driving" and family == "legacy9d":
      verify.assert_called_once()
      activate.assert_called_once_with(runtime.BUNDLE, runtime.MANIFEST_SHA256,
                                       runtime.LEGACY_REVISION, role, Path("/data/starpilot-model-runtime"))
      native_prepare.assert_not_called()
    else:
      native_prepare.assert_called_once_with(role, plan if role == "driving" else None)
      verify.assert_not_called()
      activate.assert_not_called()
    assert runtime.prepare(role) is selected
    assert (activate.call_count if role == "driving" and family == "legacy9d" else native_prepare.call_count) == 1
    with pytest.raises(RuntimeError, match="cannot change its execution role"):
      runtime.prepare("monitoring" if role == "driving" else "driving")


def test_host_does_not_create_device_cache():
  with (patch("openpilot.common.hardware.AGNOS", False),
        patch.object(runtime, "_selection", None),
        patch.object(runtime, "activate", side_effect=AssertionError("must not touch device cache"))):
    assert runtime.prepare("driving") is None
