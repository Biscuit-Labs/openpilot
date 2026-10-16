# NRDR → StarPilot 7.0 port

Branch `sp7-port` (worktree `~/nrdr/openpilot-sp7`), started 2026-10-16 from `starpilot/SecretGoodStarPilot` @ `89430a70da`.
7.0 is not released: it moves SGSP → `Dom` (dev/testing) → `StarPilot` (release). This branch gets us ready ahead of that.
`sp7-port` has **no upstream** on purpose. Never push it to the `starpilot` remote.

7.0 shares no git history with our branches, so this is a re-port by subsystem, not a rebase. [LEDGER.md](LEDGER.md) lists
every file `origin/vfn` and `origin/ns-bosch-radar-testing` changed since our last 6.x merge base (`249b03a3f5`), where it
lands in 7.0, the decision, and the status.

## Conventions

- **Paths.** The tree moved under `openpilot/`; module paths did not (`openpilot.selfdrive...` is unchanged). `opendbc_repo/`,
  `panda/`, `tinygrad_repo/` stay at the root.
- **cereal.** `from cereal import X` becomes `from openpilot.cereal import X`. `car` comes from `opendbc.car.structs`.
- **LatControl.update** in 7.0 takes eight arguments (no `calibrated_pose`, `model_data`, `starpilot_toggles`). Ported
  controllers keep those three as optional keywords.
- **Tests that wait on a later slice** stay in the file and fail with an obvious import/signature error. They are not
  skipped or xfailed. Only an import that would stop the whole module from collecting moves into the test that needs it.
- **Binaries** (`*.so`, `*.a`, panda objects, params): rebuild through the Docker laptop build. Never copy a built file
  from another checkout.
- **Ledger.** Update the Status column as work lands (`todo` → `wip` → `done` / `dropped: why`). `tools/nrdr_port/make_ledger.py`
  regenerates the table from git and would reset statuses, so write it to a new file and merge if it ever needs a refresh.

## Testing

`tools/nrdr_port/docker_pytest.sh -q <tests>` runs pytest in the larch64 container with a venv built from 7.0's own
`uv.lock` (setup in the script header). 7.0's `tools/laptop_device_build/Dockerfile` differs from ours (capnp 1.0.1,
pinned base, ARM panda toolchain). Our `starpilot-larch64-builder` image is fine for Python tests; build 7.0's image
before any native build.

Known environment failure, not ours: `openpilot/common/tests/test_params_fork_lock.py` (6 tests) needs 7.0's native
regression target built.

## Decisions log

| Date | Decision | Why |
|---|---|---|
| 10-16 | Drop our Jetlink port (`starpilot/jetlink_adapter`, `jetlink_repo`) | 7.0 ships Jetlink natively |
| 10-16 | Drop our vendored tinygrad changes; take 7.0's pin and rebuild models | Ours tracked comma's pin, and 7.0 is on comma master |
| 10-16 | `HondaFlags.VGR_*` keep their vfn bits (32768–524288) | Free in 7.0 |
| 10-16 | `StarPilotLateralState.eps*` fields must move from @8–@16 to @11–@19 | 7.0 uses @8–@10 (laneCentering, learningEvidence, learningApplication). Tools read by name; old routes keep old ordinals |
| 10-16 | `HondaFlags` bits differ: 7.0 has 1024=`HAS_BSM`, 16384=`GAS_INTERCEPTOR` | Our `ALLOW_MANUAL_TRANS` (1024) and `HYBRID_ALT_BRAKEHOLD` (16384) need new bits when the Honda layer is ported |
| 10-16 | **Open, safety:** `HondaSafetyFlags` allocation | Our `NIDEC_HYBRID=64` collides with 7.0's `BOSCH_CANFD_MVL=64`. 7.0 also has `AOL_BOSCH_LONG` and `GAS_INTERCEPTOR` both at 32. Resolve with the panda safety port, against panda's own flag table |

## Slices

| # | Slice | State |
|---|---|---|
| 1 | Honda EPS lateral modules land and their pure tests pass (`honda_eps_firmware_ff`, `honda_eps_rack_map`, `honda_lateral_common`, `latcontrol_honda_eps`, `steer_ratio`, VGR flags, `get_eps_modified_steering_pressed`, `PIDController` integrator scale/reset) | **done**; 309 pass, 66 wait on 2–3 |
| 2 | Honda interface: EPS image detection → `EPS_MODIFIED` + VGR flags, per-car PID tune, `get_params` toggles; params keys; capnp `eps*`; `create_lateral_controller` hook; controlsd telemetry copy | todo |
| 3 | `latcontrol_pid` modified-EPS path (banded scales, override fade, PTM RDX) on 7.0's stock PID; NNFF (7.0 removed it) | todo |
| 4 | Panda safety: Clarity Nidec-hybrid brake + safety flag allocation; panda rebuild | todo |
| 5 | controlsd hooks: rack-map curvature, turn-hold shaping, delay schedule, stopped-model guard | todo |
| 6 | Rest of the Honda car layer (learners, 0x94 yaw, carstate), rebased on 7.0's split Honda modules | todo |
| 7 | Settings UI + Galaxy in 7.0's feature-registration design | todo |
| 8 | Longitudinal: Bosch-A fixes into `bosch_a_radar.py`, BLoT, MLT, close-lead cap | todo |
| 9 | modeld extras: C3X→C4 reprojection, Chestnut fallback/NaN capture, per-model warps | todo |
| 10 | Tools (`tools/lateral`, `eps_tools`, radar debug), docs | todo |
