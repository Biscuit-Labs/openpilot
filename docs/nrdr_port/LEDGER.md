# NRDR → StarPilot 7.0 port ledger
Generated 2026-10-16 from `git diff 249b03a3f5..{origin/vfn, origin/ns-bosch-radar-testing}` (249b03a3f5 = our last StarPilot 6.x merge base), mapped onto `starpilot/SecretGoodStarPilot` @ `89430a70da`. Each row is one file we changed. Status column is the work tracker: `todo` → `wip` → `done` / `dropped` (say why).

Decisions: **PORT** = carry the change onto the 7.0 file; **RE-HOME** = the 6.x file is gone, the logic moves into a 7.0 owner module; **REWRITE** = 7.0 replaced the subsystem, re-implement ours in its design; **DROP** = 7.0 already covers it; **REBUILD** = binary, regenerate via Docker; **COPY** = standalone, copy as is; **REVIEW** = undecided.

## By area

| Area | Files | Our + lines | Default decision |
|---|---:|---:|---|
| vendored: tinygrad | 630 | 46105 | DROP - take 7.0 tinygrad pin, rebuild models |
| jetlink | 72 | 15639 | DROP - 7.0 ships native Jetlink |
| lateral controller | 13 | 4660 | PORT - plug into lateral_controller_factory |
| modeld / models | 36 | 3598 | REVIEW each vs 7.0 comma-master modeld |
| tools | 35 | 3325 | COPY - standalone tools |
| Honda car layer | 12 | 2286 | PORT onto 7.0 refactored Honda |
| longitudinal | 15 | 1569 | RE-HOME into openpilot/starpilot/longitudinal |
| built artifact | 87 | 1368 | REBUILD; REBUILD - Docker, never copy |
| vendored: third_party | 10 | 1310 | REVIEW - likely take 7.0 |
| UI | 29 | 950 | REWRITE in 7.0 openpilot/starpilot/ui |
| long: Bosch-A radar | 4 | 831 | RE-HOME into 7.0 bosch_a_radar.py |
| Galaxy | 7 | 707 | REWRITE against 7.0 galaxy |
| other | 27 | 705 | REVIEW |
| build / scripts | 8 | 582 | REVIEW |
| controls core | 6 | 488 | PORT hooks into rewritten controlsd |
| docs | 4 | 461 | COPY ours |
| system / manager | 7 | 394 | PORT selectively |
| params / schema | 4 | 141 | PORT keys into 7.0 contracts; rebuild |
| DBC | 17 | 81 | REVIEW - regenerate from 7.0 sources |
| StarPilot glue | 5 | 81 | RE-HOME into 7.0 feature owners |
| panda safety | 2 | 27 | PORT - safety critical (Nidec hybrid brake) |
| opendbc other | 1 | 11 | REVIEW |

## Files

### vendored: tinygrad (630 files) — DROP - take 7.0 tinygrad pin, rebuild models

Collapsed; see `git diff 249b03a3f5 <branch> --stat`.

### jetlink (72 files) — DROP - 7.0 ships native Jetlink

Collapsed; see `git diff 249b03a3f5 <branch> --stat`.

