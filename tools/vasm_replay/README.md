# V-ASM driver-camera replay (D-118 evidence)

Replays the V-ASM model on every driver-camera frame of a route and compares it with radar adjacent leads.
Route data is never committed. Every script requires `--dm`, a directory containing
`<full route ID>/<segment>/{rlog.zst,dcamera.hevc}` and the derived `ex_*.json` / `conf_*.npy`
files. No script depends on another checkout or a fixed download location. Pass an existing route
data directory explicitly, or use ignored scratch space inside this repo, for example:

```bash
vasm_scratch="$PWD/scratch/vasm"
mkdir -p "$vasm_scratch/dm"
python tools/konik_fetch.py --route 'DONGLE|ROUTE' --out "$vasm_scratch/dm" --segments 30,31
python tools/konik_fetch.py --route 'DONGLE|ROUTE' --out "$vasm_scratch/dm" --segments 30,31 --dcameras
python tools/vasm_replay/rlog_extract.py --dm "$vasm_scratch/dm"
python tools/vasm_replay/conf_replay.py --dm "$vasm_scratch/dm"
python tools/vasm_replay/events.py --dm "$vasm_scratch/dm"
python tools/vasm_replay/daemon_sim.py --dm "$vasm_scratch/dm"
python tools/vasm_replay/hold_eval.py --dm "$vasm_scratch/dm"
```

Use the repo's built Python environment with `PYTHONPATH` configured as described in `STATUS.md`.
Camera replay additionally needs PyAV (`av`) and OpenCV. Before downloading to an existing shared
route folder, run `tools/prune_routes.py` on that folder and read its plan; only the owner's
explicit approval permits pruning with `--apply`. Pin routes needed for open analyses in `KEEP`.
Do not commit route data or generated crops.

| script | output |
|---|---|
| `rlog_extract.py` | `ex_<route>_<seg>.json`: V-ASM params from initData, driver frame times, radar adjacent leads, ego state |
| `conf_replay.py` | `conf_<route>_<seg>.npy`: raw model confidence, both image sides, every frame (~3 min/segment) |
| `events.py` | per pass event: where radar lost the car, and camera confidence per second around it |
| `daemon_sim.py` | the daemon's 1 s side alternation vs per-frame camera truth, with and without D-118 focus |
| `hold_eval.py` | the real `PassHold` on rlog radar, with each hold checked against the camera |
| `overtaken.py` | vehicles overtaking us: where radar first sees them, and camera confidence before that |
| `zoom.py --dm DIR --out IMAGE NAME IMGSIDE T0 T1 STEP` | contact sheet of crops with confidence, plus radar on that side |

The driver camera is mirrored, so image left is car right.
