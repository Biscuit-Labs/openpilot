# ns-bosch-updated upstream integration review

As of: 2026-10-16. Static merge review and local unit/build checks only.
The owner selected James's `vfn` branch and PR incorporation only into their own fork.

| Source | Integrated source SHA |
| --- | --- |
| trung791997/openpilot, ns-bosch-radar-testing | `217688cc88c7e230e488555533db6992b94e1ded` |
| JamesL787/openpilot, vfn | `8715c7de4422163b8f686be1d60c6197072ef172` |
| zoompilot/jetlink, main | `491cf1ef8d6786ed51cf995e18fc8721389066c6` |
| VFN tinygrad pin | `d3f09c9bbd542fbfbe68c8569a1173550c408969` |

All three tips were fetched/queried again before finalizing; they were unchanged.
Every currently tracked model artifact matches VFN by Git blob ID. Eight old
standalone split vision/policy files already retired on this fork remain absent;
the native runtime loads the unified driving artifact and camera-specific warps,
not those obsolete split files.
Tinygrad's runtime package is byte-identical to VFN's; three extra-tool files receive
EOF whitespace cleanup only. See D-131–D-134 for integration decisions and exceptions.

## Pull requests

GitHub returned **zero open PRs** for RiskyBiscuit-arc/openpilot. Four open PRs in
JamesL787/openpilot were inspected as potential source changes. No writes were made there.

| PR | Reviewed head | Disposition for this fork |
| --- | --- | --- |
| [#8 — lateral fixes](https://github.com/JamesL787/openpilot/pull/8) | `b440094c9320be68f0ad48c9623526a76ac0f4df` | The later VFN PID resets on disengagement and bleeds through override fade. Keep that current controller; do not import the older experimental relative-freeze/asymmetry file knobs. |
| [#17 — Bosch-A radar and planner](https://github.com/JamesL787/openpilot/pull/17) | `c970f73f2a5ef9be546d53889dc1c1cdb7bec355` | U11 1/72, newborn points, leadOnpath, short action time, Accel Boost and related work are already present in later form. The newer Trung changes remain canonical. |
| [#18 — planner half](https://github.com/JamesL787/openpilot/pull/18) | `7a07025ef78760bf478ffe8a8e17d7a11983775a` | Same superseded planner lineage as #17; no separate merge needed. |
| [#19 — comma 4 JetLink warp](https://github.com/JamesL787/openpilot/pull/19) | `0fe0a9d9cd1e70fb13713f545ac039d34f154f8d` | Its pickle targets API 2/tinygrad f6fc4e3f. The integrated API 3/d3f09c9b stack uses modeld's native small_driving_warp files. Do not install this incompatible pickle. |

The previous local comma 4 warp had SHA-256 `8fb200a82823f1d69bd4278f6fd71edd17d3e48f1c5c0d04c6403f21b5957484`;
PR #19's was `fc51826cedbe3eee796b3d265cf2148a4a28fe97865ab9d704b58636548321be`.
They were compared by bytes, not filenames. Both old-format paths are retired by D-133.

## Boundaries

The A220 controller remains matched to the retained RWD `8f175250…` (D-122/D-133).
VFN's corrected A220 firmware reports the same ID and cannot be automatically
distinguished. This update neither flashes firmware nor selects that corrected curve.

The branch now requires a source build on the comma; the prebuilt marker is removed
because native schemas/parameter keys changed. Host-native binaries are not published.
The local build/tests do not validate QCOM GPU artifacts on hardware, physical USB
power behavior, real radar fusion timing, model handoffs, or closed-loop driving.

Final implementation SHA and test counts are recorded in STATUS.md item 271.
