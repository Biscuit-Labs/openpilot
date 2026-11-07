"""tools/ci/jetlink_vendor_update.py against throwaway upstream and fork directories (needs git on PATH)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.ci import jetlink_vendor_update as jvu

INIT = "__version__ = '{v}'\n"
OPENPILOT_INIT = '"""adapter"""\nAPI = {api}\n'
JOINING_V1 = 'def warn():\n  log(\n    "dropped %d frames "\n    "behind the model")\n\n\ndef other():\n  return 1\n'
JOINING_FORK = 'def warn():\n  log(\n    "dropped %d frames " +\n    "behind the model")\n\n\ndef other():\n  return 1\n'
JOINING_V2_FAR = JOINING_V1.replace('return 1', 'return 2')  # upstream edit far away from the fork patch
JOINING_V2_NEAR = JOINING_V1.replace('behind the model', 'behind the big model')  # upstream edit on the patched line
DOC = ('[installer](https://github.com/zoompilot/jetlink/blob/v0.8.1/install.sh) and ' +
       '[docs](https://github.com/zoompilot/jetlink/tree/v0.8.1/docs), also v0.8.10 stays\n')


def git(cwd, *args):
  subprocess.run(['git', '-C', str(cwd), '-c', 'user.name=t', '-c', 'user.email=t@t', *args], check=True, capture_output=True)


def write(root, files):
  for rel, content in files.items():
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)


def tree_state(root):
  return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob('*')) if p.is_file()}


class TestJetlinkVendorUpdate(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.up = Path(self.tmp.name) / 'up'
    self.fork = Path(self.tmp.name) / 'fork'
    self.up.mkdir()
    self.fork.mkdir()
    git(self.up, 'init', '-q')
    self.v1 = {
      'LICENSE': 'MIT v1\n', 'README.md': 'readme v1\n', 'pyproject.toml': 'p v1\n',
      'jetlink/__init__.py': INIT.format(v='0.8.1'), 'jetlink/openpilot/__init__.py': OPENPILOT_INIT.format(api=3),
      'jetlink/client.py': 'client v1\n', 'jetlink/old.py': 'old module\n', 'jetlink/openpilot/joining.py': JOINING_V1,
      'jetlink/tests/test_client.py': 'tests never vendored\n', 'jetlink/openpilot/test_x.py': 'nor this\n',
      'docs/guide.md': 'upstream docs never vendored\n',
    }
    self.upstream_commit(self.v1, 'v0.8.1')
    # vendored copy: v0.8.1 with the fork patch in joining.py (the test files and docs are not vendored)
    vendored = {k: v for k, v in self.v1.items() if k.startswith(('jetlink/', 'LICENSE', 'README', 'pyproject'))
                and '/tests/' not in k and 'test_x' not in k}
    vendored['jetlink/openpilot/joining.py'] = JOINING_FORK
    write(self.fork / 'jetlink_repo', vendored)
    write(self.fork, {'openpilot/starpilot/models/JETLINK.md': DOC})

  def upstream_commit(self, files, tag, remove=()):
    for rel in remove:
      (self.up / rel).unlink()
    write(self.up, files)
    git(self.up, 'add', '-A')
    git(self.up, 'commit', '-q', '-m', tag)
    git(self.up, 'tag', tag)

  def release_v2(self, joining=JOINING_V2_FAR, api=3, **extra):
    files = {
      'LICENSE': 'MIT v2\n', 'jetlink/__init__.py': INIT.format(v='0.9.0'), 'jetlink/client.py': 'client v2\n',
      'jetlink/openpilot/__init__.py': OPENPILOT_INIT.format(api=api), 'jetlink/openpilot/joining.py': joining,
      'jetlink/new.py': 'new module\n', 'jetlink/tests/test_new.py': 'ignored\n', **extra,
    }
    self.upstream_commit(files, 'v0.9.0', remove=['jetlink/old.py'])

  def run_update(self):
    return jvu.update(str(self.up), 'v0.9.0', str(self.fork))

  def vendored(self, rel):
    return (self.fork / 'jetlink_repo' / rel).read_text()

  def test_update_add_remove_and_ignored_files(self):
    self.release_v2()
    s = self.run_update()
    self.assertEqual((s.old_tag, s.new_tag), ('v0.8.1', 'v0.9.0'))
    self.assertEqual(self.vendored('jetlink/client.py'), 'client v2\n')
    self.assertEqual(self.vendored('LICENSE'), 'MIT v2\n')
    self.assertEqual(self.vendored('README.md'), 'readme v1\n')
    self.assertIn('jetlink/new.py', s.added)
    self.assertEqual(self.vendored('jetlink/new.py'), 'new module\n')
    self.assertEqual(s.removed, ['jetlink/old.py'])
    self.assertFalse((self.fork / 'jetlink_repo/jetlink/old.py').exists())
    for never in ('jetlink/tests/test_new.py', 'jetlink/tests/test_client.py', 'jetlink/openpilot/test_x.py', 'docs/guide.md'):
      self.assertFalse((self.fork / 'jetlink_repo' / never).exists(), never)
    self.assertIn('jetlink/__init__.py', s.changed)
    self.assertIn("'0.9.0'", self.vendored('jetlink/__init__.py'))

  def test_fork_patch_is_merged_with_upstream_change(self):
    self.release_v2(joining=JOINING_V2_FAR)
    s = self.run_update()
    self.assertEqual(s.conflicted, [])
    self.assertEqual(s.merged, ['jetlink/openpilot/joining.py'])
    self.assertIn('jetlink/openpilot/joining.py', s.changed)
    merged = self.vendored('jetlink/openpilot/joining.py')
    self.assertEqual(merged, JOINING_FORK.replace('return 1', 'return 2'))  # fork '+' kept, upstream edit applied

  def test_fork_patch_kept_when_upstream_did_not_touch_file(self):
    self.release_v2(joining=JOINING_V1)
    s = self.run_update()
    self.assertEqual(s.merged, ['jetlink/openpilot/joining.py'])
    self.assertNotIn('jetlink/openpilot/joining.py', s.changed)
    self.assertEqual(self.vendored('jetlink/openpilot/joining.py'), JOINING_FORK)

  def test_conflict_keeps_fork_copy_without_markers_and_is_flagged(self):
    self.release_v2(joining=JOINING_V2_NEAR)
    s = self.run_update()
    self.assertEqual(s.conflicted, ['jetlink/openpilot/joining.py'])
    self.assertEqual(self.vendored('jetlink/openpilot/joining.py'), JOINING_FORK)
    self.assertTrue(s.needs_review)
    md = s.markdown()
    self.assertIn('**Conflict**', md)
    self.assertIn('NEEDS REVIEW', md)
    self.assertNotIn('<<<<<<<', self.vendored('jetlink/openpilot/joining.py'))

  def test_patched_file_deleted_upstream_is_flagged(self):
    self.release_v2()
    (self.up / 'jetlink/openpilot/joining.py').unlink()
    git(self.up, 'add', '-A')
    git(self.up, 'commit', '-q', '--amend', '--no-edit')
    git(self.up, 'tag', '-f', 'v0.9.0')
    s = self.run_update()
    self.assertEqual(s.patched_removed, ['jetlink/openpilot/joining.py'])
    self.assertIn('jetlink/openpilot/joining.py', s.removed)
    self.assertTrue(s.needs_review)

  def test_api_change_detected(self):
    self.release_v2(api=4)
    s = self.run_update()
    self.assertEqual((s.old_api, s.new_api), (3, 4))
    self.assertTrue(s.api_changed)
    self.assertTrue(s.needs_review)
    self.assertIn('`API = 3` -> `API = 4`', s.markdown())

  def test_api_unchanged(self):
    self.release_v2()
    s = self.run_update()
    self.assertFalse(s.api_changed)
    self.assertFalse(s.needs_review)
    self.assertIn('Unchanged: `API = 3`', s.markdown())

  def test_docs_tag_rewritten_without_touching_longer_versions(self):
    self.release_v2()
    s = self.run_update()
    doc = (self.fork / jvu.DOC_FILE).read_text()
    self.assertEqual(s.doc_replacements, 2)
    self.assertIn('blob/v0.9.0/install.sh', doc)
    self.assertIn('tree/v0.9.0/docs', doc)
    self.assertIn('v0.8.10 stays', doc)

  def test_executable_bit_is_kept_for_new_files(self):
    script = self.up / 'jetlink/run.sh'
    self.release_v2(**{'jetlink/run.sh': '#!/bin/sh\n'})
    script.chmod(0o755)
    git(self.up, 'add', '-A')
    git(self.up, 'commit', '-q', '--amend', '--no-edit')
    git(self.up, 'tag', '-f', 'v0.9.0')
    self.run_update()
    self.assertTrue(os.access(self.fork / 'jetlink_repo/jetlink/run.sh', os.X_OK))

  def test_second_run_changes_nothing(self):
    self.release_v2()
    self.run_update()
    before = tree_state(self.fork)
    s = self.run_update()  # vendored is now v0.9.0: old tag == new tag
    self.assertEqual((s.changed, s.added, s.removed, s.conflicted), ([], [], [], []))
    self.assertEqual(before, tree_state(self.fork))

  def test_missing_tag_is_an_error_and_main_returns_2(self):
    self.release_v2()
    with self.assertRaises(jvu.UpdateError):
      jvu.update(str(self.up), 'v9.9.9', str(self.fork))
    summary = Path(self.tmp.name) / 's.md'
    self.assertEqual(jvu.main([str(self.up), 'v9.9.9', '--repo-root', str(self.fork), '--summary', str(summary)]), 2)
    self.assertFalse(summary.exists())

  def test_main_writes_summary_and_github_output(self):
    self.release_v2(api=4, joining=JOINING_V2_NEAR)
    summary, out = Path(self.tmp.name) / 's.md', Path(self.tmp.name) / 'out'
    code = jvu.main([str(self.up), 'v0.9.0', '--repo-root', str(self.fork), '--summary', str(summary), '--github-output', str(out)])
    self.assertEqual(code, 0)
    text = out.read_text()
    for line in ('old_tag=v0.8.1', 'new_tag=v0.9.0', 'api_changed=true', 'conflicts=1', 'needs_review=true'):
      self.assertIn(line, text)
    self.assertIn('v0.8.1 -> v0.9.0', summary.read_text())


if __name__ == '__main__':
  unittest.main()
