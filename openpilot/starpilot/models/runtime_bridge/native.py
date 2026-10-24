"""Integrity gate and native02e loader; no tinygrad imports before prepare."""
from contextlib import contextmanager
import atexit
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, cast

from openpilot.starpilot.models.runtime_selection import NATIVE_REVISION
from openpilot.starpilot.models.runtime_bridge.bootstrap import (
  IMPORT_FAMILIES, _check_source_package, _namespace, _private_cache,
)

if TYPE_CHECKING:
  from tinygrad.device import Buffer


class PersistentLoad(Protocol):
  persistent_load: Callable[[tuple[int, int]], "Buffer"]

# Deliberately unpublishable until native source/guard and model evidence is sealed.
POLICY_SHA256 = '37d7b056bc6f1bd1748cab5f20bbdc75986b5af6e4ea6b878d1e1e58545ddb88'
ROOT = Path(__file__).resolve().parents[4]
BRIDGE = Path(__file__).parent
_LIBRARIES = {
  'libbounded_wait.so': '24ed559861c8636c1026cad9a244854bb2236b5ee8b91bf21c5efbf688fa4a69',
  'libusb_guards.so': '66a3dfe48ac17899862ab80160cf6dac2c9b9707234527ba0d808f3b68404114',
}
_role = None
_allowed = {}
_protection = None


def _plain_file(path):
  for parent in (*reversed(path.parents), path):
    mode = parent.lstat().st_mode
    if stat.S_ISLNK(mode):
      raise ValueError('Symlink in native runtime input')
  if not path.is_file():
    raise ValueError('Missing native runtime input')


def _digest(path):
  _plain_file(path)
  with path.open('rb') as stream:
    return hashlib.file_digest(stream, 'sha256').hexdigest()


def _unique_object(pairs):
  result = {}
  for key, value in pairs:
    if key in result:
      raise ValueError('Duplicate native policy key')
    result[key] = value
  return result


def _vendor_mapping(value):
  if not isinstance(value, dict) or not value:
    raise ValueError('Empty native vendor mapping')
  for name, expected in value.items():
    if not isinstance(name, str) or not name or not isinstance(expected, str):
      raise ValueError('Invalid native vendor entry type')
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or str(relative) != name:
      raise ValueError('Invalid native vendor path')
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
      raise ValueError('Invalid native vendor digest')
  return value


def _vendor_files(policy):
  if 'vendor_files' in policy:
    if 'vendor_parts' in policy or 'vendor_file_count' in policy:
      raise ValueError('Mixed native vendor policy formats')
    return _vendor_mapping(policy['vendor_files'])
  parts, count = policy.get('vendor_parts'), policy.get('vendor_file_count')
  if not isinstance(parts, list) or not 1 <= len(parts) <= 99 or type(count) is not int or count <= 0:
    raise ValueError('Invalid native vendor shard inventory')
  merged = {}
  for index, part in enumerate(parts, 1):
    if not isinstance(part, dict) or set(part) != {'name', 'sha256', 'count'}:
      raise ValueError('Invalid native vendor shard descriptor')
    if part['name'] != f'native-vendor-{index:02d}.json' or type(part['count']) is not int or part['count'] <= 0:
      raise ValueError('Invalid native vendor shard name/count')
    expected = part['sha256']
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
      raise ValueError('Invalid native vendor shard digest')
    path = BRIDGE / part['name']
    _plain_file(path)
    if path.stat().st_size > 96 * 1024:
      raise ValueError('Oversized native vendor shard')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
      raise ValueError('Native vendor shard changed')
    entries = _vendor_mapping(json.loads(raw, object_pairs_hook=_unique_object))
    if len(entries) != part['count'] or merged.keys() & entries.keys():
      raise ValueError('Duplicate or miscounted native vendor shard entries')
    merged.update(entries)
  if len(merged) != count:
    raise ValueError('Native vendor inventory count changed')
  return merged


