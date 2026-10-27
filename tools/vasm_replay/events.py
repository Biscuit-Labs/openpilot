"""For each radar adjacent lead lost close beside us: raw camera conf on that car-side vs time from the drop."""

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

IMG = {"left": 2, "right": 1}  # conf column: car left = image right (mirrored driver cam)
for f in sorted(glob.glob(os.path.join(dm, "conf_*.npy"))):
  name = os.path.basename(f)[len("conf_") : -4]
  conf = np.load(f)
  ex = json.load(open(f"{dm}/ex_{name}.json"))
  ft = np.array([r[1] for r in ex["frames"]])[: len(conf)]
  radar = ex["radar"]
  car = np.array(ex["car"])
  for si, side in enumerate(("left", "right")):
    b = 1 + 5 * si
    prev = None
    for row in radar:
      t = row[0]
      st, d, y, v, tid = row[b : b + 5]
      if prev and prev[0] and 0 <= prev[1] <= 15 and -prev[3] >= 0.5 and (not st or tid != prev[4]):
        t_drop = t
        v_ego = car[np.searchsorted(car[:, 0], t_drop).clip(max=len(car) - 1), 1]
        sel = (ft >= t_drop - 3) & (ft <= t_drop + 8)
        c = conf[sel, IMG[side]]
        tt = ft[sel] - t_drop
        above = tt[c >= 0.8]
        last_above = above.max() if len(above) else None
        cells = " ".join(f"{np.max(c[(tt >= a) & (tt < a + 1)]) if np.any((tt >= a) & (tt < a + 1)) else -1:.2f}" for a in range(-3, 8))
        print(
          f"{name:26s} {side:5s} t={t_drop:6.1f} vEgo={v_ego * 2.237:4.0f}mph lastd={prev[1]:5.1f} closing={-prev[3]:4.1f} "
          + f"lastConf>=.8 at {last_above if last_above is None else round(last_above, 1)}s | max/1s from -3: {cells}"
        )
      prev = (st, d, y, v, tid)
