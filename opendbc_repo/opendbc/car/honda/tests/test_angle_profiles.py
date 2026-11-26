import re
from pathlib import Path

import numpy as np

from opendbc.car.honda.angle_profiles import ANGLE_PROFILES, CAR_ROWS, OWN_GEOMETRY, PANDA_ROWS, own_angle_limit, vm_angle_limit

HONDA_H = Path(__file__).parents[3] / "safety" / "modes" / "honda.h"
SPEEDS = np.linspace(5., 40., 71)


def test_rows_match_panda():
  rows = re.findall(r"\{\.slip_factor = (-?[\d.]+), \.steer_ratio = ([\d.]+), \.wheelbase = ([\d.]+)\}", HONDA_H.read_text())
  assert 1 <= len(rows) <= 7
  assert sorted(PANDA_ROWS) == list(range(1, len(rows) + 1))
  for index, (slip, sr, wb) in enumerate(rows, start=1):
    row = PANDA_ROWS[index]
    assert row.index == index
    assert (row.slip_factor, row.steer_ratio, row.wheelbase) == (float(slip), float(sr), float(wb))


def test_every_platform_has_its_own_model_and_a_row():
  assert set(CAR_ROWS) == set(OWN_GEOMETRY) == set(ANGLE_PROFILES)
  assert set(CAR_ROWS.values()) == set(PANDA_ROWS)   # no unused rows


def test_shared_rows_never_looser_and_at_most_10_percent_tighter():
  for car, geometry in OWN_GEOMETRY.items():
    row = ANGLE_PROFILES[car]
    ratio = np.array([vm_angle_limit(v, row, accel=3.6) / own_angle_limit(v, geometry, accel=3.6) for v in SPEEDS])
    assert ratio.max() <= 1.0 + 1e-9, (car, ratio.max())
    assert ratio.min() >= 0.90, (car, ratio.min())


def test_eps_clamp_at_least_1_1_x_panda():
  # each EPS clamp is its own model at 4.0 m/s^2; panda is the row at 3.6
  for car, geometry in OWN_GEOMETRY.items():
    row = ANGLE_PROFILES[car]
    ratio = np.array([own_angle_limit(v, geometry) / vm_angle_limit(v, row) for v in SPEEDS])
    assert ratio.min() >= 1.1, (car, ratio.min())