def _verify_policy():
  path = BRIDGE / 'native-policy.json'
  _plain_file(path)
  raw = path.read_bytes()
  if hashlib.sha256(raw).hexdigest() != POLICY_SHA256:
    raise RuntimeError('Native runtime policy is not qualified')
  policy = json.loads(raw)
  required = {'native_guards.py', 'bounded_wait.c', 'usb_guards.c', *_LIBRARIES}
  if (policy.get('compiler_revision') != NATIVE_REVISION or policy.get('native_abi') != 'linux-aarch64-64bit' or
      policy.get('host_runtime_dev') not in ('CPU:LLVM', 'CPU:CLANG') or
      not isinstance(policy.get('files'), dict) or set(policy['files']) != required):
    raise ValueError('Native runtime identity mismatch')
  for name, expected in policy['files'].items():
    if _digest(BRIDGE / name) != expected or name in _LIBRARIES and expected != _LIBRARIES[name]:
      raise ValueError('Native guard source/artifact changed')
  if _digest(BRIDGE.parent / 'catalog-native02e.json') != policy.get('catalog_sha256'):
    raise ValueError('Native stock release metadata changed')
  vendor = ROOT / 'tinygrad_repo'
  expected_files = _vendor_files(policy)
  actual = set()
  for directory, dirs, files in os.walk(vendor, followlinks=False):
    dirs[:] = [name for name in dirs if name not in ('__pycache__', '.git')]
    for name in dirs:
      if (Path(directory) / name).is_symlink():
        raise ValueError('Symlink in native runtime source')
    for name in files:
      if name.endswith(('.pyc', '.pyo')):
        raise ValueError('Standalone native vendor bytecode is not source-pinned')
      if name == 'AGENTS.md':
        continue
      actual.add((Path(directory) / name).relative_to(vendor).as_posix())
  if actual != set(expected_files):
    raise ValueError('Native vendor inventory changed')
  for name, expected in expected_files.items():
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or str(relative) != name:
      raise ValueError('Invalid native vendor path')
    if _digest(vendor / name) != expected:
      raise ValueError('Native vendor source changed')
  return policy


def _remove_empty_prefix(path):
  try:
    os.rmdir(path)
  except OSError:
    pass


def prepare(role, plan):
  """Run before any tinygrad import; root seals policy after actual qualification."""
  global _role, _allowed
  if role not in ('driving', 'monitoring') or role == 'driving' and (plan is None or plan.family != 'native02e'):
    raise ValueError('Invalid native runtime role/plan')
  if _role is not None:
    raise RuntimeError('Native runtime was already selected')
  if any(name == family or name.startswith(family + '.') for name in sys.modules for family in IMPORT_FAMILIES):
    raise RuntimeError('Select native runtime before importing tinygrad')
  policy = _verify_policy()
  from openpilot.starpilot.models.manager import SHIPPED_MODELS, native_stock
  stock = native_stock()
  if role == 'monitoring':
    allowed = {str(SHIPPED_MODELS / name): row for name, row in stock.items()}
  else:
    default = json.loads(plan.default_json)
    entries = json.loads(plan.entries_json)
    allowed = {default['path']: default}
    small = entries.get(plan.small_id)
    if small is not None and small.get('_runtime_family') == 'native02e':
      allowed[small['_artifact_path']] = small
    if plan.big_id:
      row = entries[plan.big_id]
      allowed[row['_artifact_path']] = row
  cache = Path('/data/starpilot-model-runtime') / NATIVE_REVISION / role / POLICY_SHA256
  _private_cache(cache)
  _private_cache(cache / 'xdg')
  bytecode_prefix = Path(tempfile.mkdtemp(prefix='python-', dir=cache))
  _private_cache(bytecode_prefix)
  if any(bytecode_prefix.iterdir()):
    raise RuntimeError('Native bytecode prefix is not empty')
  atexit.register(_remove_empty_prefix, bytecode_prefix)
  tg_root = ROOT / 'tinygrad_repo'
  sys.path[:0] = [str(ROOT), str(tg_root)]
  sys.dont_write_bytecode = True
  # A fresh private prefix isolates READS too; dont_write_bytecode alone does not.
  sys.pycache_prefix = str(bytecode_prefix)
  os.environ.pop('PYTHONPYCACHEPREFIX', None)
  os.environ['HCQ_RUNTIME_DEV'] = policy['host_runtime_dev']
  os.environ.update(CACHEDB=str(cache / 'tinygrad.db'), XDG_CACHE_HOME=str(cache / 'xdg'), PYTHONDONTWRITEBYTECODE='1')
  sys.modules['tinygrad_repo'] = _namespace('tinygrad_repo', tg_root)
  sys.modules['extra'] = _namespace('extra', tg_root / 'extra')
  importlib.invalidate_caches()
  _check_source_package('tinygrad', tg_root / 'tinygrad/__init__.py')
  _check_source_package('examples', tg_root / 'examples/__init__.py')
  _role, _allowed = role, allowed
  return {'role': role, 'family': 'native02e', 'compiler_revision': NATIVE_REVISION,
          'manifest_sha256': POLICY_SHA256, 'runtime_files': len(_vendor_files(policy)),
          'tinygrad_origin': str(tg_root / 'tinygrad/__init__.py'), 'cache': str(cache)}


def _guard():
  global _protection
  if _role is None:
    raise RuntimeError('Native runtime is not prepared')
  if _protection is None:
    _verify_policy()
    from openpilot.starpilot.models.runtime_bridge import native_guards
    _protection = native_guards.install(_role, BRIDGE / 'libbounded_wait.so', BRIDGE / 'libusb_guards.so')
  return _protection