### lateral controller

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `starpilot/assets/nnff_models/HONDA_CLARITY.json` | bosch+vfn | 1824 | mod | **gone** | PORT - plug into lateral_controller_factory | dropped: NNFF not ported (7.0 removed it) |
| `selfdrive/controls/lib/honda_eps_firmware_ff.py` | bosch+vfn | 810 | new | **gone** | PORT - plug into lateral_controller_factory | done (slice 1) |
| `selfdrive/controls/tests/test_honda_eps_firmware_ff.py` | bosch+vfn | 733 | new | **gone** | PORT - plug into lateral_controller_factory | done (slices 1-3) |
| `selfdrive/controls/lib/latcontrol_pid.py` | bosch+vfn | 333 | mod | `openpilot/selfdrive/controls/lib/latcontrol_pid.py` | PORT - plug into lateral_controller_factory | done (slice 3: ported as latcontrol_honda_modified_pid.py; 7.0 file untouched) |
| `selfdrive/controls/lib/latcontrol_honda_eps.py` | bosch+vfn | 239 | new | **gone** | PORT - plug into lateral_controller_factory | done (slice 2) |
| `selfdrive/controls/lib/tests/test_latcontrol_pid_eps_modified.py` | bosch+vfn | 224 | new | **gone** | PORT - plug into lateral_controller_factory | done (slice 3; moved to selfdrive/controls/tests/) |
| `selfdrive/controls/lib/honda_lateral_common.py` | bosch+vfn | 191 | new | **gone** | PORT - plug into lateral_controller_factory | done (slice 1) |
| `selfdrive/controls/tests/test_latcontrol_pid_override_fade.py` | bosch+vfn | 99 | new | **gone** | PORT - plug into lateral_controller_factory | done (slice 3) |
| `selfdrive/controls/lib/honda_eps_rack_map.py` | bosch+vfn | 92 | new | **gone** | PORT - plug into lateral_controller_factory | done (slice 1) |
| `system/manager/test/test_honda_eps_param_migration.py` | bosch+vfn | 52 | new | **gone** | PORT - plug into lateral_controller_factory | todo |
| `selfdrive/controls/tests/test_latcontrol_pid_clarity_symmetry.py` | bosch+vfn | 45 | new | **gone** | PORT - plug into lateral_controller_factory | done (slice 3) |
| `starpilot/controls/lib/neural_network_feedforward.py` | bosch+vfn | 17 | mod | **gone** | PORT - plug into lateral_controller_factory | dropped: NNFF not ported (7.0 removed it) |
| `selfdrive/controls/tests/test_latcontrol.py` | bosch+vfn | 1 | mod | `openpilot/selfdrive/controls/tests/test_latcontrol.py` | PORT - plug into lateral_controller_factory | todo |

