#!/usr/bin/env python3
"""Regenerate the Night Star port ledger table from git. Writes a fresh file: statuses start at todo, so merge by hand.

usage: make_ledger.py <output.md>   (PORT_MAIN_REPO: the checkout holding origin/vfn and the starpilot remote)
"""
import collections
import os
import re
import subprocess
import sys

REPO = os.environ.get("PORT_MAIN_REPO", os.path.expanduser("~/nrdr/openpilot"))
BASE = '249b03a3f5'
G = 'starpilot/SecretGoodStarPilot'
BR = {'vfn': 'origin/vfn', 'bosch': 'origin/ns-bosch-radar-testing'}

RULES = [  # (regex, area, default decision)
  (r'^tinygrad_repo/', 'vendored: tinygrad', 'DROP - take 7.0 tinygrad pin, rebuild models'),
  (r'jetlink', 'jetlink', 'DROP - 7.0 ships native Jetlink'),
  (r'^third_party/', 'vendored: third_party', 'REVIEW - likely take 7.0'),
  (r'^panda/board/obj|\.(so|a|o|pkl|elf|bin)$|libcommon|params_pyx', 'built artifact', 'REBUILD - Docker, never copy'),
  (r'locationd/models/generated', 'built artifact', 'REBUILD'),
  (r'^eps_tools/|^tune_report\.py|^tools/lateral/|^tools/replay/lib/radar_debug', 'tools', 'COPY - standalone tools'),
  (r'opendbc/safety/', 'panda safety', 'PORT - safety critical (Nidec hybrid brake)'),
  (r'opendbc_repo/opendbc/car/honda/(radar_interface|bosch)|radard|test_radard_bosch|honda_bosch_a_radar',
   'long: Bosch-A radar', 'RE-HOME into 7.0 bosch_a_radar.py'),
  (r'opendbc_repo/opendbc/car/honda/', 'Honda car layer', 'PORT onto 7.0 refactored Honda'),
  (r'opendbc_repo/opendbc/dbc/', 'DBC', 'REVIEW - regenerate from 7.0 sources'),
  (r'opendbc_repo/', 'opendbc other', 'REVIEW'),
  (r'latcontrol|honda_eps|honda_lateral|rack_map|neural_network_feedforward|nnff', 'lateral controller',
   'PORT - plug into lateral_controller_factory'),
  # nrdr_long matches vfn's nrdr_long_tune.py file name
  (r'blotv|longitudinal|long_mpc|longcontrol|nrdr_long|curve_speed|vcruise|starpilot_planner', 'longitudinal',
   'RE-HOME into openpilot/starpilot/longitudinal'),
  ('|'.join((r'selfdrive/modeld', 'model_compiler', 'compile_modeld', 'validate_model', 'model_rebuild', 'model_manager',
             'dmonitoringmodeld', r'selfdrive/assets/models', r'^models/')), 'modeld / models', 'REVIEW each vs 7.0 comma-master modeld'),
  (r'controlsd\.py|selfdrived|desire_helper|events\.py', 'controls core', 'PORT hooks into rewritten controlsd'),
  (r'params_keys\.h|cereal/|capnp', 'params / schema', 'PORT keys into 7.0 contracts; rebuild'),
  (r'selfdrive/ui/|system/ui/|selfdrive/assets/fonts', 'UI', 'REWRITE in 7.0 openpilot/starpilot/ui'),
  (r'the_galaxy|device_settings_layout', 'Galaxy', 'REWRITE against 7.0 galaxy'),
  (r'starpilot_variables|starpilot_utilities|starpilot_card', 'StarPilot glue', 'RE-HOME into 7.0 feature owners'),
  (r'system/manager|process_config|hardwared|system/hardware', 'system / manager', 'PORT selectively'),
  (r'^scripts/|^\.gitignore|^\.dockerignore|SConstruct|SConscript', 'build / scripts', 'REVIEW'),
  (r'\.md$|^docs/', 'docs', 'COPY ours'),
  (r'', 'other', 'REVIEW'),
]
DECISIONS = '; '.join((
  '**PORT** = carry the change onto the 7.0 file',
  '**RE-HOME** = the 6.x file is gone, the logic moves into a 7.0 owner module',
  '**REWRITE** = 7.0 replaced the subsystem, re-implement ours in its design',
  '**DROP** = 7.0 already covers it',
  '**REBUILD** = binary, regenerate via Docker',
  '**COPY** = standalone, copy as is',
  '**REVIEW** = undecided.',
))


