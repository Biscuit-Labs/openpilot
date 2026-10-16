import subprocess, sys, collections, re
REPO = __import__("os").environ.get("NRDR_MAIN_REPO", __import__("os").path.expanduser("~/nrdr/openpilot"))
BASE = '249b03a3f5'
G = 'starpilot/SecretGoodStarPilot'
BR = {'vfn': 'origin/vfn', 'bosch': 'origin/ns-bosch-radar-testing'}
def git(*a): return subprocess.run(['git', '-C', REPO, *a], capture_output=True, text=True).stdout
sgsp = set(git('ls-tree', '-r', '--name-only', G).split('\n'))
files = collections.OrderedDict()
for tag, ref in BR.items():
  for line in git('diff', '--numstat', '--no-renames', BASE, ref).splitlines():
    a, d, p = line.split('\t')
    e = files.setdefault(p, {'add': 0, 'src': set(), 'bin': a == '-'})
    if a != '-': e['add'] = max(e['add'], int(a))
    e['src'].add(tag)
basefiles = set(git('ls-tree', '-r', '--name-only', BASE).split('\n'))
RULES = [  # (regex, area, default decision)
  (r'^tinygrad_repo/', 'vendored: tinygrad', 'DROP - take 7.0 tinygrad pin, rebuild models'),
  (r'jetlink', 'jetlink', 'DROP - 7.0 ships native Jetlink'),
  (r'^third_party/', 'vendored: third_party', 'REVIEW - likely take 7.0'),
  (r'^panda/board/obj|\.(so|a|o|pkl|elf|bin)$|libcommon|params_pyx', 'built artifact', 'REBUILD - Docker, never copy'),
  (r'locationd/models/generated', 'built artifact', 'REBUILD'),
  (r'^eps_tools/|^tune_report\.py|^tools/lateral/|^tools/replay/lib/radar_debug', 'tools', 'COPY - standalone tools'),
  (r'opendbc/safety/', 'panda safety', 'PORT - safety critical (Nidec hybrid brake)'),
  (r'opendbc_repo/opendbc/car/honda/(radar_interface|bosch)|radard|test_radard_bosch|honda_bosch_a_radar', 'long: Bosch-A radar', 'RE-HOME into 7.0 bosch_a_radar.py'),
  (r'opendbc_repo/opendbc/car/honda/', 'Honda car layer', 'PORT onto 7.0 refactored Honda'),
  (r'opendbc_repo/opendbc/dbc/', 'DBC', 'REVIEW - regenerate from 7.0 sources'),
  (r'opendbc_repo/', 'opendbc other', 'REVIEW'),
  (r'latcontrol|honda_eps|honda_lateral|rack_map|neural_network_feedforward|nnff', 'lateral controller', 'PORT - plug into lateral_controller_factory'),
  (r'blotv|longitudinal|long_mpc|longcontrol|nrdr_long|curve_speed|vcruise|starpilot_planner', 'longitudinal', 'RE-HOME into openpilot/starpilot/longitudinal'),
  (r'selfdrive/modeld|model_compiler|compile_modeld|validate_model|model_rebuild|model_manager|dmonitoringmodeld|selfdrive/assets/models|^models/', 'modeld / models', 'REVIEW each vs 7.0 comma-master modeld'),
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
def classify(p):
  for rx, area, dec in RULES:
    if re.search(rx, p): return area, dec
rows = []
for p, e in files.items():
  area, dec = classify(p)
  dest = ('openpilot/' + p) if ('openpilot/' + p) in sgsp else (p if p in sgsp else '')
  kind = 'mod' if p in basefiles else 'new'
  rows.append((area, p, e, dest, kind, dec))
area_tot = collections.OrderedDict()
for area, p, e, dest, kind, dec in rows:
  t = area_tot.setdefault(area, [0, 0, set()]); t[0] += 1; t[1] += e['add']; t[2].add(dec)
out = []
w = out.append
w('# NRDR → StarPilot 7.0 port ledger\n')
w('Generated 2026-10-16 from `git diff 249b03a3f5..{origin/vfn, origin/ns-bosch-radar-testing}` (249b03a3f5 = our last StarPilot 6.x merge base), ')
w(f'mapped onto `{G}` @ `{git("rev-parse", "--short", G).strip()}`. Each row is one file we changed. ')
w('Status column is the work tracker: `todo` → `wip` → `done` / `dropped` (say why).\n')
w('\nDecisions: **PORT** = carry the change onto the 7.0 file; **RE-HOME** = the 6.x file is gone, the logic moves into a 7.0 owner module; **REWRITE** = 7.0 replaced the subsystem, re-implement ours in its design; **DROP** = 7.0 already covers it; **REBUILD** = binary, regenerate via Docker; **COPY** = standalone, copy as is; **REVIEW** = undecided.\n')
w('\n## By area\n\n| Area | Files | Our + lines | Default decision |\n|---|---:|---:|---|\n')
for area, (n, l, decs) in sorted(area_tot.items(), key=lambda kv: -kv[1][1]):
  w(f'| {area} | {n} | {l} | {"; ".join(sorted(decs))} |\n')
w('\n## Files\n')
order = [a for a, _ in sorted(area_tot.items(), key=lambda kv: -kv[1][1])]
for area in order:
  rs = [r for r in rows if r[0] == area]
  if area.startswith('vendored') or area == 'built artifact' or area == 'jetlink':
    w(f'\n### {area} ({len(rs)} files) — {rs[0][5]}\n\nCollapsed; see `git diff {BASE} <branch> --stat`.\n')
    continue
  w(f'\n### {area}\n\n| File | From | +lines | Ours was | 7.0 path | Decision | Status |\n|---|---|---:|---|---|---|---|\n')
  for _, p, e, dest, kind, dec in sorted(rs, key=lambda r: -r[2]['add']):
    src = '+'.join(sorted(e['src']))
    w(f'| `{p}` | {src} | {e["add"]} | {kind} | {("`"+dest+"`") if dest else "**gone**"} | {dec} | todo |\n')
open(sys.argv[1], 'w').write(''.join(out))
print(len(rows), 'rows')