### modeld / models

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `selfdrive/modeld/modeld.py` | bosch+vfn | 825 | mod | `openpilot/selfdrive/modeld/modeld.py` | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/tests/test_usbgpu_helpers.py` | bosch+vfn | 401 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/compile_modeld.py` | bosch+vfn | 344 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/tests/test_reproject_daemons.py` | vfn | 314 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reprojectcalibd.py` | vfn | 215 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/tests/test_stateful_model_artifacts.py` | bosch | 203 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reprojectd.py` | vfn | 181 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/geometry.py` | vfn | 148 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/fit.py` | vfn | 112 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/meter.py` | vfn | 111 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/tables.py` | vfn | 99 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `scripts/model_compiler.py` | bosch+vfn | 86 | mod | `scripts/model_compiler.py` | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/kernel.py` | vfn | 86 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/SConscript` | vfn | 80 | mod | `openpilot/selfdrive/modeld/SConscript` | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/tests/test_model_fallback.py` | vfn | 68 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/helpers.py` | vfn | 59 | mod | `openpilot/selfdrive/modeld/helpers.py` | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/rotation.py` | vfn | 52 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_config.py` | vfn | 51 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `starpilot/assets/model_manager.py` | bosch+vfn | 41 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `scripts/validate_model_artifact.py` | bosch+vfn | 39 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/cameras.py` | vfn | 28 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/dmonitoringmodeld.py` | vfn | 21 | mod | `openpilot/selfdrive/modeld/dmonitoringmodeld.py` | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/reproject_c4/__init__.py` | vfn | 12 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/tests/test_model_laboratory.py` | bosch+vfn | 8 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `scripts/model_rebuild_pipeline.py` | vfn | 5 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/get_model_metadata.py` | vfn | 4 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `starpilot/system/the_galaxy/assets/components/tools/model_manager.js` | bosch | 3 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_tinygrad.pkl.chunkmanifest` | vfn | 1 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_tinygrad.pkl.sha256` | vfn | 1 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/dmonitoring_model.onnx` | vfn | 0 | mod | `openpilot/selfdrive/modeld/models/dmonitoring_model.onnx` | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_supercombo.onnx` | vfn | 0 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_tinygrad.pkl.chunk01of02` | vfn | 0 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_tinygrad.pkl.chunk01of03` | vfn | 0 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_tinygrad.pkl.chunk02of02` | vfn | 0 | new | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_tinygrad.pkl.chunk02of03` | vfn | 0 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |
| `selfdrive/modeld/models/driving_tinygrad.pkl.chunk03of03` | vfn | 0 | mod | **gone** | REVIEW each vs 7.0 comma-master modeld | todo |

### tools

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `eps_tools/flash.py` | bosch+vfn | 535 | new | **gone** | COPY - standalone tools | todo |
| `tune_report.py` | bosch+vfn | 463 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/eps-diag.py` | bosch+vfn | 347 | new | **gone** | COPY - standalone tools | todo |
| `tools/lateral/eps_report.py` | bosch+vfn | 318 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/eps-update.py` | bosch+vfn | 315 | new | **gone** | COPY - standalone tools | todo |
| `tools/lateral/fit_rack_map.py` | bosch+vfn | 221 | new | **gone** | COPY - standalone tools | todo |
| `tools/lateral/fit_column_load.py` | bosch+vfn | 146 | new | **gone** | COPY - standalone tools | todo |
| `tools/lateral/plan_timing.py` | bosch+vfn | 141 | new | **gone** | COPY - standalone tools | todo |
| `tools/replay/lib/radar_debug.py` | bosch+vfn | 114 | new | **gone** | COPY - standalone tools | todo |
| `tools/lateral/fit_yaw_scale.py` | bosch+vfn | 113 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/check_rwd.py` | bosch+vfn | 104 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/README.md` | bosch+vfn | 91 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd_format/x31.py` | bosch+vfn | 91 | new | **gone** | COPY - standalone tools | todo |
| `tools/lateral/live_row_fit.py` | bosch+vfn | 74 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/README.md` | bosch+vfn | 73 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd_format/base.py` | bosch+vfn | 60 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd_format/x5a.py` | bosch+vfn | 60 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd_format/header.py` | bosch+vfn | 35 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd_format/header_value.py` | bosch+vfn | 24 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TBA,C020-20260805-ClarityPminus5-P117to265-D737-KFF45-Norm1650-Trk4500-TargetMapD-Telem-SpeedClamp0-Pclamp7373.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TBA-C120-linear-max.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TBA-C120-stock.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TLA-A040-linear-max.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TLA-A040-stock.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TLA-A040_tq30000_a9000_44256c0b.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TRW-A020-06.18.2026-stable.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TXM-A040-linear-max.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/39990-TXM-A040-stock.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/Clarity-1663.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/ClarityMax-20260719-1202-FFV1.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/ClarityMax-20260719-1202-Smooth.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/ClarityMax-20260722-1806-FF45-Tracker3200-Norm1650-3840.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/Clarity_PShapeSmooth_KFF45_R6Lead_R6L2_B6_NoSHLL2_CCP728_Telem6A3_TXFIX.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd/Clarity_R6L2_B6_FFV1P_KFF8_NoSHLL2_CCP728_Telem6A3_TXFIX.rwd` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |
| `eps_tools/rwd_format/__init__.py` | bosch+vfn | 0 | new | **gone** | COPY - standalone tools | todo |

