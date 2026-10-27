"""Vehicles overtaking us: radar adjacent track first seen at dRel<20 with vRel>=0. Camera conf on that side around it."""

import argparse
import glob
import json
import os
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dm", required=True, help="route data directory containing <route>/<segment> and ex_/conf_ artifacts")
args = parser.parse_args()
dm = os.path.abspath(args.dm)
if not os.path.isdir(dm):
  parser.error("--dm must name an existing route data directory")

IMG = {"left": 2, "right": 1}
for f in sorted(glob.glob(os.path.join(dm, "conf_*.npy"))):
  name = os.path.basename(f)[len("conf_") : -4]
  conf = np.load(f)
  ex = json.load(open(f"{dm}/ex_{name}.json"))
  ft = np.array([r[1] for r in ex["frames"]])[: len(conf)]
  for si, side in enumerate(("left", "right")):
    b = 1 + 5 * si
    seen = set()
    for row in ex["radar"]:
      t = row[0]
      st, d, y, v, tid = row[b : b + 5]
      if not st or tid in seen:
        continue
      seen.add(tid)
      if d < 20 and v >= -0.5:
        sel = (ft >= t - 4) & (ft <= t + 8)
        c = conf[sel, IMG[side]]
        tt = ft[sel] - t
        cells = " ".join(f"{np.max(c[(tt >= a) & (tt < a + 1)]) if np.any((tt >= a) & (tt < a + 1)) else -1:.2f}" for a in range(-4, 8))
        trk = [(r[0] - t, r[b + 1], r[b + 3]) for r in ex["radar"] if r[b + 4] == tid and r[b]]
        print(f"{name:26s} car{side:5s} t={t:7.1f} first d={d:5.1f} v={v:+.1f} tid={tid} lasts {trk[-1][0]:4.1f}s to d={trk[-1][1]:5.1f} | -4..+8: {cells}")
