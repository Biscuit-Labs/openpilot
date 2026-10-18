"""Radar point roles for the replay UI's top-down view (Night Star port, from ns-bosch-radar-testing).

A visualization of the published radarTracks and radarState only; it never touches radar or control code. On 7.0 the
leads are radarState.leadOne/leadTwo (starpilotRadarState's side leads are frozen, unpopulated fields), and a point's
measured flag is RadarPoint.deprecated.measured.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Indices into tools/replay/ui.py's top-down palette.
RADAR_PALETTE = {
  "leadOne": 1,    # red
  "leadTwo": 5,    # orange
  "measured": 2,   # green
  "estimated": 7,  # grey: the decoder coasted the point (not measured this sweep)
}
RADAR_ROLE_PRIORITY = ("leadOne", "leadTwo")


def _field(reader: Any, name: str, default: Any = None) -> Any:
  if reader is None:
    return default
  try:
    return getattr(reader, name)
  except (AttributeError, KeyError, TypeError):
    return default


def point_measured(point: Any) -> bool:
  return bool(_field(_field(point, "deprecated"), "measured", False))


def radar_track_roles(radar_state: Any = None) -> dict[int, tuple[str, ...]]:
  """Published lead roles keyed by the native radar track id."""
  roles: dict[int, list[str]] = {}
  for role in RADAR_ROLE_PRIORITY:
    lead = _field(radar_state, role)
    if not bool(_field(lead, "status", False)):
      continue
    try:
      track_id = int(_field(lead, "radarTrackId", -1))
    except (TypeError, ValueError):
      continue
    if track_id >= 0:
      roles.setdefault(track_id, []).append(role)
  return {track_id: tuple(track_roles) for track_id, track_roles in roles.items()}


def radar_track_style(track_id: int, measured: bool, roles: Mapping[int, Iterable[str]] | None = None) -> tuple[str, int]:
  """The display role and palette index for one point."""
  point_roles = set(roles.get(track_id, ())) if roles is not None else set()
  for role in RADAR_ROLE_PRIORITY:
    if role in point_roles:
      return role, RADAR_PALETTE[role]
  role = "measured" if measured else "estimated"
  return role, RADAR_PALETTE[role]


def radar_track_summary(points: Iterable[Any], roles: Mapping[int, Iterable[str]] | None = None) -> dict[str, Any]:
  """Counts for the sidebar: points, how many are measured, and which track ids hold each lead."""
  track_ids: list[int] = []
  measured = 0
  role_ids: dict[str, list[int]] = {role: [] for role in RADAR_ROLE_PRIORITY}
  for point in points or ():
    try:
      track_id = int(_field(point, "trackId", -1))
    except (TypeError, ValueError):
      track_id = -1
    if track_id >= 0:
      track_ids.append(track_id)
    measured += point_measured(point)
    for role in (roles or {}).get(track_id, ()):
      if role in role_ids and track_id not in role_ids[role]:
        role_ids[role].append(track_id)
  return {
    "count": len(track_ids),
    "measured": measured,
    "track_ids": tuple(sorted(track_ids)),
    "role_ids": {role: tuple(sorted(ids)) for role, ids in role_ids.items()},
  }