### Honda car layer

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `opendbc_repo/opendbc/car/honda/carcontroller.py` | bosch+vfn | 586 | mod | `opendbc_repo/opendbc/car/honda/carcontroller.py` | PORT onto 7.0 refactored Honda | wip (get_eps_modified_steering_pressed done) |
| `opendbc_repo/opendbc/car/honda/tests/test_carcontroller_learners.py` | bosch+vfn | 526 | new | **gone** | PORT onto 7.0 refactored Honda | todo |
| `opendbc_repo/opendbc/car/honda/tests/test_honda.py` | bosch+vfn | 327 | mod | `opendbc_repo/opendbc/car/honda/tests/test_honda.py` | PORT onto 7.0 refactored Honda | todo |
| `opendbc_repo/opendbc/car/honda/steer_ratio.py` | bosch+vfn | 292 | new | **gone** | PORT onto 7.0 refactored Honda | done (slice 1) |
| `opendbc_repo/opendbc/car/honda/tests/test_bosch_a_radar.py` | bosch+vfn | 194 | mod | `opendbc_repo/opendbc/car/honda/tests/test_bosch_a_radar.py` | PORT onto 7.0 refactored Honda | todo |
| `opendbc_repo/opendbc/car/honda/interface.py` | bosch+vfn | 139 | mod | `opendbc_repo/opendbc/car/honda/interface.py` | PORT onto 7.0 refactored Honda | wip (slice 2 lateral done; Bosch-A radar default, vEgoStopping, Nidec hybrid safety still todo) |
| `opendbc_repo/opendbc/car/honda/yaw_rate.py` | bosch+vfn | 87 | new | **gone** | PORT onto 7.0 refactored Honda | todo |
| `opendbc_repo/opendbc/car/honda/tests/test_steer_ratio.py` | bosch+vfn | 74 | new | **gone** | PORT onto 7.0 refactored Honda | done (slice 1) |
| `opendbc_repo/opendbc/car/honda/carstate.py` | bosch+vfn | 29 | mod | `opendbc_repo/opendbc/car/honda/carstate.py` | PORT onto 7.0 refactored Honda | todo |
| `opendbc_repo/opendbc/car/honda/hondacan.py` | bosch+vfn | 16 | mod | `opendbc_repo/opendbc/car/honda/hondacan.py` | PORT onto 7.0 refactored Honda | todo |
| `opendbc_repo/opendbc/car/honda/values.py` | bosch+vfn | 14 | mod | `opendbc_repo/opendbc/car/honda/values.py` | PORT onto 7.0 refactored Honda | wip (VGR flags done; safety flags: see README) |
| `opendbc_repo/opendbc/car/honda/fingerprints.py` | bosch+vfn | 2 | mod | `opendbc_repo/opendbc/car/honda/fingerprints.py` | PORT onto 7.0 refactored Honda | done (slice 2) |

