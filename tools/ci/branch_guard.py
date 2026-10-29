"""Enforce the Honda-PTM branch flow on pull requests (docs/BRANCH_WORKFLOW.md).

Rulesets can protect a branch, but they cannot say which branch a pull request comes from. This check does:
  - Honda-PTM-Stage takes pull requests only from Honda-PTM-Testing,
  - Honda-PTM-Stable takes pull requests only from Honda-PTM-Stage,
  - Honda-PTM-Testing takes no pull request from Stage, Stable or Clean (changes move one way), and
    no branch named with a tool or agent prefix such as `claude/`,
  - Honda-PTM-Clean is checked by tools/night_star_port/check_clean_branch.py against Honda-PTM-Stable,
  - a pull request into Honda-PTM-Testing must be branched from Testing (or from a branch of Testing): it may not
    carry commits that are on Stage or Stable but not on Testing, such as promotion merge commits.

Git does not record which branch a branch was created from, so this is checked from the commits the pull request brings.

Promotion pull requests must come from this repository, not from a fork.

usage: branch_guard.py <base> <head> <head-repo> <repo> [<head-sha>]
"""
import subprocess
import sys

STABLE, STAGE, TESTING, CLEAN = 'Honda-PTM-Stable', 'Honda-PTM-Stage', 'Honda-PTM-Testing', 'Honda-PTM-Clean'
LONG_LIVED = (STABLE, STAGE, TESTING, CLEAN)
PROMOTES_FROM = {STAGE: TESTING, STABLE: STAGE}
AGENT_PREFIXES = ('claude/', 'codex/', 'copilot/', 'cursor/', 'gemini/')


def violations(base, head, head_repo, repo):
  if base in PROMOTES_FROM:
    source = PROMOTES_FROM[base]
    if head != source or head_repo != repo:
      return [f'{base} takes pull requests only from {repo}:{source}, not {head_repo}:{head}. '
              f'Open the change against {TESTING} and promote it.']
    return []
  if base == TESTING:
    if head in LONG_LIVED and head_repo == repo:
      return [f'{head} does not merge back into {TESTING}: changes move Testing -> Stage -> Stable only. '
              f'Branch the fix off {TESTING} instead.']
    if head.lower().startswith(AGENT_PREFIXES):
      return [f'branch {head} uses a tool or agent prefix; name it after the work (for example wifi-power-save)']
  return []


def rev_list(*revs):
  return set(subprocess.run(['git', 'rev-list', *revs], check=True, capture_output=True, text=True).stdout.split())


def base_violations(base, head_sha, remote='origin'):
  """Commits the pull request brings that come from Stage or Stable instead of Testing."""
  if base != TESTING:
    return []
  brought = rev_list(head_sha, f'^{remote}/{TESTING}')
  promoted = rev_list(f'{remote}/{STAGE}', f'{remote}/{STABLE}', f'^{remote}/{TESTING}')
  foreign = brought & promoted
  if not foreign:
    return []
  return [f'this branch carries {len(foreign)} commit(s) from {STAGE} or {STABLE} that are not on {TESTING} '
          f'(for example {sorted(foreign)[0][:12]}). Branch off {TESTING} instead and cherry-pick your own commits.']


def main(argv):
  if len(argv) not in (4, 5):
    sys.exit(__doc__)
  found = violations(*argv[:4])
  if len(argv) == 5:
    found += base_violations(argv[0], argv[4])
  for line in found:
    print(f'::error::{line}')
  print(f'{argv[2]}:{argv[1]} -> {argv[0]}: ' + ('FAIL' if found else 'ok'))
  return 1 if found else 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
