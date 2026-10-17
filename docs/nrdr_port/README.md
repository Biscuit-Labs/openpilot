# NRDR → StarPilot 7.0 port

Branch `sp7-port` (worktree `~/nrdr/openpilot-sp7`), started 2026-10-16 from `starpilot/SecretGoodStarPilot` @ `89430a70da`.
7.0 is not released: it moves SGSP → `Dom` (dev/testing) → `StarPilot` (release). This branch gets us ready ahead of that.
`sp7-port` tracks `origin/sp7-port` (our fork). Never push it to the `starpilot` remote.

`sp7-port` starts from **one snapshot commit** of the 7.0 tree (`e2d325132e`), not 7.0's history: that history
references ~5.3 GB of comma-master LFS models GitHub would demand in our fork's LFS store. The full-history version is
the local branch `sp7-port-history`. To take a newer 7.0, apply `git diff 89430a70da <new SecretGoodStarPilot>` onto
`sp7-port` as one "StarPilot 7.0 sync" commit and record the new base hash here.

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

Baseline as of slice 3 (honda car tests + controls tests + car interfaces + params): 2204 pass, **30 fail, and all 30 also
fail on pristine 7.0** (27 `stock_intent` `standard_active`, `test_stock_aol`, `test_adjacent_radar_schema` schema-policy
drift, `test_leads::test_radar_fault` params path). Anything beyond those 30 is ours.

## Decisions log

