"""Exact native reader AST with inert GPU buffers and a real authenticated fd."""
import ast
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import pickle
import stat
import struct
import tempfile
from types import ModuleType, SimpleNamespace
from typing import Any, cast
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(os.environ.get('STARPILOT_NATIVE_READER_SOURCE', Path(__file__).resolve().parents[1] / 'runtime_bridge/native.py'))
CHUNK = 8 << 20


class Stream:
  def __init__(self, stream, events, pending, truncate=False):
    self.stream, self.events, self.pending, self.truncate = stream, events, pending, truncate
  def fileno(self):
    return self.stream.fileno()
  def tell(self):
    return self.stream.tell()
  def read(self, size):
    self.events.append(('read', size))
    return self.stream.read(size)
  def readinto(self, view):
    if self.pending:
      raise AssertionError('staging reused before synchronization')
    self.events.append(('readinto', len(view)))
    count = self.stream.readinto(view)
    return count - 1 if self.truncate else count


class TestNativeDrivingReader(unittest.TestCase):
  def setUp(self):
    self.temp = self.enterContext(tempfile.TemporaryDirectory())
    self.path = Path(self.temp) / 'artifact.pkl'
    self.events: list[Any] = []
    self.pending: list[Any] = []
    self.arenas: list[bytearray] = []
    self.stages: list[memoryview] = []
    self.allocations: list[Any] = []
    tree = ast.parse(SOURCE.read_text())
    nodes: list[ast.stmt] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_verified', '_load_driving')]
    self.ns: dict[str, Any] = {"contextmanager": contextmanager, "os": os, "stat": stat, "hashlib": hashlib,
                               "Path": Path, "cast": cast, "_allowed": {}, "__name__": __name__}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), self.ns)
    owner = self

    class Buffer:
      def __init__(self, device, size, preallocate=False, opaque=None):
        owner.allocations.append((device, size, preallocate, opaque is not None))
        self.device, self.offset, self.size = device, 0, size
        self.data = opaque if opaque is not None else bytearray(size)
        if opaque is not None:
          owner.stages.append(opaque)
        else:
          owner.arenas.append(self.data)
      def view(self, size, offset):
        if size < 0 or offset < 0 or offset + size > self.size:
          raise ValueError('view outside arena')
        return View(self.data, self.offset + offset, size)
      def __del__(self):
        if self.device == 'HOST':
          owner.events.append('staging-buffer-released')

    class View:
      def __init__(self, data, offset, size):
        self.data, self.offset, self.size = data, offset, size
      def ensure_allocated(self):
        return self
      def copy_from(self, source):
        owner.events.append(('copy', self.offset, self.size, source.offset))
        owner.pending.append((self, source))
    def synchronize():
      for target, source in self.pending:
        target.data[target.offset:target.offset + target.size] = source.data[source.offset:source.offset + source.size]
      self.pending.clear()
      self.events.append('sync')
    tg = ModuleType('tinygrad')
    tg.Device = SimpleNamespace(DEFAULT='GPU', default=SimpleNamespace(synchronize=synchronize))
    device = ModuleType('tinygrad.device')
    device.Buffer, device.HCQ_RUNTIME_DEV = Buffer, SimpleNamespace(device='HOST')
    self.enterContext(patch.dict('sys.modules', {'tinygrad': tg, 'tinygrad.device': device}))

  def envelope(self, payload, opcodes=b'actual opaque opcodes'):
    data = struct.pack('<q', len(opcodes)) + opcodes + payload
    self.path.write_bytes(data)
    self.ns['_allowed'][str(self.path)] = {'artifact_size': len(data), 'artifact_sha256': hashlib.sha256(data).hexdigest()}
    return opcodes

  def test_exact_chunked_bytes_offsets_alias_tail_sync_and_release(self):
    payload = bytes(range(251)) * ((2 * CHUNK + 173) // 251 + 1)
    payload = payload[:2 * CHUNK + 173]
    opcodes = self.envelope(payload)
    owner = self
    class Unpickler:
      persistent_load: Any
      def __init__(self, stream):
        owner.assertEqual(stream.read(), opcodes)
      def load(self):
        owner.events.append('unpickle')
        owner.assertIn('staging-buffer-released', owner.events)
        with owner.assertRaises(ValueError):
          _ = owner.stages[0].nbytes
        return (self.persistent_load((CHUNK + 9, CHUNK - 7)), self.persistent_load((173, 2 * CHUNK)))
    with patch.object(pickle, 'Unpickler', Unpickler), self.ns['_verified'](self.path) as (stream, unchanged):
      aliases = self.ns['_load_driving'](Stream(stream, self.events, self.pending), unchanged)
    self.assertEqual(bytes(self.arenas[0]), payload)
    self.assertEqual(self.allocations, [('GPU', len(payload), True, False), ('HOST', CHUNK, False, True)])
    self.assertEqual([e for e in self.events if isinstance(e, tuple) and e[0] == 'read'], [('read', 8), ('read', len(opcodes))])
    self.assertEqual([e for e in self.events if isinstance(e, tuple) and e[0] == 'readinto'], [('readinto', CHUNK), ('readinto', CHUNK), ('readinto', 173)])
    self.assertEqual([e for e in self.events if isinstance(e, tuple) and e[0] == 'copy'],
                     [('copy', 0, CHUNK, 0), ('copy', CHUNK, CHUNK, 0), ('copy', 2 * CHUNK, 173, 0)])
    self.assertEqual(self.events.count('sync'), 3)
    for alias, offset, size in ((aliases[0], CHUNK - 7, CHUNK + 9), (aliases[1], 2 * CHUNK, 173)):
      self.assertIs(alias.data, self.arenas[0])
      self.assertEqual(bytes(alias.data[offset:offset + size]), payload[offset:offset + size])
    self.assertEqual(self.events[-1], 'unpickle')

  def test_zero_oob_uses_real_pickle_loads_without_buffer_allocation(self):
    expected = {'metadata': ('unchanged', 7)}
    self.envelope(b'', pickle.dumps(expected))
    unchanged = Mock()
    with self.path.open('rb') as stream:
      self.assertEqual(self.ns['_load_driving'](Stream(stream, self.events, self.pending), unchanged), expected)
    unchanged.assert_called_once_with()
    self.assertEqual(self.allocations, [])

  def test_truncated_payload_readinto_fails_before_deserialization(self):
    self.envelope(b'payload')
    with self.path.open('rb') as stream, patch.object(pickle, 'Unpickler', side_effect=AssertionError('must not deserialize')):
      with self.assertRaisesRegex(ValueError, 'Truncated native OOB payload'):
        self.ns['_load_driving'](Stream(stream, self.events, self.pending, truncate=True), lambda: None)

  def test_unchanged_exception_propagates_before_transfer(self):
    self.envelope(b'payload')
    failure = RuntimeError('owned unchanged failure')
    with self.path.open('rb') as stream:
      with self.assertRaises(RuntimeError) as raised:
        self.ns['_load_driving'](stream, Mock(side_effect=failure))
    self.assertIs(raised.exception, failure)
    self.assertEqual(self.pending, [])

  def test_authenticated_descriptor_mutation_is_rejected_after_copy(self):
    self.envelope(b'payload')
    class MutatingStream(Stream):
      def readinto(inner, view):
        count = super().readinto(view)
        with self.path.open('ab') as target:
          target.write(b'mutated')
        return count
    with self.assertRaisesRegex(ValueError, 'changed while loading'):
      with self.ns['_verified'](self.path) as (stream, unchanged):
        self.ns['_load_driving'](MutatingStream(stream, self.events, self.pending), unchanged)


if __name__ == '__main__':
  unittest.main()