### longitudinal

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `selfdrive/controls/lib/blotv2.py` | bosch+vfn | 247 | new | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/lib/longcontrol.py` | bosch+vfn | 191 | mod | `openpilot/selfdrive/controls/lib/longcontrol.py` | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/lib/longitudinal_planner.py` | bosch+vfn | 174 | mod | `openpilot/selfdrive/controls/lib/longitudinal_planner.py` | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/lib/tests/test_blotv2.py` | bosch+vfn | 171 | new | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/lib/nrdr_long_tune.py` | bosch+vfn | 167 | new | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/tests/test_longitudinal_planner.py` | bosch+vfn | 143 | mod | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/lib/longitudinal_lead.py` | bosch+vfn | 97 | new | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/tests/test_curve_speed_controller.py` | bosch+vfn | 82 | mod | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/tests/test_longcontrol.py` | bosch+vfn | 78 | mod | `openpilot/selfdrive/controls/tests/test_longcontrol.py` | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/tests/test_starpilot_vcruise.py` | bosch+vfn | 67 | mod | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/ui/layouts/settings/starpilot/longitudinal.py` | bosch+vfn | 52 | mod | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `starpilot/controls/lib/curve_speed_controller.py` | bosch+vfn | 48 | mod | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py` | bosch+vfn | 26 | mod | `openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py` | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `starpilot/controls/lib/starpilot_vcruise.py` | bosch+vfn | 21 | mod | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |
| `starpilot/controls/starpilot_planner.py` | bosch+vfn | 5 | mod | **gone** | RE-HOME into openpilot/starpilot/longitudinal | todo |

### built artifact (87 files) — REBUILD - Docker, never copy

Collapsed; see `git diff 249b03a3f5 <branch> --stat`.

### vendored: third_party (10 files) — REVIEW - likely take 7.0

Collapsed; see `git diff 249b03a3f5 <branch> --stat`.

### UI

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `selfdrive/ui/layouts/settings/starpilot/nrdr_tuning.py` | bosch+vfn | 500 | new | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/assets/fonts/como-heavy.fnt` | bosch+vfn | 96 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/mici/tests/test_mici_device_reboot.py` | bosch+vfn | 55 | new | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/widgets/exp_mode_button.py` | bosch+vfn | 55 | mod | `openpilot/selfdrive/ui/widgets/exp_mode_button.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/onroad/augmented_road_view.py` | vfn | 37 | mod | `openpilot/selfdrive/ui/onroad/augmented_road_view.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/starpilot/lateral.py` | bosch+vfn | 36 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/settings.py` | bosch+vfn | 33 | mod | `openpilot/selfdrive/ui/layouts/settings/settings.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/lib/starpilot_version.py` | bosch+vfn | 25 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/mici/layouts/settings/device.py` | bosch+vfn | 19 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/ui_state.py` | bosch+vfn | 13 | mod | `openpilot/selfdrive/ui/ui_state.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/starpilot/aethergrid.py` | bosch+vfn | 11 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/lib/tests/test_starpilot_version.py` | bosch+vfn | 11 | new | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/soundd.py` | bosch+vfn | 11 | mod | `openpilot/selfdrive/ui/soundd.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/home.py` | bosch+vfn | 8 | mod | `openpilot/selfdrive/ui/layouts/home.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/starpilot/vehicle.py` | bosch+vfn | 6 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/mici/layouts/home.py` | bosch+vfn | 6 | mod | `openpilot/selfdrive/ui/mici/layouts/home.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/starpilot/main_panel.py` | bosch+vfn | 5 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/mici/layouts/settings/settings.py` | bosch | 5 | mod | `openpilot/selfdrive/ui/mici/layouts/settings/settings.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/starpilot/driving_model.py` | vfn | 4 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/starpilot/panel.py` | bosch+vfn | 4 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/mici/layouts/settings/developer.py` | bosch | 2 | mod | `openpilot/selfdrive/ui/mici/layouts/settings/developer.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/tests/test_starpilot_navigation_structure.py` | bosch | 2 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/assets/fonts/process.py` | bosch+vfn | 1 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/device.py` | vfn | 1 | mod | `openpilot/selfdrive/ui/layouts/settings/device.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/starpilot/system_settings.py` | bosch+vfn | 1 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/mici/widgets/pairing_dialog.py` | bosch+vfn | 1 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `system/ui/lib/application.py` | bosch+vfn | 1 | mod | `openpilot/system/ui/lib/application.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/ui/layouts/settings/developer.py` | bosch | 1 | mod | `openpilot/selfdrive/ui/layouts/settings/developer.py` | REWRITE in 7.0 openpilot/starpilot/ui | todo |
| `selfdrive/assets/fonts/como-heavy.png` | bosch+vfn | 0 | mod | **gone** | REWRITE in 7.0 openpilot/starpilot/ui | todo |

### long: Bosch-A radar

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `selfdrive/controls/tests/test_radard_bosch.py` | bosch+vfn | 445 | new | **gone** | RE-HOME into 7.0 bosch_a_radar.py | todo |
| `opendbc_repo/opendbc/dbc/honda_bosch_a_radar.dbc` | bosch | 177 | mod | `opendbc_repo/opendbc/dbc/honda_bosch_a_radar.dbc` | RE-HOME into 7.0 bosch_a_radar.py | todo |
| `opendbc_repo/opendbc/car/honda/radar_interface.py` | bosch | 144 | mod | `opendbc_repo/opendbc/car/honda/radar_interface.py` | RE-HOME into 7.0 bosch_a_radar.py | todo |
| `selfdrive/controls/radard.py` | bosch | 65 | mod | `openpilot/selfdrive/controls/radard.py` | RE-HOME into 7.0 bosch_a_radar.py | todo |

