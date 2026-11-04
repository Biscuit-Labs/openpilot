import hashlib
import json

import pytest

from openpilot.common.file_chunker import package_file
from openpilot.starpilot.models import manager
from openpilot.starpilot.models.catalog import BUNDLED_CURRENT, DEFAULT_SMALL
from openpilot.starpilot.models.runtime_selection import freeze_plan, selection_family
from openpilot.starpilot.models.tests.native_fixture import native_fixture


@pytest.fixture(autouse=True)
def release_metadata(tmp_path, monkeypatch):
  data = b"verified fixture"
  monkeypatch.setattr(manager, "SHIPPED_MODELS", tmp_path / "shipped")
  monkeypatch.setattr(manager, "DEFAULT_SMALL_SHA256", hashlib.sha256(data).hexdigest())
  monkeypatch.setattr(manager, "DEFAULT_SMALL_SIZE", len(data))
  with native_fixture(tmp_path, data):
    yield


def frozen_plan(root):
  prefs, entries = manager.preferences(root), manager.catalog(root)
  family = selection_family(prefs, entries)
  return freeze_plan(prefs, entries, manager.default_record(family, root))


def test_unset_small_loads_shipped_rdf_v4_with_v15_parser(tmp_path, monkeypatch):
  artifact = tmp_path / "shipped.pkl"
  artifact.write_bytes(b"verified fixture")
  monkeypatch.setattr(manager, "shipped_default", lambda plan=None: artifact)
  selected = manager.resolve_runtime(False, root=tmp_path, plan=frozen_plan(tmp_path))
  assert manager.preferences(tmp_path)["small"] == DEFAULT_SMALL
  assert selected.small_id == "rdf43"
  assert selected.small_version == "v15"
  assert selected.small_path == artifact
  assert selected.small_sha256 == manager.default_record("native02e", tmp_path)["artifact_sha256"]
  assert not selected.allow_big


@pytest.mark.parametrize("selection", [BUNDLED_CURRENT, "gwm8223"])
def test_legacy_alias_and_missing_selected_artifact_use_rdf_only(tmp_path, monkeypatch, selection):
  manager.atomic_json(tmp_path / "preferences.json", {"small": selection})
  path = tmp_path / "rdf.pkl"
  monkeypatch.setattr(manager, "shipped_default", lambda plan=None: path)
  selected = manager.resolve_runtime(False, root=tmp_path, plan=frozen_plan(tmp_path))
  assert selected.small_id == DEFAULT_SMALL and selected.small_path == path
  assert manager.preferences(tmp_path)["small"] == (DEFAULT_SMALL if selection == BUNDLED_CURRENT else selection)


def test_missing_or_corrupt_only_shipped_model_refuses_startup(tmp_path, monkeypatch):
  monkeypatch.setattr(manager, "shipped_default", lambda plan=None: None)
  with pytest.raises(manager.ModelError, match="Shipped RDFv4 is missing or corrupt"):
    manager.resolve_runtime(False, root=tmp_path, plan=frozen_plan(tmp_path))


def test_big_default_disabled_and_explicit_download_preserved(tmp_path):
  assert manager.preferences(tmp_path)["big"] == ""
  manager.atomic_json(tmp_path / "preferences.json", {"big": "cinquev3"})
  assert manager.preferences(tmp_path)["big"] == "cinquev3"
  manager.atomic_json(tmp_path / "preferences.json", {"big": BUNDLED_CURRENT})
  assert manager.preferences(tmp_path)["big"] == ""


def test_verified_download_precedes_shipped_default(tmp_path, monkeypatch):
  path = tmp_path / "download.pkl"
  monkeypatch.setattr(manager, "catalog", lambda _: {DEFAULT_SMALL: {"artifact_sha256": "download-hash", "version": "v15",
                                                                  "_runtime_family": "native02e"}})
  monkeypatch.setattr(manager, "verified_artifact", lambda *args: path)
  fallback = tmp_path / "fallback.pkl"
  def verified_fallback(plan):
    assert plan is not None
    return fallback
  monkeypatch.setattr(manager, "shipped_default", verified_fallback)
  selected = manager.resolve_runtime(False, root=tmp_path, plan=frozen_plan(tmp_path))
  assert selected.small_path == path
  assert selected.small_sha256 == "download-hash"
  assert selected.fallback_path == fallback
  assert selected.small_path != selected.fallback_path


@pytest.mark.parametrize("family", ["native02e", "legacy9d"])
@pytest.mark.parametrize("damage", [None, "bytes", "size", "missing"])
def test_shipped_parts_require_pinned_hash_and_size(tmp_path, monkeypatch, damage, family):
  data = b"small isolated compiled artifact fixture"
  source = tmp_path / "source.pkl"
  source.write_bytes(data)
  destination = tmp_path / ("compat9d/rdf43_driving_tinygrad.pkl" if family == "legacy9d" else "rdf43_driving_tinygrad.pkl")
  package_file(source, destination)
  monkeypatch.setattr(manager, "SHIPPED_MODELS", tmp_path)
  monkeypatch.setattr(manager, "DEFAULT_SMALL_SHA256", hashlib.sha256(data).hexdigest())
  monkeypatch.setattr(manager, "DEFAULT_SMALL_SIZE", len(data) + (damage == "size"))
  with native_fixture(tmp_path, data) as document:
    if damage == "size":
      document["models"][0]["artifact_size"] += 1
      manager.NATIVE_CATALOG_PATH.write_text(json.dumps(document))
    record = manager.default_record(family, tmp_path)
  plan = freeze_plan({"small": "rdf43" if family == "native02e" else "gwm8223", "big": ""},
                     {"gwm8223": {"_runtime_family": "legacy9d"}}, record)
  part = destination.with_name(destination.name + ".chunk01of01")
  if damage == "bytes":
    part.write_bytes(b"x" * len(data))
  elif damage == "missing":
    part.unlink()
  result = manager.shipped_default(plan)
  assert (result is not None) == (damage is None)
  if result is not None:
    assert result.read_bytes() == data


def test_shipped_default_is_verified_asynchronously_in_menu(tmp_path, monkeypatch):
  data = b"isolated shipped fixture"
  source = tmp_path / "source.pkl"
  source.write_bytes(data)
  shipped = tmp_path / "shipped"
  package_file(source, shipped / "rdf43_driving_tinygrad.pkl")
  monkeypatch.setattr(manager, "SHIPPED_MODELS", shipped)
  monkeypatch.setattr(manager, "DEFAULT_SMALL_SHA256", hashlib.sha256(data).hexdigest())
  monkeypatch.setattr(manager, "DEFAULT_SMALL_SIZE", len(data))
  with native_fixture(tmp_path, data):
    owner = manager.ModelManager(root=tmp_path / "preferences", parked=lambda: True, gpu_present=lambda: False)
    try:
      owner.snapshot()
      if owner.verify_worker is not None:
        owner.verify_worker.join(2)
      row = next(row for row in owner.snapshot()["models"] if row["value"] == DEFAULT_SMALL)
      assert row["installed"] and row["selectable"] and not row["checking"]
      owner.action("active", {"profile": "small", "model": DEFAULT_SMALL})
      selected = manager.resolve_runtime(False, root=owner.root, plan=frozen_plan(owner.root))
      assert selected.small_id == DEFAULT_SMALL and selected.small_path.read_bytes() == data
    finally:
      owner.close()
