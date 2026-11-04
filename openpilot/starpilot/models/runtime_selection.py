"""Freeze one driving runtime before importing either tinygrad family."""
from dataclasses import dataclass
import hashlib
import json

NATIVE_REVISION = "02e698160eed1751738212144a7ea2cfb160b3f1"
LEGACY_REVISION = "9d0446a4ba8a532c8b674fb6ad795af015cd9dcf"
NATIVE_ABI = "tinygrad_single_v2_arena"
LEGACY_ABI = "tinygrad_single_v1_arena"
NATIVE_GENERATION = "native02e-v1"


@dataclass(frozen=True)
class RuntimePlan:
  family: str
  compiler_revision: str
  artifact_abi: str
  small_id: str
  big_id: str
  preferences_json: str
  entries_json: str
  default_json: str
  snapshot_sha256: str


def selection_family(preferences: dict, entries: dict, *, recovery_small_only: bool = False) -> str:
  # Entries come from validated catalogs: native rows include qualification identity.
  if recovery_small_only:
    return "native02e"
  small, big = preferences["small"], preferences["big"]
  if big and big != "bundled-current":
    return "native02e" if entries.get(big, {}).get("_runtime_family") == "native02e" else "legacy9d"
  return "native02e" if small == "rdf43" or small not in entries else "legacy9d"


def freeze_plan(preferences: dict, entries: dict, default: dict, *, recovery_small_only: bool = False) -> RuntimePlan:
  # Keep unconverted BIG and its fallback on legacy9d in the SAME process.
  small, big = preferences["small"], preferences["big"]
  family = selection_family(preferences, entries, recovery_small_only=recovery_small_only)
  native = family == "native02e"
  if default["runtime_family"] != family:
    raise ValueError("wrong runtime fallback for frozen selection")
  selected_big = big if not recovery_small_only and entries.get(big, {}).get("_runtime_family") == family else ""
  parts = [json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) for value in (preferences, entries, default)]
  return RuntimePlan(family=family, compiler_revision=NATIVE_REVISION if native else LEGACY_REVISION,
                     artifact_abi=NATIVE_ABI if native else LEGACY_ABI, small_id="rdf43" if native else small,
                     big_id=selected_big, preferences_json=parts[0], entries_json=parts[1], default_json=parts[2],
                     snapshot_sha256=hashlib.sha256("\n".join(parts).encode()).hexdigest())


def require_artifact_contract(artifact: dict, plan: RuntimePlan | None) -> None:
  revision, abi = (plan.compiler_revision, plan.artifact_abi) if plan is not None else (LEGACY_REVISION, LEGACY_ABI)
  if (not isinstance(artifact, dict) or artifact.get("compiler_revision") != revision or
      artifact.get("artifact_abi") != abi or artifact.get("format_version") != 1):
    raise ValueError("catalog model compiler/ABI mismatch")