### Galaxy

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `starpilot/common/assets/device_settings_layout.json` | bosch+vfn | 483 | mod | **gone** | REWRITE against 7.0 galaxy | todo |
| `starpilot/system/the_galaxy/assets/mobile/js/components/JetlinkModelsCard.js` | bosch | 83 | new | **gone** | REWRITE against 7.0 galaxy | todo |
| `starpilot/system/the_galaxy/the_galaxy.py` | bosch+vfn | 68 | mod | **gone** | REWRITE against 7.0 galaxy | todo |
| `starpilot/system/the_galaxy/tests/test_device_settings_layout.py` | bosch+vfn | 50 | mod | **gone** | REWRITE against 7.0 galaxy | todo |
| `starpilot/system/the_galaxy/assets/components/tools/device_settings.js` | bosch+vfn | 12 | mod | **gone** | REWRITE against 7.0 galaxy | todo |
| `starpilot/system/the_galaxy/tests/test_navigation_params.py` | bosch+vfn | 7 | mod | **gone** | REWRITE against 7.0 galaxy | todo |
| `starpilot/system/the_galaxy/assets/mobile/js/views/ModelManager.js` | bosch | 4 | mod | **gone** | REWRITE against 7.0 galaxy | todo |

### other

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `selfdrive/controls/tests/test_turn_hold_shaping.py` | bosch+vfn | 142 | new | **gone** | REVIEW | todo |
| `tools/replay/ui.py` | bosch+vfn | 108 | mod | `openpilot/tools/replay/ui.py` | REVIEW | todo |
| `starpilot/assets/tests/test_model_pipeline.py` | bosch+vfn | 92 | mod | **gone** | REVIEW | todo |
| `tools/replay/lib/ui_helpers.py` | bosch+vfn | 73 | mod | `openpilot/tools/replay/lib/ui_helpers.py` | REVIEW | todo |
| `tools/StarPilot/feasibleparams.txt` | bosch+vfn | 65 | mod | **gone** | REVIEW | todo |
| `selfdrive/locationd/test/test_calibrationd.py` | vfn | 46 | mod | `openpilot/selfdrive/locationd/test/test_calibrationd.py` | REVIEW | todo |
| `tools/replay/tests/test_radar_debug.py` | bosch+vfn | 40 | new | **gone** | REVIEW | todo |
| `selfdrive/locationd/calibrationd.py` | vfn | 33 | mod | `openpilot/selfdrive/locationd/calibrationd.py` | REVIEW | todo |
| `selfdrive/controls/tests/test_navigation_desires.py` | bosch+vfn | 30 | mod | **gone** | REVIEW | todo |
| `common/transformations/model.py` | vfn | 16 | mod | `openpilot/common/transformations/model.py` | REVIEW | todo |
| `tools/StarPilot/derive_feasible_params.py` | bosch+vfn | 12 | mod | **gone** | REVIEW | todo |
| `selfdrive/monitoring/policy.py` | bosch+vfn | 11 | mod | `openpilot/selfdrive/monitoring/policy.py` | REVIEW | todo |
| `selfdrive/car/redneck_cruise.py` | bosch+vfn | 9 | mod | **gone** | REVIEW | todo |
| `common/tests/test_params.py` | bosch+vfn | 7 | mod | `openpilot/common/tests/test_params.py` | REVIEW | todo |
| `common/pid.py` | bosch+vfn | 6 | mod | `openpilot/common/pid.py` | REVIEW | done (slice 1) |
| `selfdrive/car/car_specific.py` | bosch+vfn | 6 | mod | **gone** | REVIEW | todo |
| `system/updated/updated.py` | bosch+vfn | 5 | mod | `openpilot/system/updated/updated.py` | REVIEW | todo |
| `selfdrive/car/card.py` | bosch+vfn | 1 | mod | `openpilot/selfdrive/car/card.py` | REVIEW | todo |
| `selfdrive/car/tests/test_car_specific.py` | bosch+vfn | 1 | mod | **gone** | REVIEW | todo |
| `tools/lib/api.py` | bosch+vfn | 1 | mod | `openpilot/tools/lib/api.py` | REVIEW | todo |
| `tools/lib/auth.py` | bosch+vfn | 1 | mod | `openpilot/tools/lib/auth.py` | REVIEW | todo |
| `selfdrive/pandad/pandad` | bosch+vfn | 0 | mod | `openpilot/selfdrive/pandad/pandad` | REVIEW | todo |
| `starpilot/controls/lib/tests/__init__.py` | bosch+vfn | 0 | new | **gone** | REVIEW | todo |
| `system/camerad/camerad` | bosch+vfn | 0 | mod | `openpilot/system/camerad/camerad` | REVIEW | todo |
| `system/loggerd/bootlog` | bosch+vfn | 0 | mod | `openpilot/system/loggerd/bootlog` | REVIEW | todo |
| `system/loggerd/encoderd` | bosch+vfn | 0 | mod | `openpilot/system/loggerd/encoderd` | REVIEW | todo |
| `system/loggerd/loggerd` | bosch+vfn | 0 | mod | `openpilot/system/loggerd/loggerd` | REVIEW | todo |