@contextmanager
def _verified(path):
  path = Path(path)
  record = _allowed.get(str(path).removesuffix('.unchunked'))
  if record is None:
    raise ValueError('Artifact is outside the frozen native selection')
  fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
  with os.fdopen(fd, 'rb') as stream:
    before = os.fstat(stream.fileno())
    def identity(value):
      return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns
    if (not stat.S_ISREG(before.st_mode) or before.st_size != record['artifact_size'] or
        hashlib.file_digest(stream, 'sha256').hexdigest() != record['artifact_sha256']):
      raise ValueError('Native artifact identity mismatch')
    stream.seek(0)
    def unchanged():
      named = path.lstat()
      if (not stat.S_ISREG(named.st_mode) or identity(before) != identity(os.fstat(stream.fileno())) or
          identity(before) != identity(named)):
        raise ValueError('Native artifact changed while loading')
    unchanged()
    yield stream, unchanged
    unchanged()


def _load_driving(stream, unchanged):
  import io
  import mmap
  import pickle
  import struct
  from tinygrad import Device
  from tinygrad.device import Buffer, HCQ_RUNTIME_DEV
  length_raw = stream.read(8)
  if len(length_raw) != 8:
    raise ValueError('Missing native OOB envelope')
  length = struct.unpack('<q', length_raw)[0]
  if not 0 < length <= os.fstat(stream.fileno()).st_size - 8:
    raise ValueError('Invalid native OOB envelope')
  opcodes = stream.read(length)
  if stream.tell() == os.fstat(stream.fileno()).st_size:
    unchanged()
    return pickle.loads(opcodes)
  # Map the already authenticated inode. Do not reopen a path or use a cached
  # DISK:/proc/self/fd device whose descriptor number can be reused later.
  mapping = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_COPY)
  view = memoryview(mapping)[stream.tell():]
  buffers = Buffer(HCQ_RUNTIME_DEV.device, len(view), opaque=view)
  arena, chunk_size = Buffer(Device.DEFAULT, buffers.nbytes, preallocate=True), 8 << 20
  unchanged()
  for off in range(0, buffers.nbytes, chunk_size):
    size = min(chunk_size, buffers.nbytes - off)
    arena.view(size, off).ensure_allocated().copy_from(buffers.view(size, off).ensure_allocated())
  Device.default.synchronize()
  unchanged()
  del buffers
  view.release()
  mapping.close()
  unpickler = pickle.Unpickler(io.BytesIO(opcodes))
  cast("PersistentLoad", unpickler).persistent_load = lambda record: arena.view(*record)
  return unpickler.load()


def _load_monitoring(stream, unchanged):
  import io
  import pickle
  import struct
  from tinygrad import Device
  from tinygrad.device import Buffer
  data = stream.read()
  unchanged()
  if len(data) < 8:
    raise ValueError('Missing native monitoring envelope')
  length = struct.unpack('<q', data[:8])[0]
  if not 0 < length <= len(data) - 8:
    raise ValueError('Invalid native monitoring envelope')
  end = 8 + length
  if end == len(data):
    unchanged()
    return pickle.loads(data[8:end])
  arena = Buffer(Device.DEFAULT, len(data) - end, initial_value=data[end:])
  unchanged()
  unpickler = pickle.Unpickler(io.BytesIO(data[8:end]))
  cast("PersistentLoad", unpickler).persistent_load = lambda record: arena.view(*record)
  return unpickler.load()


def load_oob(path, chestnut=False):
  if _role is None or chestnut and _role != 'driving':
    raise ValueError('Invalid native artifact role')
  from tinygrad import Context, Device
  from tinygrad.runtime.ops_qcom import QCOMDevice
  protection = _guard()
  with _verified(path) as (stream, unchanged), Context(DEV='USB+AMD:LLVM' if chestnut else 'QCOM'):
    if not isinstance(Device['QCOM'], QCOMDevice):
      raise RuntimeError('Expected the native QCOM device')
    artifact = _load_monitoring(stream, unchanged) if _role == 'monitoring' else _load_driving(stream, unchanged)
    return protection.artifact(artifact, chestnut=chestnut)


def load_warp(path):
  if _role != 'monitoring':
    raise ValueError('Native warp loader requires monitoring role')
  import pickle
  from tinygrad import Context, Device
  from tinygrad.runtime.ops_qcom import QCOMDevice
  protection = _guard()
  with _verified(path) as (stream, unchanged), Context(DEV='QCOM'):
    if not isinstance(Device['QCOM'], QCOMDevice):
      raise RuntimeError('Expected the native QCOM device')
    data = stream.read()
    unchanged()
    artifact = pickle.loads(data)
    if not isinstance(artifact, dict) or set(artifact) != {'metadata', 'run', 'input_specs'}:
      raise ValueError('Unexpected native monitoring warp layout')
    return protection.warp(artifact['run'])
