"""Raw V-ASM model confidence for BOTH image sides on every dcamera frame (the daemon only samples one side ~1 Hz)."""

import argparse
import glob
import json
import os
import av
import numpy as np
from openpilot.starpilot.system.adj_spot_monitor_vision_inference import VASMInference, V_ASM_MODEL_PATH

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dm", required=True, help="route data directory containing <route>/<segment> and ex_/conf_ artifacts")
args = parser.parse_args()
dm = os.path.abspath(args.dm)
if not os.path.isdir(dm):
  parser.error("--dm must name an existing route data directory")

for d in sorted(glob.glob(os.path.join(dm, "*", "*"))):
  name = os.path.relpath(d, dm).replace(os.sep, "_")
  outp = f"{dm}/conf_{name}.npy"
  if os.path.exists(outp):
    continue
  ex = json.load(open(f"{dm}/ex_{name}.json"))
  inf = VASMInference(V_ASM_MODEL_PATH)
  assert inf.load(), inf.last_error
  inf.load_config(json.loads(ex["params"]["VASMAnnotationConfig"]))
  rows = []
  c = av.open(os.path.join(d, "dcamera.hevc"))
  for i, fr in enumerate(c.decode(video=0)):
    nv = fr.to_ndarray(format="nv12")  # (h*3/2, w)
    h, w = fr.height, fr.width
    inf._prepare_geometry(h, w)
    rows.append([i, inf._run_inference(nv, h, "left"), inf._run_inference(nv, h, "right")])
    if i == 0:
      print(name, w, h, inf.bboxes["left"], inf.bboxes["right"], flush=True)
  np.save(outp, np.array(rows, dtype=np.float32))
  print(name, len(rows), flush=True)