### build / scripts

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `scripts/model_source_map_v26.json` | vfn | 453 | new | `scripts/model_source_map_v26.json` | REVIEW | todo |
| `scripts/rebuild_tg_artifacts.sh` | vfn | 66 | new | **gone** | REVIEW | todo |
| `scripts/tests/test_model_release.py` | vfn | 29 | mod | **gone** | REVIEW | todo |
| `scripts/host_tool_runner.sh` | bosch+vfn | 19 | mod | `scripts/host_tool_runner.sh` | REVIEW | todo |
| `.gitignore` | bosch+vfn | 8 | mod | `.gitignore` | REVIEW | todo |
| `.dockerignore` | bosch+vfn | 5 | mod | **gone** | REVIEW | todo |
| `scripts/model_release.py` | vfn | 1 | mod | **gone** | REVIEW | todo |
| `scripts/model_source_map_v22.json` | bosch+vfn | 1 | mod | **gone** | REVIEW | todo |

### controls core

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `selfdrive/controls/controlsd.py` | bosch+vfn | 294 | mod | `openpilot/selfdrive/controls/controlsd.py` | PORT hooks into rewritten controlsd | wip (factory hook + eps telemetry done in slice 2; hooks are slice 5) |
| `selfdrive/controls/tests/test_controlsd.py` | bosch+vfn | 120 | new | **gone** | PORT hooks into rewritten controlsd | todo |
| `selfdrive/selfdrived/selfdrived.py` | bosch+vfn | 37 | mod | `openpilot/selfdrive/selfdrived/selfdrived.py` | PORT hooks into rewritten controlsd | todo |
| `selfdrive/selfdrived/events.py` | bosch+vfn | 27 | mod | `openpilot/selfdrive/selfdrived/events.py` | PORT hooks into rewritten controlsd | todo |
| `selfdrive/controls/lib/desire_helper.py` | bosch+vfn | 6 | mod | `openpilot/selfdrive/controls/lib/desire_helper.py` | PORT hooks into rewritten controlsd | todo |
| `selfdrive/selfdrived/alerts_offroad.json` | bosch | 4 | mod | `openpilot/selfdrive/selfdrived/alerts_offroad.json` | PORT hooks into rewritten controlsd | todo |

### docs

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `docs/JETLINK.md` | bosch | 255 | new | **gone** | COPY ours | todo |
| `docs/HONDA_EPS_CONTROLLER.md` | bosch+vfn | 103 | new | **gone** | COPY ours | todo |
| `docs/MODEL_REBUILD.md` | bosch+vfn | 76 | mod | **gone** | COPY ours | todo |
| `tools/replay/README.md` | bosch+vfn | 27 | mod | `openpilot/tools/replay/README.md` | COPY ours | todo |

