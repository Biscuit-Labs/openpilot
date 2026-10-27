"""Run the real D-118 PassHold on rlog radar; compare with per-frame camera truth (conf>=0.8) on the same car side."""

import argparse
import glob
import json
import os
import numpy as np
from openpilot.starpilot.common.vasm_assist import AdjacentLead, PassHold

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dm", required=True, help="route data directory containing <route>/<segment> and ex_/conf_ artifacts")
args = parser.parse_args()
dm = os.path.abspath(args.dm)
if not os.path.isdir(dm):
  parser.error("--dm must name an existing route data directory")

IMG = {"left": 2, "right": 1}
tot = {"holds": 0, "hold_s": 0.0, "cam_during_or_after": 0, "gap_bridged": []}
for f in sorted(glob.glob(os.path.join(dm, "conf_*.npy"))):
  name = os.path.basename(f)[len("conf_") : -4]
  conf = np.load(f)
  ex = json.load(open(f"{dm}/ex_{name}.json"))
  ft = np.array([r[1] for r in ex["frames"]])[: len(conf)]
  ph = PassHold()
  on = {"left": None, "right": None}
  for row in ex["radar"]:
    t = row[0]
    for si, side in enumerate(("left", "right")):
      st, d, y, v, tid = row[1 + 5 * si : 6 + 5 * si]
      h = ph.update(side, AdjacentLead(bool(st), d, v, tid) if st else None, t)
      if h and on[side] is None:
        on[side] = t
      if not h and on[side] is not None:
        a, b = on[side], t
        on[side] = None
        c = conf[:, IMG[side]]
        sel = (ft >= a) & (ft <= b + 1.0)
        cam_t = ft[sel][c[sel] >= 0.8]
        first = cam_t[0] - a if len(cam_t) else None
        tot["holds"] += 1
        tot["hold_s"] += b - a
        tot["cam_during_or_after"] += first is not None
        first_s = f"+{first:.1f}s" if first is not None else "NEVER"
        last_s = f", last {b - cam_t[-1]:.1f}s before hold end" if len(cam_t) else ""
        print(f"{name:26s} car{side:5s} hold {a:7.1f}..{b:7.1f} ({b - a:3.1f}s) camera>=.8 first at {first_s}{last_s}")
print(tot["holds"], "holds", round(tot["hold_s"], 1), "s; confirmed by camera:", tot["cam_during_or_after"])
