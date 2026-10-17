# Night Star → StarPilot 7.0 port

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
- **Ledger.** Update the Status column as work lands (`todo` → `wip` → `done` / `dropped: why`). `tools/night_star_port/make_ledger.py`
  regenerates the table from git and would reset statuses, so write it to a new file and merge if it ever needs a refresh.

## Testing

`tools/night_star_port/docker_pytest.sh -q <tests>` runs pytest in the larch64 container with a venv built from 7.0's own
`uv.lock` (setup in the script header). 7.0's `tools/laptop_device_build/Dockerfile` differs from ours (capnp 1.0.1,
pinned base, ARM panda toolchain). Our `starpilot-larch64-builder` image is fine for Python tests; build 7.0's image
before any native build.

Known environment failure, not ours: `openpilot/common/tests/test_params_fork_lock.py` (6 tests) needs 7.0's native
regression target built.

Baseline (honda car + safety tests, controls, selfdrived, car interfaces, params, state migration, starpilot honda, FLM):
**36 fail, and all 36 also fail on pristine 7.0** (the 30 below plus 6 FLM `test_operation_owner` environment failures) (27 `stock_intent` `standard_active`, `test_stock_aol`, `test_adjacent_radar_schema` schema-policy
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
| 10-16 | Modified-EPS PID tune: one `_modified_eps_tune` helper (four-point 25 mph handoff) for Clarity, Civic, Civic Bosch, CR-V 5G, Insight, PTM RDX (N-BOX dropped 10-17) | Same values and same override order as vfn (autoResumeSng/minEnableSpeed are recomputed at the end, as on vfn) |
| 10-16 | **Open:** stock (unmodified) RDX 3G keeps 7.0's PID 0.2/0.06 | Our PTM commit 7954615283 moved the stock RDX 3G to the torque controller; that is a change to a non-fleet car, so it was not carried silently |
| 10-16 | PTM RDX 3G MMR on stock ACC gets 7.0's 70 km/h minSteerSpeed from `apply_factory_profile` | vfn's branch order skipped it; the radar filtering steering below 70 km/h is physical |
| 10-16 | Every port-added `HondaFlags` bit must be added to `stock_aol.qualified()`'s detected set | It rejects any flag it does not know; the VGR bits silently disabled AOL on the modified Clarity until added |
| 10-16 | Fixed a 7.0 bug: `ACURA_RDX_3G_MMR` assigned `dashcamOnly = is_release`, clearing the unrecognized-modified-EPS dashcam | Worth reporting upstream |
| 10-16 | `liveParameters` is `vehicleParameters` (`log.VehicleParameters`) in 7.0 | Same fields our controller reads |
| 10-17 | **NNFF is dropped** (7.0 removed it; user call). The Clarity NNFF hybrid (`NrdrClarityHybrid`) goes with it | Modified-EPS Hondas steer through LatControlHondaEps or LatControlHondaModifiedPID |
| 10-17 | Our modified-EPS PID path lives in `latcontrol_honda_modified_pid.py` (`LatControlHondaModifiedPID`, subclass of 7.0's `LatControlPID`), picked by the factory for a modified-EPS Honda without an EPS firmware calibration. 7.0's `latcontrol_pid.py` is untouched | Keeps 7.0 syncs clean and every non-fleet car on 7.0's stock PID |
| 10-17 | Stock-EPS Clarity / Civic Bosch / CR-V 5G / Insight no longer get the road-measured steer-ratio curve | On vfn LatControlPID applied it to them too; non-fleet cars keep 7.0's behavior (and see the geometry rule above) |
| 10-17 | Not carried from vfn's LatControlPID: StarPilot 6.x `latcontrol_vehicle_tunes` (Subaru Impreza, RAV4 TSS2, **CR-V 5G output shaping**), the Civic Bosch testing ground, `starpilot_toggles` kp/ki scales | firestar's 6.x code that 7.0 removed. **Open for the CR-V owner:** on vfn the 6.x CR-V 5G low-speed centre-reversal damping also shaped the *modified* CR-V's output |
| 10-17 | `Lat{P,I,F}Scale{LowSpeed,Standard,Highway}` params added (percent; I defaults 20/100/0) | Same keys, defaults and scaling as vfn |
| 10-17 | **Geometry rule (both controllers): measured rack map → the exact image's firmware VGR table → paramsd's fixed ratio.** The road-fit steer-ratio curves are not used (data kept in `honda_lateral_common.py` for tools); `HondaEpsFirmwareVgr` is registered but inert | User direction: everyone on LatControlHondaEps with rack maps; the PID fallback uses firmware VGR. Yaw validation had the road fit ~12% high at centre and the firmware A table within 2%. Changes CR-V A040/A220 and Civic Bosch C120 (road curve → their VGR tables); TGG-A120 and PTM RDX stay on paramsd's ratio |
| 10-17 | Insight `TXM,A040` steers with LatControlHondaEps by default (like the Clarity); still only on the exact modified image | User call |
| 10-17 | Calibrations synced to ns-bosch @ 9d8de58075 (Insight corrected PTM f3a6a124bd; TEG R6 shape 78eb039f43 and corrected PTM 9d8de58075) | vfn does not have these three yet |
| 10-17 | Params kept as on vfn until LatControlHondaModifiedPID is retired; then downsize | User call |
| 10-17 | Output LPF defaults **on**: `HondaTorqueOutputLowPassFilter` default "1" and an unset bool now reads as its default | vfn's manager seeded it on at first start; 7.0 has no seeding, so the port had it off. The Clarity runs it on with taus 0.07/0.05/0.01 (route 0000038c) |
| 10-17 | `Lat*Scale` defaults stay P 100/100/100, I 20/100/0 (params_keys), **not** vfn's manager seed (P 100/135/200, I 20/135/0) | The seed dates from 06-28, before the banding moved into interface.py (07-26); on a fresh vfn install it double-bands highway kp. A vfn bug |
| 10-17 | N-BOX modified tune dropped; Civic 2022 modified branch kept (inert until an image is on the allow-list) | User call / nothing to remove yet |
| 10-17 | "Linear-max" wording replaced by "modified-EPS command map" (output × the image's cap) | Naming |
| 10-17 | **Slice 6 (car layer):** every Honda on a recognized modified EPS steers through `opendbc/car/honda/modified_eps.py` in the car controller: the shared override detector, override fade (down/up, kept torque, LKAS during override), `HondaMinSteerSpeed`, and the stock steer rate limit made opt-in (`HondaSteerDeltaLimiter`). It replaces 7.0's Civic Bosch-only `ModifiedCivicSteering`, whose car-controller low-pass read as safety limiting and froze the integrator. Stock-EPS Hondas keep 7.0's path | vfn applied the override stage to every Honda; non-fleet cars keep 7.0 behavior. 7.0's `modified_civic_steering.py` stays (FLM replay helpers import it) but nothing steers through it; delete in the naming cleanup |
| 10-17 | Settings reach opendbc 7.0's way: `starpilot/car/honda/modified_eps.py` (`ModifiedEpsPreferences`, refreshed once a second) attached by `controller_extensions.configure_controller` to the car controller and car state; opendbc reads no Params | vfn imported openpilot `Params` into opendbc |
| 10-17 | `HondaDriverOverrideThreshold` (was `NrdrDriverOverrideThreshold`), modified EPS only, default **2000** (vfn 2400); the lane-change nudge still counts the stock 1200 on those cars (`DesireHelper(nudge_torque=)`, Honda-only, where vfn applied a raw 1200 to every brand). `HondaMinSteerSpeed` (was `NrdrMinSteerSpeed`). Both renamed and carried over | User calls. UI toggle for the threshold in slice 7 |
| 10-17 | VSA yaw decode (`yaw_rate.py`, `KINEMATICS.YAW_RATE`, `LONG_ACCEL` scale −0.049) on modified-EPS cars only | Reading KINEMATICS makes the parser require 0x94; it is confirmed on the fleet (Clarity, Civic Bosch, CR-V, Insight, TEG) but not on every stock car. In 7.0 only Ford reads `yawRate`, so for Hondas it is telemetry for tools/lateral |
| 10-17 | Not ported (slice 6): redneck cruise (7.0 removed it), the old Civic Bosch graded detector/filter, the static Clarity `HYBRID` flag (the Clarity sends 0x184, so 7.0 detects it; the Insight is detected the same way and only its ACC-fault message changes, as on vfn) | User calls / not needed |
| 10-17 | **No "NRDR" naming:** params, identifiers, modules (`honda_eps_settings.py`), folders (`docs/night_star_port`, `tools/night_star_port`), comments and commit messages ("night star port:") | User direction. Left on purpose: the old saved key names in the rename map (`NrdrLat*`, `NrdrDriverOverrideThreshold`, `NrdrMinSteerSpeed`; they are what is on disk), vfn file names in the ledger, and the `~/nrdr` checkout path |
| 10-17 | **Slice 5 (controlsd):** LatControlHondaEps cars measure curvature through their rack map and tell the model the calibration's delay schedule; no lateral while `modelV2` is not alive (route 000003bb); `steerSaturated` suppressed on modified-EPS Hondas | `steer_limited_by_safety` tied to `latActive` is already in 7.0 |
| 10-17 | **Not ported (slice 5):** model-action interpolation (`NrdrLatModelActionInterp`), the low-speed turn hold and its shaping (7.0's `ModelTurnAssist` is Ioniq-6-only, so our cars have no turn hold), the `NrdrLearn*` paramsd freeze toggles, the NNFF `torque_carparams` path | User calls. `desire_helper` `turn_stop_hold` is gone in 7.0 too; the lane-change nudge torque threshold waits on slice 6's override threshold |
| 10-17 | 7.0's `modified_civic_steering.py` **kept** (unused by the car controller) | FLM's projection format carries the old Civic filter state (a 7-field `shape`, validated on serialization) and its replay branch reads it; removing the module means redesigning that format. Our car controller always reports an empty shape, and FLM only learns on torque-domain controllers, so it is dead code for our cars |
| 10-17 | **Settings carry-over:** 7.0's first start archives every saved setting outside `OPERATIONAL_KEYS` and starts fresh. `starpilot/honda_eps_settings.py` adds the Honda EPS tuning keys to that set and, before it runs, renames vfn's older names (`NrdrLat{EpsFirmwareFF,UseFirmwareVgr,AngleRateLimit}`, `HondaTorqueLowPassFilter`, `HondaLpfTau*`) as vfn's manager does | Without it the Clarity would lose its LPF taus (0.07/0.05/0.01), fade-up 0.5 and rate limit 219 (still saved as `NrdrLatAngleRateLimit`) on the first 7.0 boot. All other StarPilot settings still start fresh, as 7.0 intends |
| 10-17 | **Nidec-hybrid brake (Clarity), slice 4.** Safety takes the larger of `COMPUTER_BRAKE` and `COMPUTER_BRAKE_HYBRID` on every Nidec (TX brake limit and stock-AEB forwarding), so there is **no `NIDEC_HYBRID` safety param** | Stock 7.0 would brake the Clarity on the wrong field (the 06-30 "no braking" bug). A new param bit would have had to thread 7.0's exact-word checks: the interceptor enables only on param 32/36, so the Clarity's 96 would have silently lost the pedal. Non-hybrids are unchanged (nothing else in those bits). Option A (vfn's bit 64) is the fallback if ever needed |
| 10-17 | `hondacan.create_brake_command(..., hybrid=)` writes `COMPUTER_BRAKE_HYBRID`/`BRAKE_PUMP_REQUEST_HYBRID` for `HondaFlags.HYBRID`; carstate reads the hybrid stock-AEB field, `blockPcmEnable` from brake hold, and `BRAKE_HOLD_HYBRID_ALT` (0x223) under new `HYBRID_ALT_BRAKEHOLD = 1048576` (16384 is 7.0's GAS_INTERCEPTOR) | vfn 5f5e384660 / 4eccd1a858. vfn's `car_specific` belowEngageSpeed is not needed: 7.0's `brakeHold` event already blocks an OP-long engage in brake hold |
| 10-17 | Panda app firmware rebuilt (DEBUG, debug-signed, as 7.0 builds it); bootstub and body binaries left as 7.0's | Only the version stamp changed in those |
| 10-17 | **Slice 7 defaults:** override fade-down 0 s and fade-up 0.5 s; output LPF always on, bands 0.07/0.05/0.01 (`HONDA_TORQUE_OUTPUT_LPF_TAU`). No settings rows for either | User call ("what works, works"); the Clarity's values. The keys stay registered until the params downsizing |
| 10-17 | **Night Star settings page** (`starpilot/ui/night_star_feature.py`, `FeaturePage.NIGHT_STAR`, linked from Driving Controls, Galaxy page `night_star`). Live onroad edits (`preferences`): angle rate limit (only on LatControlHondaEps), override threshold, min steer speed, torque during override, assist during override, steer rate limiter + up/down, seatbelt check. `HondaEpsController` shows only on a calibrated image that is not `default_on`, and is parked-only (read at startup). No fade, LPF or PID-trim rows. Tune report dropped | User calls. PID trims dropped instead of shown on the PID path: LatControlHondaModifiedPID is being retired once every PTM car has a calibration |
| 10-17 | `DisableSeatbeltCheck` (Night Star only): card clears `carState.seatbeltUnlatched` while on (`starpilot/car/seatbelt_check.py`), so 7.0's alert, AOL and longitudinal seatbelt gates all stand down; kept across the first start | vfn behavior, kept on purpose (user call) — unlike Brett's nightly, which keeps lateral but blocks gas/brake |
| 10-17 | **Konik only** (Night Star): `ConnectProvider` defaults to `konik`, comma cannot be selected (`provider.ALLOWED_PROVIDERS`), state from a comma build switches through 7.0's journaled switch. `connect/konik_adoption.py` carries a vfn device's Konik identity (KonikDongleId + the factory key Konik already trusts) into 7.0's provider state before the first-start migration | 7.0 makes Konik a new key, so the Clarity (aa72d9572459015c, ~11.9k Konik minutes) would have registered as a new device. Routes vfn left in `realdata_konik` do not upload from 7.0 (it records to `realdata`) |
| 10-17 | **Clean branch `sp7-clean`** = sp7-port + one commit that **deletes** the Night Star policy code: Konik-only + identity adoption (back to stock 7.0: comma, Konik selectable), the seatbelt toggle, the steer-saturated suppression; it never gets driver-monitoring timing changes. Everything that is car capability or safety stays. Rebase it onto sp7-port after each slice | User call, modeled on Brett's nrdr-clean (comma backend, stock DM, stock events); code removed outright rather than switched off |

## Slices

| # | Slice | State |
|---|---|---|
| 1 | Honda EPS lateral modules land and their pure tests pass (`honda_eps_firmware_ff`, `honda_eps_rack_map`, `honda_lateral_common`, `latcontrol_honda_eps`, `steer_ratio`, VGR flags, `get_eps_modified_steering_pressed`, `PIDController` integrator scale/reset) | **done** |
| 2 | Honda interface: EPS image allow-list + VGR flags, per-car PID tune, command maps; params keys; capnp `eps*`; `create_lateral_controller` hook; controlsd telemetry copy | **done** (params lib rebuild pending) |
| 3 | Modified-EPS PID path (banded kf/scales, VGR/road-curve target, rate limit, press detector, override fade, output LPF) as `LatControlHondaModifiedPID`; NNFF dropped | **done** |
| 4 | Clarity Nidec-hybrid brake: safety (larger brake field), brake command, car state, alt brake hold; panda rebuild | **done** |
| 5 | controlsd: rack-map curvature, delay schedule, stopped-model guard; steerSaturated suppression; settings carry-over | **done** |
| 6 | Car layer, lateral side: modified-EPS steering stage, override threshold, min steer speed, yaw decode | **done** (long-side carcontroller pieces are slice 8) |
| 7 | Settings UI + Galaxy in 7.0's feature-registration design (Night Star page), fixed defaults, seatbelt check, Konik only | **done** |
| 8 | Longitudinal: Bosch-A fixes into `bosch_a_radar.py`, BLoT, MLT, close-lead cap | todo |
| 9 | modeld extras: C3X→C4 reprojection, Chestnut fallback/NaN capture, per-model warps | todo |
| 10 | Tools (`tools/lateral`, `eps_tools`, radar debug), docs | todo |
