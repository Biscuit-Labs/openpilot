"""Metadata-only tests of actual selection functions; no runtime admission proof."""
import ast
from dataclasses import dataclass, FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import re
import types
import unittest
from typing import Any
from unittest.mock import Mock, patch

SOURCE = Path(os.environ.get("STARPILOT_PARTIAL_NATIVE_SOURCE_ROOT", Path(__file__).resolve().parents[4]))
MODELS = SOURCE / "openpilot/starpilot/models"


def extract(path, names, namespace):
  tree = ast.parse(path.read_text(), filename=str(path))
  selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
  if {node.name for node in selected} != set(names):
    raise AssertionError("Missing actual source definitions")
  # Compile the original nodes unchanged, including decorators and annotations.
  body: list[ast.stmt] = [*selected]
  exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)


def subjects():
  ns = {"__name__": __name__, "dataclass": dataclass, "hashlib": hashlib, "json": json, "Path": Path, "re": re}
  # This entire module has only standard-library imports; no production imports.
  exec(compile((MODELS / "runtime_selection.py").read_text(), str(MODELS / "runtime_selection.py"), "exec"), ns)
  ns.update(ROOT=Path("/metadata-fixture"), DEFAULT_SMALL="rdf43", BUNDLED_CURRENT="bundled-current",
            GENERATION="v26", COMPILER_REVISION=ns["LEGACY_REVISION"], ARTIFACT_ABI=ns["LEGACY_ABI"],
            MODEL_ID=re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z"), SHA=re.compile(r"[0-9a-f]{64}\Z"),
            SUPPORTED_VERSIONS={f"v{i}" for i in range(8, 17)}, MAX_ARTIFACT=2 * 1024**3,
            MODEL_RUNNER_REVISION=2, BY_ID={},
            RUNTIME_ARTIFACT_KEYS={"min_runner_revision", "artifact_format", "artifact_sha256", "artifact_size",
                                   "artifact_chunk_count", "conversion_provenance", "validation"},
            CATALOG_PATH=Path("/metadata-fixture/legacy.json"), NATIVE_CATALOG_PATH=Path("/metadata-fixture/native.json"))
  extract(MODELS / "manager.py", ["ModelError", "validate_manifest", "native_stock", "catalog", "RuntimeSelection",
                                  "requested_runtime_id", "resolve_runtime"], ns)
  ns["ModelEntry"] = types.SimpleNamespace
  extract(MODELS / "catalog.py", ["resolve_selection"], ns)
  return ns


