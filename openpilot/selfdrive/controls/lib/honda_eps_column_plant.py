"""The steering column behind an EPS firmware calibration, simulated: the command map, the firmware law with its
tracker-1 rate feedback, and the calibration's ColumnLoadModel. tools/lateral/eps_closed_loop.py replays drives through
it and the on-device car learner (honda_eps_car_learner) checks a fitted load against it, so both use this one copy.
Only numpy and the firmware law here.
"""
import math
from collections import deque

import numpy as np

from openpilot.selfdrive.controls.lib import honda_eps_firmware_ff as F

DT, SUB = 0.01, 20  # 100 Hz controller, 2 kHz plant
TRACKER_TAU = 0.0195  # s, tracker-1 at its Route-A / P-minus-5 setting (KB TRACKER1_TIMING.md)
# The Ridgeline's rate feedback filter instead: the 7/8 IIR in its 4 kHz motor task (1.9 ms) and the c6/c8 IIR in its 1 kHz
# control task (6.6 ms), FUN_0002e2b6 / FUN_00035fc8
TRACKER_TAU_BY_CALIBRATION = {"ridgeline_t6z_a110": 0.0085}
FITTED_FRICTION_WIDTH = 2.0  # deg/s, the Coulomb knee fit_column_load.py fits with
OPEN_LOOP_BAND = (0.6, 2.5)  # Hz
OPEN_LOOP_FRAMES = 2000


class Plant:
  """friction_width_v: the Coulomb knee at eps_ff.FRICTION_WIDTH_SPEED_BP when the load was fitted with a scheduled one."""
  def __init__(self, cal, j, sensor_delay, friction_width_v=None):
    self.cal, self.L, self.j = cal, cal.load, j
    self.trk = (DT / SUB) / (TRACKER_TAU_BY_CALIBRATION.get(cal.name, TRACKER_TAU) + DT / SUB)
    self.nd = int(round(sensor_delay / DT))
    self.friction_width_v = friction_width_v
    self.reset(0.0, 0.0)

  def reset(self, th, thd):
    self.th, self.thd = th, thd
    self.ref = F.firmware_r6(thd, th, self.cal)
    self.hist = deque([th] * self.nd)

  def frame(self, e4, v, roll):
    cal, L, h = self.cal, self.L, DT / SUB
    r5 = F.r5_from_output(-e4 / cal.e4_per_output, v, cal)
    kp = F.firmware_kp(r5, cal)
    g = 1.0 if cal.r6_angle_bp is None else float(np.interp(abs(self.th), cal.r6_angle_bp, cal.r6_angle_gain))
    k_ang, bias = L.k0 + L.k1 * v * v, L.bias + L.kroll * roll * v * v
    width = FITTED_FRICTION_WIDTH if self.friction_width_v is None else float(np.interp(v, F.FRICTION_WIDTH_SPEED_BP, self.friction_width_v))
    for _ in range(SUB):
      self.ref += self.trk * (max(min(cal.r6_per_deg_s * g * self.thd, F.R6_CLAMP), -F.R6_CLAMP) - self.ref)
      fw = F.firmware_law(r5, self.ref, kp, cal)
      self.thd += h * (fw - k_ang * self.th - L.c * self.thd - bias - L.friction * math.tanh(self.thd / width)) / self.j
      self.th += h * self.thd
    self.hist.append(self.th)
    return self.hist.popleft()


def band(x, lo, hi):
  X = np.fft.rfft(x - x.mean())
  f = np.fft.rfftfreq(len(x), DT)
  X[(f < lo) | (f > hi)] = 0
  return np.fft.irfft(X, len(x))


def open_loop_window(plant, e4, v, roll, angle, rate0):
  """(gain, correlation) of the simulated wheel on the measured one in OPEN_LOOP_BAND, the plant driven by the 0xE4
  that reached the firmware (already lagged) from the measured starting state."""
  plant.reset(float(angle[0]), float(rate0))
  y = np.array([plant.frame(float(e), float(s), float(r)) for e, s, r in zip(e4, v, roll, strict=True)])
  yb, mb = band(y, *OPEN_LOOP_BAND), band(np.asarray(angle, float), *OPEN_LOOP_BAND)
  return float(np.std(yb) / max(np.std(mb), 1e-6)), float(np.corrcoef(yb, mb)[0, 1])