### system / manager

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `system/manager/manager.py` | bosch+vfn | 237 | mod | `openpilot/system/manager/manager.py` | PORT selectively | todo |
| `system/manager/accelerator_shutdown.py` | bosch | 72 | new | **gone** | PORT selectively | todo |
| `system/manager/process.py` | bosch | 46 | mod | `openpilot/system/manager/process.py` | PORT selectively | todo |
| `system/hardware/hardwared.py` | bosch+vfn | 25 | mod | `openpilot/system/hardware/hardwared.py` | PORT selectively | todo |
| `system/manager/process_config.py` | bosch+vfn | 10 | mod | `openpilot/system/manager/process_config.py` | PORT selectively | todo |
| `system/hardware/tests/test_usb.py` | vfn | 3 | mod | **gone** | PORT selectively | todo |
| `system/hardware/usb.py` | vfn | 1 | mod | **gone** | PORT selectively | todo |

### params / schema

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `common/params_keys.h` | bosch+vfn | 71 | mod | `openpilot/common/params_keys.h` | PORT keys into 7.0 contracts; rebuild | wip (Honda EPS keys done in slice 2; rest todo) |
| `cereal/custom.capnp` | bosch+vfn | 53 | mod | `openpilot/cereal/custom.capnp` | PORT keys into 7.0 contracts; rebuild | wip (eps* done in slice 2, @11-@19) |
| `cereal/log.capnp` | bosch+vfn | 15 | mod | `openpilot/cereal/log.capnp` | PORT keys into 7.0 contracts; rebuild | todo |
| `cereal/services.py` | vfn | 2 | mod | `openpilot/cereal/services.py` | PORT keys into 7.0 contracts; rebuild | todo |

### DBC

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `opendbc_repo/opendbc/dbc/acura_ilx_2016_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/acura_mdx_2017_can_ext_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/acura_rdx_2018_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/acura_rdx_2020_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/generator/honda/_honda_common.dbc` | bosch+vfn | 5 | mod | `opendbc_repo/opendbc/dbc/generator/honda/_honda_common.dbc` | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_accord_2017_can_ext_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_bosch_radarless_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_civic_hatchback_ex_2017_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_civic_touring_2016_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_clarity_hybrid_2018_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_common_canfd_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_crv_touring_2016_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_e_advance_2020_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_insight_ex_2019_can_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_odyssey_exl_2018_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/honda_odyssey_twn_2018_generated.dbc` | bosch+vfn | 5 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |
| `opendbc_repo/opendbc/dbc/hyundai_can_refresh_generated.dbc` | bosch+vfn | 1 | mod | **gone** | REVIEW - regenerate from 7.0 sources | todo |

### StarPilot glue

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `starpilot/controls/tests/test_starpilot_card.py` | bosch+vfn | 36 | mod | **gone** | RE-HOME into 7.0 feature owners | todo |
| `starpilot/common/starpilot_variables.py` | bosch+vfn | 18 | mod | **gone** | RE-HOME into 7.0 feature owners | todo |
| `starpilot/common/tests/test_starpilot_variables.py` | bosch+vfn | 14 | mod | **gone** | RE-HOME into 7.0 feature owners | todo |
| `starpilot/controls/starpilot_card.py` | bosch+vfn | 8 | mod | **gone** | RE-HOME into 7.0 feature owners | todo |
| `starpilot/common/starpilot_utilities.py` | bosch+vfn | 5 | mod | **gone** | RE-HOME into 7.0 feature owners | todo |

### panda safety

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `opendbc_repo/opendbc/safety/tests/test_honda.py` | bosch+vfn | 17 | mod | `opendbc_repo/opendbc/safety/tests/test_honda.py` | PORT - safety critical (Nidec hybrid brake) | todo |
| `opendbc_repo/opendbc/safety/modes/honda.h` | bosch+vfn | 10 | mod | `opendbc_repo/opendbc/safety/modes/honda.h` | PORT - safety critical (Nidec hybrid brake) | todo |

### opendbc other

| File | From | +lines | Ours was | 7.0 path | Decision | Status |
|---|---|---:|---|---|---|---|
| `opendbc_repo/opendbc/car/interfaces.py` | bosch+vfn | 11 | mod | `opendbc_repo/opendbc/car/interfaces.py` | REVIEW | todo |
