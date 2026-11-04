"""Private stdlib-only tests of exact AST-extracted vendor reader; no product imports."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from collections.abc import Callable
from typing import cast
import unittest

SOURCE = Path(os.environ.get('STARPILOT_NATIVE_SHARD_SOURCE_ROOT', Path(__file__).resolve().parents[4]))
BRIDGE = SOURCE / 'openpilot/starpilot/models/runtime_bridge'
NAMES = {'_plain_file', '_unique_object', '_vendor_mapping', '_vendor_files'}


def subjects(root):
  tree = ast.parse((BRIDGE / 'native.py').read_text())
  namespace: dict[str, object] = {'Path': Path, 'PurePosixPath': PurePosixPath, 'hashlib': hashlib,
                                 'json': json, 'stat': stat, 'BRIDGE': root}
  nodes: list[ast.stmt] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
  if {n.name for n in nodes if isinstance(n, ast.FunctionDef)} != NAMES:
    raise AssertionError('Missing exact native reader definitions')
  exec(compile(ast.Module(body=nodes, type_ignores=[]), str(BRIDGE / 'native.py'), 'exec'), namespace)
  return cast(Callable[[object], dict[str, str]], namespace['_vendor_files'])


class Shards(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
    self.root = Path(self.temp.name).resolve()
    self.reader = subjects(self.root)
    for path in BRIDGE.glob('native-vendor-*.json'):
      shutil.copyfile(path, self.root / path.name)
    self.policy = json.loads((BRIDGE / 'native-policy.json').read_text())
    self.original = self.reader(self.policy)

  def tearDown(self):
    self.temp.cleanup()

  def read(self):
    return self.reader(self.policy)

  def replace_part(self, raw):
    part = self.policy['vendor_parts'][0]
    (self.root / part['name']).write_bytes(raw)
    part['sha256'] = hashlib.sha256(raw).hexdigest()

  def test_exact_1669_and_flat(self):
    self.assertEqual(len(self.original), 1669)
    self.assertEqual(self.read(), self.original)
    self.assertEqual(self.reader({'vendor_files': self.original}), self.original)
    self.assertTrue(all(path.stat().st_size <= 96 * 1024 for path in self.root.iterdir()))

  def test_tamper_and_missing(self):
    path = self.root / self.policy['vendor_parts'][0]['name']
    original = path.read_bytes()
    path.write_bytes(original + b' ')
    with self.assertRaises(ValueError):
      self.read()
    path.unlink()
    with self.assertRaises(OSError):
      self.read()

  def test_symlink(self):
    path = self.root / self.policy['vendor_parts'][0]['name']
    target = self.root / 'target'
    path.rename(target)
    path.symlink_to(target)
    with self.assertRaises(ValueError):
      self.read()

  def test_json_duplicate_and_malformed(self):
    for raw in (b'{"x":"' + b'0' * 64 + b'","x":"' + b'0' * 64 + b'"}', b'{'):
      with self.subTest(raw=raw):
        self.replace_part(raw)
        with self.assertRaises(ValueError):
          self.read()

  def test_cross_part_duplicate(self):
    first = self.policy['vendor_parts'][0]
    second = self.policy['vendor_parts'][1]
    raw = (self.root / first['name']).read_bytes()
    (self.root / second['name']).write_bytes(raw)
    second.update(sha256=hashlib.sha256(raw).hexdigest(), count=first['count'])
    with self.assertRaises(ValueError):
      self.read()

  def test_format_name_count_and_digest_rejects(self):
    original = copy.deepcopy(self.policy)
    mutations = [lambda p: p.update(vendor_files=self.original),
                 lambda p: p.update(vendor_file_count=True),
                 lambda p: p.update(vendor_file_count=1670),
                 lambda p: p.update(vendor_parts=[]),
                 lambda p: p['vendor_parts'][0].update(name='../native-vendor-01.json'),
                 lambda p: p['vendor_parts'][0].update(count=True),
                 lambda p: p['vendor_parts'][0].update(count=1),
                 lambda p: p['vendor_parts'][0].update(sha256='G' * 64),
                 lambda p: p['vendor_parts'][0].update(extra=1)]
    for mutate in mutations:
      self.policy = copy.deepcopy(original)
      mutate(self.policy)
      with self.subTest(policy=self.policy['vendor_file_count']):
        with self.assertRaises(ValueError):
          self.read()

  def test_entry_types_paths_and_hashes(self):
    for value in ({}, [], {'../escape': '0' * 64}, {'/absolute': '0' * 64},
                  {'a//b': '0' * 64}, {'a\\b': '0' * 64}, {'a': 12}, {'a': 'z' * 64}, {'': '0' * 64}):
      self.replace_part(json.dumps(value).encode())
      with self.subTest(value=value):
        with self.assertRaises(ValueError):
          self.read()

  def test_oversize(self):
    self.replace_part(b' ' * (96 * 1024 + 1))
    with self.assertRaises(ValueError):
      self.read()


if __name__ == '__main__':
  unittest.main()
