#!/usr/bin/env python3
"""Fit a car's rack map (honda_eps_rack_map.RackMapTable) against its VSA yaw sensor, the Clarity method.

Every moving frame, wheel angle shifted by the wheel->yaw lag, gives y = lin_rad / (L * k_eff) = R(theta), where lin
is the firmware VGR (A table) linear angle of the physical wheel angle and k_eff = k (1 - sf v^2) - g sf roll with
k = yaw / v from 0x94. sf comes from the speed dependence of y inside each wheel-angle band (it is the value that
makes R the same at every speed); R per band is the mean of the left and right medians, so an angle offset cancels.
Then held-out by route: how well the fitted map, and the car's current road curve, predict the measured curvature.

  fit_rack_map.py --car HONDA_CIVIC_BOSCH --vgr civic_tba_c020 --bus 1 --scale 0.244 '<route>/rlog*' ...
"""
import argparse
import bz2
import ast
import os
import glob
import re

import numpy as np
import zstandard as zstd

from openpilot.cereal import log
from opendbc.car.honda.steer_ratio import HONDA_VGR_INVERSE_BY_PROFILE
from opendbc.car.honda.values import CAR
from opendbc.car.honda.yaw_rate import RIGHT_LOSS_BP
from openpilot.selfdrive.controls.lib.honda_eps_car_learner import RackMapFit, rack_samples
from openpilot.selfdrive.controls.lib.honda_eps_rack_map import GRAVITY

LATERAL_COMMON = os.path.join(os.path.dirname(__file__), '..', '..', 'selfdrive', 'controls', 'lib', 'honda_lateral_common.py')


def road_curves():
  """The road steer-ratio curves (honda_lateral_common.HONDA_SR_CURVE_BY_FP), read from the source so the tool
  runs without the device's compiled modules."""
  env = {}
  for node in ast.parse(open(LATERAL_COMMON).read()).body:
    if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
      try:
        exec(compile(ast.Module([node], []), LATERAL_COMMON, 'exec'), {}, env)
      except Exception:
        pass
  return env.get('HONDA_SR_CURVE_BY_FP', {})


def seg(p):
  m = re.search(r'(?:rlog_|--)(\d+)(?:\.zst|\.bz2|/rlog)', p)
  return int(m.group(1)) if m else 0


def read_route(pattern, bus):
  st = {'y': np.nan, 'off': 0.0, 'roll': 0.0}
  rows = []
  for p in sorted({f for g in pattern.split(',') for f in glob.glob(g)}, key=seg):
    raw = bz2.decompress(open(p, 'rb').read()) if p.endswith('.bz2') else zstd.ZstdDecompressor().stream_reader(open(p, 'rb').read()).read()
    try:
      for e in log.Event.read_multiple_bytes(raw):
        w = e.which()
        if w == 'can':
          for m in e.can:
            if m.src == bus and m.address == 0x94:
              st['y'] = (m.dat[0] << 2) | (m.dat[1] >> 6)
        elif w == 'vehicleParameters':
          st['off'], st['roll'] = e.vehicleParameters.angleOffsetDeg, e.vehicleParameters.roll
        elif w == 'carState':
          c = e.carState
          rows.append((e.logMonoTime * 1e-9, c.vEgo, c.aEgo, c.steeringAngleDeg, c.steeringRateDeg, st['y'], st['off'], st['roll']))
    except Exception:
      pass
  return dict(zip(['t', 'v', 'a', 'angle', 'rate', 'y', 'off', 'roll'], np.array(rows, float).T, strict=True))


def samples(d, scale, right):
  t, v = d['t'], d['v']
  still = np.convolve((v < 0.01).astype(float), np.ones(100) / 100, 'same') > 0.999
  ok = np.isfinite(d['y'])
  zero = float(np.mean(d['y'][still & ok])) if (still & ok).sum() > 300 else 512.0
  counts = d['y'] - zero
  ramp = np.clip((counts - RIGHT_LOSS_BP[0]) / (RIGHT_LOSS_BP[1] - RIGHT_LOSS_BP[0]), 0.0, 1.0)
  yaw = -np.radians(counts * scale + right * ramp)            # clockwise-positive decode -> left-positive like the wheel
  idx, angle, k = rack_samples(t, v, d['a'], d['rate'], d['angle'] - d['off'], np.where(ok, yaw, np.nan), d['roll'])
  return zero, np.c_[v[idx], angle[idx], k[idx], d['roll'][idx]]


