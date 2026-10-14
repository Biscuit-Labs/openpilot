# CR-V 5G A220 PTM firmware-inversion controller

## Artifact and scope

The owner supplied
`39990-TLA,A220-20261006-PTM-ClarityFF45-Norm1650-Trk3200-P117to265-D737-Pclamp7373-Dclamp1774-Out9000-SpeedClamp0-A280Flat.rwd`.
The exact file is retained as
`firmware_evidence/a220/8f175250519130b0a8505291ef328b82f9caf543cfb76c62c3bc23e954e727a7.rwd`.
Its decrypted application covers `0x4000..0x6ffff`, SHA-256
`3c6019fd062c3d9c6f605efbc79edc7e30ffa9dc3ee3eadf2db7e0278495bbb6`.
The container checksum and both application checksums pass `eps_tools/check_rwd.py`.

The file is byte-identical to the Honda repository's previously reviewed
`A220-PTM-A280Flat-3c6019fd-DO_NOT_FLASH.rwd`; it is new to this openpilot tree,
not a newly discovered firmware build. The source review from Honda repository
commit `1e35d929bb8f48d9f5f68d12422f8c7a349a41c9` is folded in as
`firmware_evidence/a220/source-ptm-review.md`, SHA-256
`b3d30d4043267dc37f20c5446ac13f7795b88ca94d1e16a62c69f28a3bbeada4`.
Its relative references describe the original repository. It is evidence, not
instructions to flash or change the firmware. The review's hardware/recovery
restrictions remain in force; adding controller support does not validate flashing.

## Selection and tables

The modified fingerprint `39990-TLA,A220` is recognized as CR-V 5G. Exact
normalized EPS ID `39990-TLA-A220` selects `CRV_5G_A220_FF45` in both
`LatControlHondaEps` and the PID firmware-feedforward shadow. A040 retains its
existing calibration. The firmware-controller enable toggle continues to apply.
No additional command delay or PID trims are inferred for A220.

`[CONFIRMED, static byte decode of the application hash above]`:

| Table / constant | Address | Value |
|---|---|---|
| Command X, rows 0/1 | `0x11ae0`, stride `0x12` | 0,161,222,322,409,534,696,998,1663 |
| Command Y, all rows | `0x11b5e`, stride `0x12` | 0,1926,4938,8455,12036,15926,20138,26955,30000 |
| P X, rows 0/1 | `0x11e2e`, stride `0x12` | 0,104,279,510,807,1108,1330,1552,1663 |
| P Y, all rows | `0x11eac`, stride `0x12` | 117,148,184,220,245,257,263,265,265 |
| Command clamp | `0x11ade` | 1774 |
| Speed ceiling X, row 0 | `0x11930` | 0,50,100,150,200,250,300,350,400 |
| Speed ceiling Y, row 0 | `0x119ae` | 1774,1774,1774,1774,1774,1774,1330,1330,1330 |
| Tracker / feedback normalization | `0x11ada` / `0x42558` | 3200 / 1650 |
| Motor-angle conversion word | `0x19c00` | 3121 |
| Position VGR X / Y, 30 words each | `0x11374` / `0x11338` | exactly equal to the existing A040 position table |

The input clamp, interpolation literals and row byte are traced by the source
review. Its FF cave implements the additive Kff45 law. A220's command X must
not reuse A040's: at key 443 the two ask approximately 13094 and 4938 R5.
The stored speed ceiling is retained conservatively; the exact scope of the
`SpeedClamp0` bypass has not been measured on A220.

The separate A220 VGR flag selects the shared, byte-identical position map.
`A280Flat` refers to attenuation tables; it does not flatten the position VGR
table. The existing firmware-VGR setting and its default are unchanged.

## Explicit calibration limits

`[CONFIRMED, static]` This calibration models rows **0/1**. Rows 2/3 use 1050
instead of 998 at the penultimate command knot; rows 4–6 have other differences.
Firmware configuration normally selects rows 0–3, with a separate forced-row-6
path. The supplied image has **no A040-style telemetry patch**. No A220 route or
live row evidence has been supplied for this change, so this implementation
does not establish which row the owner's EPS selects.

`[INFERRED, transferred calibration]` The R6 scale and column-load fit retain
the existing A040 calibration from route `00000006--82bb552a2c`, logged openpilot
`49e6610d08373bb8512ccce38d2f75c61656325e` (D-093). Norm 1650, tracker 3200,
motor conversion 3121 and the position table support this transfer, but it is
not an A220 vehicle measurement. The A280 attenuation change is not represented
by a new fitted load model. See the source review for its rows-0–3-only scope.

Unit tests verify the actual artifact, tables, firmware selection, VGR selection,
inversion math and real controller/PID-shadow construction. They do not verify
A220 live row selection, steering response, timing, physical stability, or the
closed loop. No firmware was modified or flashed and no controller was deployed
to the comma as part of this change.
