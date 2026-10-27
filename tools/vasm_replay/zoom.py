import json
import os
import argparse
import av
import cv2
import numpy as np
from openpilot.starpilot.system.adj_spot_monitor_vision_inference import VASMInference, V_ASM_MODEL_PATH

parser = argparse.ArgumentParser(description="Make a V-ASM crop contact sheet for an explicit route data directory.")
parser.add_argument("--dm", required=True, help="route data directory containing ex_/conf_ artifacts")
parser.add_argument("--out", required=True, help="output contact-sheet image filename")
parser.add_argument("name", help="<full route ID>_<segment>")
parser.add_argument("side", choices=("left", "right"), help="image side, opposite to the car side")
parser.add_argument("t0", type=float)
parser.add_argument("t1", type=float)
parser.add_argument("step", type=int)
args = parser.parse_args()
if args.step <= 0 or args.t1 < args.t0:
  parser.error("step must be positive and t1 must be at least t0")
dm = os.path.abspath(args.dm)
name, side, t_a, t_b, step = args.name, args.side, args.t0, args.t1, args.step
seg = name.rsplit("_", 1)
d = f"{dm}/{seg[0]}/{seg[1]}"
conf = np.load(f"{dm}/conf_{name}.npy")
ex = json.load(open(f"{dm}/ex_{name}.json"))
ft = [r[1] for r in ex["frames"]]
inf = VASMInference(V_ASM_MODEL_PATH)
inf.load()
inf.load_config(json.loads(ex["params"]["VASMAnnotationConfig"]))
col = 1 if side == "left" else 2
tiles = []
for i, fr in enumerate(av.open(os.path.join(d, "dcamera.hevc")).decode(video=0)):
  if not (t_a <= ft[i] <= t_b) or i % step:
    continue
  rgb = fr.to_ndarray(format="rgb24")
  inf._prepare_geometry(fr.height, fr.width)
  x, y, w, h = inf.bboxes[side]
  crop = np.ascontiguousarray(cv2.resize(rgb[y : y + h, x : x + w], (240, int(240 * h / w)))[:, :, ::-1])
  c = conf[i, col]
  cv2.putText(crop, f"{ft[i]:.2f} {c:.2f}", (3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0) if c >= 0.8 else (0, 0, 255), 2)
  tiles.append(crop)
rows = [np.hstack(tiles[k : k + 8] + [np.zeros_like(tiles[0])] * (8 - len(tiles[k : k + 8]))) for k in range(0, len(tiles), 8)]
if not tiles:
  parser.error("no camera frames matched the requested time window and step")
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
if not cv2.imwrite(args.out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 70]):
  raise OSError(f"could not write contact sheet: {args.out}")
# radar on the car side for this window (img left = car right)
b = 6 if side == "left" else 1
for r in ex["radar"]:
  if t_a <= r[0] <= t_b and int(r[0] * 4) != int((r[0] - 0.05) * 4):
    print(f"{r[0]:.2f} st={r[b]} d={r[b + 1]} y={r[b + 2]} v={r[b + 3]} id={r[b + 4]}")