class TestPartialNativeSelection(unittest.TestCase):
  def setUp(self):
    self.n = subjects()
    self.prefs = {"small": "optional-small", "big": "traintrack", "userFavorites": ["optional-small"],
                  "blacklistedModels": ["another-small"], "randomizer": False, "sortMode": "favorites"}
    self.entries = {
      "optional-small": {"id": "optional-small", "version": "v15", "_runtime_family": "legacy9d", "artifact_sha256": "a" * 64},
      "traintrack": {"id": "traintrack", "version": "v16", "_runtime_family": "native02e", "artifact_sha256": "b" * 64},
    }
    self.default = {"runtime_family": "native02e", "version": "v15", "artifact_sha256": "c" * 64}

  def plan(self, **kw):
    return self.n["freeze_plan"](self.prefs, self.entries, self.default, **kw)

  def resolve(self, plan, available=True, installed=True, fallback=True):
    self.n["verified_artifact"] = Mock(side_effect=lambda mid, *_: Path("/verified") / mid if installed else None)
    self.n["shipped_default"] = Mock(return_value=Path("/verified/rdf43") if fallback else None)
    return self.n["resolve_runtime"](available, plan=plan)

  def document(self, native=True):
    return {"generation": self.n["NATIVE_GENERATION"] if native else "v26",
            "compiler_revision": self.n["NATIVE_REVISION"] if native else self.n["LEGACY_REVISION"],
            "artifact_abi": self.n["NATIVE_ABI"] if native else self.n["LEGACY_ABI"],
            "models": [{"id": "traintrack", "name": "TrainTrack", "version": "v16", "uses_external_gpu": True,
                        "artifact_sha256": "b" * 64, "artifact_size": 123, "artifact_chunk_count": 0,
                        "artifact_format": self.n["NATIVE_ABI"] if native else self.n["LEGACY_ABI"],
                        "qualification_sha256": "d" * 64}]}

  def test_native_big_uses_native_rdf_without_rewriting_saved_small(self):
    before = json.dumps(self.prefs, sort_keys=True)
    plan = self.plan()
    self.assertEqual((plan.family, plan.small_id, plan.big_id), ("native02e", "rdf43", "traintrack"))
    selected = self.resolve(plan)
    self.assertTrue(selected.allow_big)
    self.assertEqual((selected.small_path, selected.big_path, selected.fallback_path),
                     (Path("/verified/rdf43"), Path("/verified/traintrack"), Path("/verified/rdf43")))
    self.assertEqual(json.dumps(self.prefs, sort_keys=True), before)
    self.assertEqual(json.loads(plan.preferences_json), self.prefs)

  def test_default_rdf_selects_native_without_a_big_request(self):
    self.prefs.update(small="rdf43", big="")
    plan = self.plan()
    self.assertEqual((plan.family, plan.small_id, plan.big_id), ("native02e", "rdf43", ""))
    selected = self.resolve(plan)
    self.assertEqual(selected.small_sha256, "c" * 64)
    self.assertFalse(selected.allow_big)

  def test_unconverted_big_keeps_legacy_payload_custom_small_and_saved_request(self):
    self.entries["traintrack"]["_runtime_family"] = "legacy9d"
    self.default["runtime_family"] = "legacy9d"
    plan = self.plan()
    self.assertEqual((plan.family, plan.small_id, plan.big_id), ("legacy9d", "optional-small", "traintrack"))
    selected = self.resolve(plan)
    self.assertTrue(selected.allow_big)
    self.assertEqual((selected.small_id, selected.big_id), ("optional-small", "traintrack"))
    self.assertEqual(self.n["requested_runtime_id"](True, plan=plan), "traintrack")
    self.assertEqual(self.prefs["big"], "traintrack")

  def test_optional_small_only_uses_legacy_and_legacy_fallback(self):
    self.prefs["big"] = ""
    self.default["runtime_family"] = "legacy9d"
    plan = self.plan()
    selected = self.resolve(plan)
    self.assertEqual((plan.family, plan.compiler_revision, plan.artifact_abi),
                     ("legacy9d", self.n["LEGACY_REVISION"], self.n["LEGACY_ABI"]))
    self.assertEqual(selected.small_id, "optional-small")
    self.assertEqual(selected.small_sha256, "a" * 64)
    self.assertFalse(selected.allow_big)
    missing = self.resolve(plan, installed=False)
    self.assertEqual((missing.small_id, missing.small_path), ("rdf43", Path("/verified/rdf43")))

  def test_absent_chestnut_or_artifact_retains_big_request_but_disables_execution(self):
    for available, installed in ((False, True), (True, False)):
      with self.subTest(available=available, installed=installed):
        selected = self.resolve(self.plan(), available, installed)
        self.assertEqual(selected.big_id, "traintrack")
        self.assertIsNone(selected.big_path)
        self.assertFalse(selected.allow_big)
        self.assertEqual(selected.small_id, "rdf43")

  def test_recovery_forces_native_rdf_and_preserves_preferences(self):
    before = json.dumps(self.prefs, sort_keys=True)
    plan = self.plan(recovery_small_only=True)
    self.assertEqual((plan.family, plan.small_id, plan.big_id), ("native02e", "rdf43", ""))
    self.assertFalse(self.resolve(plan).allow_big)
    self.assertEqual(json.dumps(self.prefs, sort_keys=True), before)

  def test_frozen_benchmark_snapshot_is_detached_and_does_not_write_preferences(self):
    before = json.dumps((self.prefs, self.entries, self.default), sort_keys=True)
    first = self.plan()
    self.assertEqual(first, self.plan())
    self.assertEqual(json.dumps((self.prefs, self.entries, self.default), sort_keys=True), before)
    self.assertEqual(first.snapshot_sha256, hashlib.sha256("\n".join(
      (first.preferences_json, first.entries_json, first.default_json)).encode()).hexdigest())
    self.prefs["small"] = "later-choice"
    self.entries["traintrack"]["version"] = "v15"
    self.assertEqual(self.n["requested_runtime_id"](True, plan=first), "traintrack")
    self.assertEqual(json.loads(first.entries_json)["traintrack"]["version"], "v16")
    self.assertNotEqual(first.snapshot_sha256, self.plan().snapshot_sha256)
    with self.assertRaises(FrozenInstanceError):
      first.small_id = "mutated"

  def test_wrong_fallback_and_missing_verified_default_fail_closed(self):
    self.default["runtime_family"] = "legacy9d"
    with self.assertRaisesRegex(ValueError, "wrong runtime fallback"):
      self.plan()
    self.default["runtime_family"] = "native02e"
    with self.assertRaisesRegex(self.n["ModelError"], "missing or corrupt"):
      self.resolve(self.plan(), fallback=False)

  def test_unknown_or_pending_selector_is_rejected_without_silent_default(self):
    rdf = types.SimpleNamespace(selectable=True)
    self.n["model_entries"] = lambda _: {"rdf43": rdf, "pending-big": types.SimpleNamespace(selectable=False)}
    for requested in ("unknown", "pending-big", 7):
      with self.subTest(requested=requested), self.assertRaisesRegex(ValueError, "unqualified"):
        self.n["resolve_selection"](requested)
    self.assertIs(self.n["resolve_selection"](None), rdf)
    self.assertIs(self.n["resolve_selection"]("bundled-current"), rdf)

  def test_artifact_revision_abi_and_format_are_exact(self):
    for plan in (self.plan(), None):
      artifact = {"compiler_revision": plan.compiler_revision if plan else self.n["LEGACY_REVISION"],
                  "artifact_abi": plan.artifact_abi if plan else self.n["LEGACY_ABI"], "format_version": 1}
      self.n["require_artifact_contract"](artifact, plan)
      for key, bad in (("compiler_revision", "0" * 40), ("compiler_revision", "corrupt"),
                       ("artifact_abi", "unknown"), ("format_version", 2)):
        with self.subTest(key=key, bad=bad), self.assertRaisesRegex(ValueError, "compiler/ABI mismatch"):
          self.n["require_artifact_contract"]({**artifact, key: bad}, plan)

  def test_native_manifest_requires_exact_revision_abi_and_qualification(self):
    good = self.document()
    row = self.n["validate_manifest"](good, native=True)["traintrack"]
    self.assertEqual((row["_runtime_family"], row["compiler_revision"]), ("native02e", self.n["NATIVE_REVISION"]))
    for key, bad in (("compiler_revision", self.n["LEGACY_REVISION"]), ("compiler_revision", "corrupt"),
                     ("artifact_abi", self.n["LEGACY_ABI"]), ("generation", "unknown")):
      with self.subTest(key=key), self.assertRaises(self.n["ModelError"]):
        self.n["validate_manifest"]({**good, key: bad}, native=True)
    for key, bad in (("qualification_sha256", "bad"), ("uses_external_gpu", False), ("artifact_format", "unknown")):
      doc = self.document()
      doc["models"][0][key] = bad
      with self.subTest(key=key), self.assertRaises(self.n["ModelError"]):
        self.n["validate_manifest"](doc, native=True)

  def test_catalog_preserves_unconverted_legacy_big_payload(self):
    doc = self.document(native=False)
    small = {**doc["models"][0], "id": "optional-small", "uses_external_gpu": False}
    doc["models"].append(small)
    self.n["read_json"] = Mock(side_effect=[doc, FileNotFoundError()])
    self.n["native_catalog"] = Mock(return_value={})
    rows = self.n["catalog"]()
    self.assertEqual(set(rows), {"traintrack", "optional-small"})
    self.assertEqual(rows["traintrack"]["_runtime_family"], "legacy9d")
    self.assertEqual(rows["traintrack"]["artifact_sha256"], "b" * 64)
    self.assertEqual(rows["optional-small"]["_runtime_family"], "legacy9d")
    self.assertEqual(rows["optional-small"]["artifact_sha256"], "b" * 64)

  def test_legacy_big_forces_legacy_even_with_saved_default_rdf(self):
    self.prefs["small"] = "rdf43"
    self.entries["traintrack"]["_runtime_family"] = "legacy9d"
    self.default["runtime_family"] = "legacy9d"
    plan = self.plan()
    selected = self.resolve(plan)
    self.assertEqual((plan.family, plan.small_id, plan.big_id), ("legacy9d", "rdf43", "traintrack"))
    self.assertTrue(selected.allow_big)
    self.assertEqual(selected.small_sha256, "c" * 64)

  def test_native_counterpart_switches_new_snapshot_only(self):
    self.entries["traintrack"]["_runtime_family"] = "legacy9d"
    self.default["runtime_family"] = "legacy9d"
    old = self.plan()
    self.entries["traintrack"]["_runtime_family"] = "native02e"
    self.default["runtime_family"] = "native02e"
    new = self.plan()
    self.assertEqual((old.family, new.family), ("legacy9d", "native02e"))
    self.assertEqual((old.small_id, new.small_id), ("optional-small", "rdf43"))
    self.assertTrue(self.resolve(old).allow_big)
    self.assertTrue(self.resolve(new).allow_big)
    self.assertEqual(self.prefs["small"], "optional-small")

  def test_native_overlay_replaces_only_converted_big_id(self):
    doc = self.document(native=False)
    doc["models"].append({**doc["models"][0], "id": "unconverted-big"})
    native = self.n["validate_manifest"](self.document(), native=True)
    self.n["read_json"] = Mock(side_effect=[doc, FileNotFoundError()])
    self.n["native_catalog"] = Mock(return_value=native)
    rows = self.n["catalog"]()
    self.assertEqual(set(rows), {"traintrack", "unconverted-big"})
    self.assertEqual(rows["traintrack"]["_runtime_family"], "native02e")
    self.assertEqual(rows["unconverted-big"]["_runtime_family"], "legacy9d")
    self.assertEqual(rows["unconverted-big"]["artifact_sha256"], "b" * 64)

  def test_legacy_big_missing_hardware_or_payload_uses_same_family_fallback(self):
    self.entries["traintrack"]["_runtime_family"] = "legacy9d"
    self.default["runtime_family"] = "legacy9d"
    plan = self.plan()
    for available, installed in ((False, True), (True, False)):
      selected = self.resolve(plan, available=available, installed=installed)
      self.assertFalse(selected.allow_big)
      self.assertEqual(selected.big_id, "traintrack")
      self.assertEqual(selected.fallback_sha256, "c" * 64)
      self.assertEqual(plan.family, "legacy9d")

  def test_bundled_big_sentinel_does_not_force_a_legacy_session(self):
    self.prefs.update(small="rdf43", big="bundled-current")
    plan = self.plan()
    self.assertEqual((plan.family, plan.small_id, plan.big_id), ("native02e", "rdf43", ""))

  def test_cross_family_big_frozen_row_is_rejected(self):
    plan = self.plan()
    entries = json.loads(plan.entries_json)
    entries["traintrack"]["_runtime_family"] = "legacy9d"
    with self.assertRaisesRegex(self.n["ModelError"], "Big artifact does not match"):
      self.resolve(replace(plan, entries_json=json.dumps(entries)))

  def test_native_monitoring_stock_is_separate_complete_release(self):
    doc = self.document()
    names = {"dmonitoring_model_tinygrad.pkl", "dm_warp_1928x1208_tinygrad.pkl", "dm_warp_1344x760_tinygrad.pkl"}
    doc["stock"] = {name: {"artifact_sha256": "e" * 64, "artifact_size": 23, "qualification_sha256": "f" * 64}
                    for name in names}
    self.n["read_json"] = lambda _: doc
    self.assertEqual(set(self.n["native_stock"]()), names)
    del doc["stock"]["dm_warp_1344x760_tinygrad.pkl"]
    with self.assertRaisesRegex(self.n["ModelError"], "not qualified"):
      self.n["native_stock"]()

  def test_monitoring_prepare_never_freezes_driving_preferences(self):
    ns: dict[str, Any] = {"__name__": __name__, "_selection": None, "_plan": None}
    extract(MODELS / "runtime_bridge/runtime.py", ["prepare"], ns)
    hardware = types.ModuleType("openpilot.common.hardware")
    hardware.AGNOS = True
    bridge = types.ModuleType("openpilot.starpilot.models.runtime_bridge")
    bridge.native = types.SimpleNamespace(prepare=Mock(return_value={"role": "monitoring", "family": "native02e"}))
    with patch.dict("sys.modules", {"openpilot.common.hardware": hardware,
                                  "openpilot.starpilot.models.runtime_bridge": bridge}):
      selected = ns["prepare"]("monitoring")
    bridge.native.prepare.assert_called_once_with("monitoring", None)
    self.assertEqual(selected, {"role": "monitoring", "family": "native02e"})
    self.assertIsNone(ns["_plan"])

  def test_cross_family_small_and_postfreeze_randomization_rejected(self):
    self.prefs["big"] = ""
    self.default["runtime_family"] = "legacy9d"
    plan = self.plan()
    bad_entries = json.loads(plan.entries_json)
    bad_entries["optional-small"]["_runtime_family"] = "native02e"
    with self.assertRaisesRegex(self.n["ModelError"], "does not match"):
      self.resolve(replace(plan, entries_json=json.dumps(bad_entries)))
    with self.assertRaisesRegex(self.n["ModelError"], "Randomize before freezing"):
      self.n["resolve_runtime"](True, plan=plan, randomize=True)


if __name__ == "__main__":
  unittest.main()