class Fit(RackMapFit):
  """The learner's fit (it is the same code on the device), plus the road curve it is scored against here."""
  def predict_curve(self, D, curve, sf_vm=-0.00061):
    v, th, k, ro = D.T
    sr = np.interp(np.abs(th), *curve)
    return (np.radians(th) / (sr * self.L) + GRAVITY * sf_vm * ro) / (1 - sf_vm * v ** 2)


def score(D, pred, label):
  v, th, k = D[:, 0], D[:, 1], D[:, 2]
  row = []
  for a0, a1 in ((3, 20), (20, 70), (70, 150), (150, 450)):
    for v0, v1 in ((2.5, 9), (9, 40)):
      m = (np.abs(th) >= a0) & (np.abs(th) < a1) & (v >= v0) & (v < v1)
      row.append(f'{np.median(k[m] / pred[m]):.3f}' if m.sum() > 100 else '  -  ')
  print(f'  {label:22s} ' + ' '.join(f'{x:>6s}' for x in row))


def main():
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  ap.add_argument('--car', required=True, help='fingerprint, for its current road curve and wheelbase')
  ap.add_argument('--vgr', required=True, help='VGR profile (steer_ratio.HONDA_VGR_INVERSE_BY_PROFILE key)')
  ap.add_argument('--bus', type=int, required=True)
  ap.add_argument('--scale', type=float, required=True, help='deg/s per 0x94 count (GPS-checked)')
  ap.add_argument('--right', type=float, default=0.0, help='clockwise correction, deg/s')
  ap.add_argument('--wheelbase', type=float, default=None)
  ap.add_argument('routes', nargs='+', help='rlog glob per route, comma-separated globs allowed (quote it)')
  a = ap.parse_args()
  wheelbase = a.wheelbase or CAR(a.car).config.specs.wheelbase
  fit = Fit(HONDA_VGR_INVERSE_BY_PROFILE[a.vgr], wheelbase)
  per = []
  for r in a.routes:
    zero, D = samples(read_route(r, a.bus), a.scale, a.right)
    print(f'{r}: zero {zero:.1f}, {len(D) / 20:.0f} s moving at >= 3 deg', flush=True)
    per.append(D)
  D = np.vstack(per)
  if len(D) / 20 < 300:
    raise SystemExit(f'only {len(D) / 20:.0f} s of turning at >= 3 deg: not enough to fit a rack map (the Insight fit had 440 s)')
  sf = fit.fit_sf(D)
  bp, val, n = fit.table(D, sf)
  print(f'\n{a.car} / {a.vgr}: wheelbase {wheelbase}, slip factor {sf} (from the speed dependence within each band)')
  print('RackMapTable(')
  print(f'  ratio_bp=({", ".join(f"{x:.1f}" for x in bp)}),')
  print(f'  ratio_v=({", ".join(f"{x:.2f}" for x in val)}),')
  print(f'  slip_factor={sf},')
  print(')')
  print('  samples per band (s):', [int(x / 20) for x in n])
  print('\nmeasured / predicted curvature, held out by route (1.000 = exact)')
  print('  ' + ' ' * 22 + ' '.join(f'{h:>6s}' for h in ('3-20s', '3-20f', '20-70s', '20-70f', '70-150s', '70-150f', '150+s', '150+f')))
  curve = road_curves().get(a.car)
  for i in range(len(per)) if len(per) > 1 else []:
    tr = np.vstack([p for j, p in enumerate(per) if j != i])
    sfi = fit.fit_sf(tr)
    bpi, vali, _ = fit.table(tr, sfi)
    score(per[i], fit.predict_map(per[i], sfi, bpi, vali), f'route {i}: rack map')
    if curve is not None:
      score(per[i], fit.predict_curve(per[i], curve), f'route {i}: road curve')
  print('  (s = 2.5-9 m/s, f = 9-40 m/s)')


if __name__ == '__main__':
  main()
