#!/usr/bin/env python3
"""Re-vendor jetlink_repo/ from an upstream zoompilot/jetlink checkout (used by .github/workflows/jetlink-update.yaml).

usage: jetlink_vendor_update.py <upstream-checkout> <new-tag> [--repo-root DIR] [--summary FILE] [--github-output FILE]

<upstream-checkout> is a git clone of zoompilot/jetlink that has both the old tag (read from the vendored
jetlink/__init__.py __version__, as `v<version>`) and <new-tag>. Everything is read from git objects, so the working
tree of the clone does not matter.

What is vendored (the "sync set"), the same rule for the old and the new tag:
  - LICENSE, README.md and pyproject.toml at the upstream root, and
  - every file under jetlink/ except tests: directories named tests or test, test_*.py, *_test.py, conftest.py and
    anything under __pycache__ or ending in .pyc.
So a file that upstream adds to a package directory (new module, new data file) is added, a file upstream no longer
has is removed, and every other vendored file is overwritten with the upstream one. Nothing outside that set is
touched, and upstream files outside it (docs/, install.sh, the Swift and Android apps, tests) are never copied.

Fork patches: a vendored file whose content differs from the old tag's version carries a local patch (today
jetlink/openpilot/joining.py and model_state.py, explicit string concatenation). Those are 3-way merged with
`git merge-file` (base = old tag, ours = vendored copy, theirs = new tag). If the merge conflicts, the fork copy is
kept unchanged, no conflict markers are written, and the summary says so, because the upstream changes to that file are
then NOT applied and need a manual merge. A patched file that upstream deleted is removed and flagged the same way.

Also rewrites the old tag to the new tag in openpilot/starpilot/models/JETLINK.md, and reports whether the adapter API
(`API = <n>` in jetlink/openpilot/__init__.py) changed.

Exit status: 0 when the update ran (conflicts and API changes are reported, not failures), 2 on a usage or input error.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

VENDOR_DIR = 'jetlink_repo'
VERSION_FILE = 'jetlink/__init__.py'
API_FILE = 'jetlink/openpilot/__init__.py'
DOC_FILE = 'openpilot/starpilot/models/JETLINK.md'
ROOT_FILES = ('LICENSE', 'README.md', 'pyproject.toml')
PACKAGE_DIR = 'jetlink'
TEST_DIRS = ('tests', 'test', '__pycache__')
TEST_FILE_GLOBS = ('test_*.py', '*_test.py', 'conftest.py', '*.pyc')

VERSION_RE = re.compile(r"""^__version__\s*=\s*['"]([^'"]+)['"]\s*$""", re.M)
API_RE = re.compile(r'^API\s*=\s*(\d+)\s*$', re.M)


class UpdateError(Exception):
  pass


@dataclass
class Summary:
  old_tag: str
  new_tag: str
  changed: list[str] = field(default_factory=list)
  added: list[str] = field(default_factory=list)
  removed: list[str] = field(default_factory=list)
  merged: list[str] = field(default_factory=list)  # patched files whose fork patch was kept (clean 3-way merge)
  conflicted: list[str] = field(default_factory=list)  # patched files kept as the fork copy
  patched_removed: list[str] = field(default_factory=list)  # patched files that upstream deleted
  old_api: int | None = None
  new_api: int | None = None
  doc_replacements: int = 0

  @property
  def api_changed(self) -> bool:
    return self.old_api != self.new_api

  @property
  def needs_review(self) -> bool:
    return self.api_changed or bool(self.conflicted) or bool(self.patched_removed)

  def markdown(self) -> str:
    def files(title, names):
      return [f'### {title} ({len(names)})', '', *([f'- `{n}`' for n in names] or ['- none']), '']

    lines = [f'## Jetlink re-vendor: {self.old_tag} -> {self.new_tag}', '']
    if self.needs_review:
      lines += ['**NEEDS REVIEW**: see the API and fork patch sections below.', '']
    lines += ['### Fork API version', '']
    if self.api_changed:
      lines.append(f'**Changed**: `API = {self.old_api}` -> `API = {self.new_api}` in `{API_FILE}`. Check the fork adapter ' +
                   'against the upstream porting notes and that it still declares an API that upstream accepts.')
    else:
      lines.append(f'Unchanged: `API = {self.new_api}`.')
    lines += ['', '### Fork patches (3-way merge: base = upstream old tag, ours = fork copy, theirs = upstream new tag)', '']
    if self.conflicted:
      lines.append('**Conflict**: the fork copy was kept unchanged for these files, so upstream changes to them are NOT ' +
                   'applied. Merge them by hand:')
      lines += [f'- `{n}`' for n in self.conflicted]
    if self.patched_removed:
      lines.append('**Deleted upstream** while carrying a fork patch (removed here; check that nothing still imports it):')
      lines += [f'- `{n}`' for n in self.patched_removed]
    if self.merged:
      lines.append('Merged cleanly (fork patch kept on top of the new upstream file):')
      lines += [f'- `{n}`' for n in self.merged]
    if not (self.conflicted or self.patched_removed or self.merged):
      lines.append('No vendored file carried a fork patch.')
    lines += ['', *files('Files changed', self.changed), *files('Files added', self.added), *files('Files removed', self.removed)]
    lines += ['### Docs', '',
              f'`{DOC_FILE}`: {self.doc_replacements} reference(s) to `{self.old_tag}` rewritten to `{self.new_tag}`.'
              + ('' if self.doc_replacements else ' **None found: check the links by hand.**'), '']
    return '\n'.join(lines)


def run_git(cwd: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
  proc = subprocess.run(['git', '-C', cwd, *args], capture_output=True)
  if check and proc.returncode != 0:
    raise UpdateError(f'git {" ".join(args)} failed in {cwd}: {proc.stderr.decode(errors="replace").strip()}')
  return proc


def is_test_path(path: str) -> bool:
  parts = PurePosixPath(path).parts
  if any(p in TEST_DIRS for p in parts[:-1]):
    return True
  return any(fnmatch.fnmatch(parts[-1], g) for g in TEST_FILE_GLOBS)


def in_sync_set(path: str) -> bool:
  if path in ROOT_FILES:
    return True
  return path.startswith(PACKAGE_DIR + '/') and not is_test_path(path)


def list_upstream(upstream: str, ref: str) -> dict[str, str]:
  """Sync-set files at `ref` as {path: git mode} (100644 or 100755)."""
  out = run_git(upstream, 'ls-tree', '-r', '-z', f'{ref}^{{tree}}').stdout.decode()
  files = {}
  for entry in filter(None, out.split('\0')):
    meta, path = entry.split('\t', 1)
    mode, kind, _ = meta.split()
    if kind == 'blob' and mode in ('100644', '100755') and in_sync_set(path):
      files[path] = mode
  return files


def upstream_blob(upstream: str, ref: str, path: str) -> bytes:
  return run_git(upstream, 'cat-file', 'blob', f'{ref}:{path}').stdout


def read_regex(text: bytes, regex: re.Pattern, what: str) -> str:
  match = regex.search(text.decode())
  if not match:
    raise UpdateError(f'cannot find {what}')
  return match.group(1)


def api_at(upstream: str, ref: str) -> int:
  return int(read_regex(upstream_blob(upstream, ref, API_FILE), API_RE, f'API in {API_FILE} at {ref}'))


def resolve_ref(upstream: str, tag: str) -> str:
  proc = run_git(upstream, 'rev-parse', '--verify', '--quiet', f'refs/tags/{tag}^{{commit}}', check=False)
  if proc.returncode != 0:
    raise UpdateError(f'tag {tag} not found in {upstream}; fetch tags first (git fetch --tags)')
  return f'refs/tags/{tag}'


def merge3(base: bytes, ours: bytes, theirs: bytes) -> tuple[bytes, bool]:
  """git merge-file -p: returns (merged bytes, conflicted). On conflict the caller must not use the bytes."""
  with tempfile.TemporaryDirectory() as tmp:
    paths = []
    for name, data in (('ours', ours), ('base', base), ('theirs', theirs)):
      path = os.path.join(tmp, name)
      with open(path, 'wb') as f:
        f.write(data)
      paths.append(path)
    proc = subprocess.run(['git', 'merge-file', '-p', *paths], capture_output=True)
  if proc.returncode < 0 or proc.returncode > 127:
    raise UpdateError(f'git merge-file failed: {proc.stderr.decode(errors="replace").strip()}')
  return proc.stdout, proc.returncode > 0


def vendored_files(vendor: str) -> set[str]:
  found = set()
  for dirpath, dirnames, filenames in os.walk(vendor):
    dirnames[:] = [d for d in dirnames if d != '__pycache__']
    for name in filenames:
      rel = os.path.relpath(os.path.join(dirpath, name), vendor).replace(os.sep, '/')
      if not rel.endswith('.pyc'):
        found.add(rel)
  return found


def write_file(vendor: str, rel: str, data: bytes, mode: str) -> None:
  if '..' in PurePosixPath(rel).parts or rel.startswith('/'):
    raise UpdateError(f'refusing to write outside {VENDOR_DIR}: {rel}')
  path = os.path.join(vendor, rel)
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'wb') as f:
    f.write(data)
  os.chmod(path, 0o755 if mode == '100755' else 0o644)


def rewrite_docs(doc_path: str, old_tag: str, new_tag: str) -> int:
  if not os.path.exists(doc_path):
    return 0
  with open(doc_path, encoding='utf-8') as f:
    text = f.read()
  # `v0.8.1` must not match inside `v0.8.12` or `v0.8.1.5`
  new_text, count = re.subn(re.escape(old_tag) + r'(?![0-9]|\.[0-9])', new_tag, text)
  if count:
    with open(doc_path, 'w', encoding='utf-8') as f:
      f.write(new_text)
  return count


def remove_vendored(vendor: str, rel: str) -> None:
  os.remove(os.path.join(vendor, rel))
  parent = os.path.dirname(os.path.join(vendor, rel))
  while parent != vendor and not os.listdir(parent):
    os.rmdir(parent)
    parent = os.path.dirname(parent)


def update(upstream: str, new_tag: str, repo_root: str) -> Summary:
  vendor = os.path.join(repo_root, VENDOR_DIR)
  version_path = os.path.join(vendor, VERSION_FILE)
  if not os.path.exists(version_path):
    raise UpdateError(f'{version_path} not found')
  with open(version_path, 'rb') as f:
    old_tag = 'v' + read_regex(f.read(), VERSION_RE, f'__version__ in {version_path}')
  if not re.fullmatch(r'v\d+(\.\d+)*', new_tag):
    raise UpdateError(f'new tag {new_tag!r} does not look like vX.Y.Z')
  old_ref, new_ref = resolve_ref(upstream, old_tag), resolve_ref(upstream, new_tag)

  old_files, new_files = list_upstream(upstream, old_ref), list_upstream(upstream, new_ref)
  have = vendored_files(vendor)
  summary = Summary(old_tag=old_tag, new_tag=new_tag, old_api=api_at(upstream, old_ref), new_api=api_at(upstream, new_ref))

  # A vendored file that was upstream at the old tag and is not at the new one was deleted upstream. A vendored file
  # that was never upstream (not in the old sync set) is not ours to remove.
  for rel in sorted(have):
    if rel in new_files or rel not in old_files:
      continue
    with open(os.path.join(vendor, rel), 'rb') as f:
      if f.read() != upstream_blob(upstream, old_ref, rel):
        summary.patched_removed.append(rel)
    remove_vendored(vendor, rel)
    summary.removed.append(rel)

  for rel, mode in sorted(new_files.items()):
    theirs = upstream_blob(upstream, new_ref, rel)
    path = os.path.join(vendor, rel)
    if rel not in have:
      write_file(vendor, rel, theirs, mode)
      summary.added.append(rel)
      continue
    with open(path, 'rb') as f:
      ours = f.read()
    base = upstream_blob(upstream, old_ref, rel) if rel in old_files else None
    if base is not None and ours != base:  # carries a fork patch
      if base == theirs:
        summary.merged.append(rel)  # upstream did not touch it: the fork copy stays as it is
        continue
      merged, conflicted = merge3(base, ours, theirs)
      if conflicted:
        summary.conflicted.append(rel)
        continue
      if merged != ours:
        write_file(vendor, rel, merged, mode)
        summary.changed.append(rel)
      summary.merged.append(rel)
    elif ours != theirs:
      write_file(vendor, rel, theirs, mode)
      summary.changed.append(rel)

  summary.doc_replacements = rewrite_docs(os.path.join(repo_root, DOC_FILE), old_tag, new_tag)
  return summary


def main(argv: list[str]) -> int:
  parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
  parser.add_argument('upstream', help='git clone of zoompilot/jetlink with the old and new tags')
  parser.add_argument('new_tag', help='tag to vendor, e.g. v0.9.0')
  parser.add_argument('--repo-root', default='.', help='root of the fork checkout (default: current directory)')
  parser.add_argument('--summary', default='jetlink-update-summary.md', help='markdown summary file to write')
  parser.add_argument('--github-output', help='file (usually $GITHUB_OUTPUT) to append old_tag, new_tag, api_changed, ' +
                                              'conflicts and needs_review to')
  args = parser.parse_args(argv)
  try:
    summary = update(args.upstream, args.new_tag, args.repo_root)
  except UpdateError as e:
    print(f'error: {e}', file=sys.stderr)
    return 2
  with open(args.summary, 'w', encoding='utf-8') as f:
    f.write(summary.markdown())
  if args.github_output:
    with open(args.github_output, 'a', encoding='utf-8') as f:
      f.write(f'old_tag={summary.old_tag}\nnew_tag={summary.new_tag}\n' +
              f'api_changed={str(summary.api_changed).lower()}\nconflicts={len(summary.conflicted)}\n' +
              f'needs_review={str(summary.needs_review).lower()}\n')
  print(summary.markdown())
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