def git(*args):
  return subprocess.run(['git', '-C', REPO, *args], capture_output=True, text=True).stdout


def classify(path):
  for rx, area, decision in RULES:
    if re.search(rx, path):
      return area, decision
  raise AssertionError('the last rule matches everything')


def main(out_path):
  sgsp = set(git('ls-tree', '-r', '--name-only', G).split('\n'))
  basefiles = set(git('ls-tree', '-r', '--name-only', BASE).split('\n'))
  files = collections.OrderedDict()
  for tag, ref in BR.items():
    for line in git('diff', '--numstat', '--no-renames', BASE, ref).splitlines():
      added, _, path = line.split('\t')
      entry = files.setdefault(path, {'add': 0, 'src': set()})
      if added != '-':
        entry['add'] = max(entry['add'], int(added))
      entry['src'].add(tag)

  rows = []
  for path, entry in files.items():
    area, decision = classify(path)
    dest = ('openpilot/' + path) if ('openpilot/' + path) in sgsp else (path if path in sgsp else '')
    rows.append((area, path, entry, dest, 'mod' if path in basefiles else 'new', decision))

  totals = collections.OrderedDict()
  for area, _, entry, _, _, decision in rows:
    total = totals.setdefault(area, [0, 0, set()])
    total[0] += 1
    total[1] += entry['add']
    total[2].add(decision)

  out = ['# Night Star → StarPilot 7.0 port ledger\n',
         f'Generated from `git diff {BASE}..{{origin/vfn, origin/ns-bosch-radar-testing}}` ({BASE} = the last StarPilot 6.x ' +
         f'merge base), mapped onto `{G}` @ `{git("rev-parse", "--short", G).strip()}`. Each row is one file we changed. ',
         'Status column is the work tracker: `todo` → `wip` → `done` / `dropped` (say why).\n',
         f'\nDecisions: {DECISIONS}\n',
         '\n## By area\n\n| Area | Files | Our + lines | Default decision |\n|---|---:|---:|---|\n']
  order = sorted(totals.items(), key=lambda kv: -kv[1][1])
  for area, (count, lines, decisions) in order:
    out.append(f'| {area} | {count} | {lines} | {"; ".join(sorted(decisions))} |\n')
  out.append('\n## Files\n')
  for area, _ in order:
    area_rows = [r for r in rows if r[0] == area]
    if area.startswith('vendored') or area in ('built artifact', 'jetlink'):
      out.append(f'\n### {area} ({len(area_rows)} files) — {area_rows[0][5]}\n\nCollapsed; see `git diff {BASE} <branch> --stat`.\n')
      continue
    out.append(f'\n### {area}\n\n| File | From | +lines | Ours was | 7.0 path | Decision | Status |\n|---|---|---:|---|---|---|---|\n')
    for _, path, entry, dest, kind, decision in sorted(area_rows, key=lambda r: -r[2]['add']):
      where = f'`{dest}`' if dest else '**gone**'
      out.append(f'| `{path}` | {"+".join(sorted(entry["src"]))} | {entry["add"]} | {kind} | {where} | {decision} | todo |\n')
  with open(out_path, 'w') as f:
    f.write(''.join(out))
  print(len(rows), 'rows')


if __name__ == '__main__':
  main(sys.argv[1])