| Date | Decision | Why |
|---|---|---|
| 10-16 | Drop our Jetlink port (`starpilot/jetlink_adapter`, `jetlink_repo`) | 7.0 ships Jetlink natively |
| 10-16 | Drop our vendored tinygrad changes; take 7.0's pin and rebuild models | Ours tracked comma's pin, and 7.0 is on comma master |
| 10-16 | `HondaFlags.VGR_*` keep their vfn bits (32768–524288) | Free in 7.0 |
| 10-16 | `StarPilotLateralState.eps*` fields must move from @8–@16 to @11–@19 | 7.0 uses @8–@10 (laneCentering, learningEvidence, learningApplication). Tools read by name; old routes keep old ordinals |
| 10-16 | `HondaFlags` bits differ: 7.0 has 1024=`HAS_BSM`, 16384=`GAS_INTERCEPTOR` | Our `ALLOW_MANUAL_TRANS` (1024) and `HYBRID_ALT_BRAKEHOLD` (16384) need new bits when the Honda layer is ported |
| 10-16 | Keep 7.0's exact-image `MODIFIED_EPS_FW` allow-list (unknown comma image → dashcam) and add our fleet: Civic `TEG,A010`; Civic Bosch `TBA,C020`, `TBA,C120`; CR-V 5G `TLA,A220`; Insight `TXM,A040`; RDX 3G / MMR `TJB,A220` | Safer than vfn's "any comma = modified"; without these entries 7.0 makes those cars dashcam-only. Fingerprints gain `TBA,C120` and `TLA,A220` as on vfn |
| 10-16 | Modified-EPS command maps live in `CarControllerParams` (7.0 has no `CP.lateralParams` for Honda); ours replace 7.0's piecewise Civic (8000 knee) and CR-V (10000 knee) maps with vfn's linear-max ones | `eps_firmware_calibration` now checks `CarControllerParams(CP).STEER_LOOKUP`; the old `lateralParams` check would have silently never engaged |
| 10-16 | Modified-EPS PID tune: one `_nrdr_modified_eps_tune` helper (four-point 25 mph handoff) for Clarity, Civic, Civic Bosch, CR-V 5G, Insight, PTM RDX | Same values and same override order as vfn (autoResumeSng/minEnableSpeed are recomputed at the end, as on vfn) |
| 10-16 | **Open:** stock (unmodified) RDX 3G keeps 7.0's PID 0.2/0.06 | Our PTM commit 7954615283 moved the stock RDX 3G to the torque controller; that is a change to a non-fleet car, so it was not carried silently |
| 10-16 | PTM RDX 3G MMR on stock ACC gets 7.0's 70 km/h minSteerSpeed from `apply_factory_profile` | vfn's branch order skipped it; the radar filtering steering below 70 km/h is physical |
| 10-16 | Every NRDR `HondaFlags` bit must be added to `stock_aol.qualified()`'s detected set | It rejects any flag it does not know; the VGR bits silently disabled AOL on the modified Clarity until added |
| 10-16 | Fixed a 7.0 bug: `ACURA_RDX_3G_MMR` assigned `dashcamOnly = is_release`, clearing the unrecognized-modified-EPS dashcam | Worth reporting upstream |
| 10-16 | `liveParameters` is `vehicleParameters` (`log.VehicleParameters`) in 7.0 | Same fields our controller reads |
| 10-17 | **NNFF is dropped** (7.0 removed it; user call). The Clarity NNFF hybrid (`NrdrClarityHybrid`) goes with it | Modified-EPS Hondas steer through LatControlHondaEps or LatControlHondaModifiedPID |
| 10-17 | Our modified-EPS PID path lives in `latcontrol_honda_modified_pid.py` (`LatControlHondaModifiedPID`, subclass of 7.0's `LatControlPID`), picked by the factory for a modified-EPS Honda without an EPS firmware calibration. 7.0's `latcontrol_pid.py` is untouched | Keeps 7.0 syncs clean and every non-fleet car on 7.0's stock PID |
| 10-17 | Stock-EPS Clarity / Civic Bosch / CR-V 5G / Insight no longer get the road-measured steer-ratio curve | On vfn LatControlPID applied it to them too; non-fleet cars keep 7.0's behavior (same principle as the stock RDX) |
| 10-17 | Not carried from vfn's LatControlPID: StarPilot 6.x `latcontrol_vehicle_tunes` (Subaru Impreza, RAV4 TSS2, **CR-V 5G output shaping**), the Civic Bosch testing ground, `starpilot_toggles` kp/ki scales | firestar's 6.x code that 7.0 removed. **Open for the CR-V owner:** on vfn the 6.x CR-V 5G low-speed centre-reversal damping also shaped the *modified* CR-V's output |
| 10-17 | `Lat{P,I,F}Scale{LowSpeed,Standard,Highway}` params added (percent; I defaults 20/100/0) | Same keys, defaults and scaling as vfn |
| 10-16 | **Open, safety:** `HondaSafetyFlags` allocation | Our `NIDEC_HYBRID=64` collides with 7.0's `BOSCH_CANFD_MVL=64`. 7.0 also has `AOL_BOSCH_LONG` and `GAS_INTERCEPTOR` both at 32. Resolve with the panda safety port, against panda's own flag table |

## Slices

| # | Slice | State |
|---|---|---|
| 1 | Honda EPS lateral modules land and their pure tests pass (`honda_eps_firmware_ff`, `honda_eps_rack_map`, `honda_lateral_common`, `latcontrol_honda_eps`, `steer_ratio`, VGR flags, `get_eps_modified_steering_pressed`, `PIDController` integrator scale/reset) | **done** |
| 2 | Honda interface: EPS image allow-list + VGR flags, per-car PID tune, command maps; params keys; capnp `eps*`; `create_lateral_controller` hook; controlsd telemetry copy | **done** (params lib rebuild pending) |
| 3 | Modified-EPS PID path (banded kf/scales, VGR/road-curve target, rate limit, press detector, override fade, output LPF) as `LatControlHondaModifiedPID`; NNFF dropped | **done** |
| 4 | Panda safety: Clarity Nidec-hybrid brake + safety flag allocation; panda rebuild | todo |
| 5 | controlsd hooks: rack-map curvature, turn-hold shaping, delay schedule, stopped-model guard | todo |
| 6 | Rest of the Honda car layer (learners, 0x94 yaw, carstate), rebased on 7.0's split Honda modules | todo |
| 7 | Settings UI + Galaxy in 7.0's feature-registration design | todo |
| 8 | Longitudinal: Bosch-A fixes into `bosch_a_radar.py`, BLoT, MLT, close-lead cap | todo |
| 9 | modeld extras: C3X→C4 reprojection, Chestnut fallback/NaN capture, per-model warps | todo |
| 10 | Tools (`tools/lateral`, `eps_tools`, radar debug), docs | todo |
