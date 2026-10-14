# A220 stock candidate and PTM static review

application_sha256=3c6019fd062c3d9c6f605efbc79edc7e30ffa9dc3ee3eadf2db7e0278495bbb6
parent_application_sha256=f790b2bdd72b1adc0797e58b3cc896c313b629c8b6ee773d6c1b550d752d9a98

## Verdict

`[CONFIRMED static bytes/Ghidra/p-code]` Application geometry, checksum arithmetic,
calibration addresses, FF hook/cave/return and intended byte changes are consistent.
The supplied PTM exactly equals an independent reconstruction from the canonical
raw image. Both firmware checksums and the RWD file checksum pass. The stock
candidate application is byte-identical to the raw application.

`[CONFIRMED limitation]` The additional attenuation change covers only rows 0–3.
Rows 4–6 remain stock, and the firmware can explicitly select row 6. It is
therefore not a universal attenuation removal or a validated stutter cure.
No telemetry was ported. A single capture plus a reconstructed copy does not
satisfy the independent-read requirement in D-047. The candidates remain
`DO_NOT_FLASH`; no hardware run, timing, interrupt-stack or recovery validation
was performed. The user calls this calibration family PTM/final tuned EPS;
that naming does not establish final validation.

## Stock application and container

The supplied decoded stock image SHA-256 is
`d527c1a1369d2426276f842e2a07cccba3120a0c30ed18329d92104f02620947`.
It has length 0x70000 and FF padding at 0x0..0x3fff. Its entire application at
0x4000..0x6ffff equals raw `df85f988...`, with SHA-256 `f790b2bd...`.
The 6561 differing bytes versus raw below 0x70000 are all in the boot region.
It is a reconstructed application image, not an independent ROM capture.

The stock RWD named by supplied `build.py` is absent from this folder, so its
original header, supported IDs and file checksum cannot be checked here. The
decoded payload is validated; the missing stock container is not.

PTM RWD is one x5A block at 0x4000 of length 0x6c000 (442368 bytes), ending at
0x70000 exclusive. It decrypts exactly to the supplied full PTM's application.
Supported IDs are `39990-TLA-A220` and `39990-TLA,A220`, each followed by two
NUL bytes. Security words are `0111/0112/1120` for both IDs. All four supplied
RWD copies (PTM, release, and two work outputs) are byte-identical.

| Check | Stock/raw | PTM |
|---|---:|---:|
| sum at 0x6ff80, over 0x4000..0x6ff7f | 0x5c67 | 0x0f30 |
| negative sum at 0x6fffe, over 0x4000..0x6fffd | 0xef57 | 0x89c5 |
| RWD file checksum | original absent | 0x038903f9 |

The raw header and runtime self-check evidence already bound to `f790b2bd...`
independently establish this geometry. PTM preserves both boot 0x0..0x3fff and
post-application 0x70000..0x7ffff byte-for-byte.

## Calibration and code addresses

| Field | A220 address | PTM value / span |
|---|---:|---|
| lower speed gate | 0x11908 | 10 → 0; upper gate unchanged |
| normalizer immediate | 0x42558 | 3429 → 1650; MOVI20 begins 0x42556, opcode intact |
| tracker alpha | 0x11ada | 1999 → 3200; tracker output clamp unchanged |
| command target Y | 0x11b5e | 7 × 9 words, stride 0x12, last row 0x11bca |
| D gain Y | 0x11db0 | 7 × 9 words, stride 0x12, last row 0x11e1c |
| P gain Y | 0x11eac | 7 × 9 words, stride 0x12, last row 0x11f18 |
| P/D/final clamps | 0x11bdc/0x11bde/0x11be0 | 7373 / 1774 / 9000 |
| attenuation Y1 | 0x11c36 | rows 0–3 at +0xc stride, six words per row |
| attenuation Y2 | 0x11cde | rows 0–3 at +0xc stride, six words per row |
| FF hook | 0x41650 | six bytes `0760eb80470b`; delay instruction at 0x41656 retained |
| FF cave | 0x6eb80..0x6ebc5 | 70 bytes; parent erased, no aligned/unaligned 32-bit pointer into exact span |
| FF continuation | 0x4165e | negative-product rounding replayed before returning |

Target Y on all seven rows:
`0,1926,4938,8455,12036,15926,20138,26955,30000`.
D Y is nine copies of 737; P Y is
`117,148,184,220,245,257,263,265,265`.
These curves, norm, tracker and clamps match the supplied A040 application
`8cf8e537ed81d3defb775b7edd5b3fd195765b7f1cd651167402e9129c5dbcea`.
That A040 application's attenuation tables do not match this new A220 change.
Authority tables, command input clamp and all X axes remain unchanged.

The FF routine implements `clamp(PD + (45 * s16(reference) >> 10), ±32767)`.
The existing product rounding and downstream scale/final clamp are retained.
Ghidra confirms R8 is the reference, R7 is overwritten before later use, and
the host saves/restores PR/MACL/GBR. The cave adds no stack stores.
At reference 30000 the additive FF is 1318; negative arithmetic right shift
gives -1319 at -30000. Leaving the target at 30000 avoids the 32767 target
endpoint hypothesis, but does not establish any physical stutter benefit.

## Additional “stutter” / A280 attenuation change

`[CONFIRMED Ghidra]` Function 0x4183c takes the absolute magnitude of its signed
input, looks up two six-point curves, then computes
`trunc(weight1*Y1/16384) + trunc(weight2*Y2/16384)`, clamped to ±32767.
The caller at 0x41640 passes a controller word at base 0xfff89ac0 + 0x5c.
The physical units and causal link to observed wheel stutter remain unproven;
“torque-rate attenuation” is the supplied label, not a measured unit claim.

X1/X2 are at 0x11be2/0x11c8a. Rows 0–3 have knots
`0,64,128,192,256,320`; both stock Ys are
`256,256,230,200,169,148`. PTM sets them to six copies of 256.
At/above key magnitude 320 this raises that path's curve weight from 148 to
256 (1.730×); it removes the declining curve, rather than fixing an instruction
or an integer overflow. 256 is the unchanged low-key curve value, not a claim
that the function's Q14 weight arithmetic has become an identity transform.

`[CONFIRMED correction]` The shared controller row is
**0xfff89c58 = 0xfff89c4c + 0xc**, read using unsigned byte loads. The earlier
A220 map's 0xfff89c4f was a pointer-arithmetic error and is superseded.
The configuration record search at 0x5a10c uses 12 records at 0xec9c with
stride 0x5b. Their row values at +0xf are
`0,0,1,0,0,0,0,2,3,0,0,0`.
Dispatch 0x5a248 supplies record byte +0xf to setter 0x422ea. This establishes
the normal configuration rows, not a speed→row mapping.

The setter checks bit 0x40 at 0xfff8ab23 and **forces row 6 when set**.
Rows 4–6 were not modified; row 6 still declines to 148 at key 320.
P-code tests execute the setter's normal and forced paths and reproduce the
remaining attenuation. The significance of that status bit and whether it
appears in the intended operating envelope still require further evidence.
Follow-up [row-six recheck](../row-investigation/ROW_SIX_RECHECK.md) traces
explicit mode entry/exit. Normal-driving use and the historical “degraded”
label are not established; telemetry rows 0/1 are compatible with it.
Do not flatten the remaining rows merely to conceal this limitation: that
would be an additional calibration change outside this review.

## Complete change scope and validation

Exactly **484 changed bytes in 86 contiguous runs**, all enumerated by the
verifier (half-open addresses). Group counts:

| Changed region | Changed bytes |
|---|---:|
| 14 version punctuation bytes in 12 main + 2 secondary records | 14 |
| speed gate / tracker | 1 / 2 |
| 7 target rows + three clamps, 0x11b5e..0x11be1 | 118 |
| attenuation Y1/Y2 rows 0–3 | 32 / 32 |
| D / P gain rows | 114 / 91 |
| FF hook / normalizer operand / FF cave | 6 / 2 / 68 |
| sum / negative checksum words | 2 / 2 |

The 70-byte cave includes two bytes already equal to parent FF, explaining
68 changed bytes. Every expected byte and every byte outside the intended
changes is compared against an independent reconstruction, without importing
or running the supplied builder. CAN descriptors (including ID, DLC and
direction) and 0x1c204 telemetry hook are unchanged: **this PTM has no telemetry**.

Executed:

- `verify_a220_ptm_review.py`: checks exact full-image reconstruction, both
  checksums, RWD decode/geometry/header/file checksum, all consumer literals,
  cave scan, every diff run, source-copy equality and computed evidence bindings.
  A checksum-valid unexpected-code mutation is a negative control.
- Vendored `check_rwd.py`: RWD file checksum and both internal checksums pass.
- `verify_a220_static_parent.py`: existing canonical parent checks still pass.
- Ghidra 12.0.3 SH-2A disassembly of actual PTM host/cave/normalizer and original
  attenuation/row setter/record dispatch; each evidence file embeds its app hash.
- Ghidra p-code: **4400 assertions, zero failures**, covering 189 FF cases,
  77 complete attenuation/interpolation cases, eight row-setter cases, and
  a stock-curve-restoration negative control.

The A040 builder and A040 telemetry-specific patch verifiers were not run or
re-pinned: this is an A220 artifact review, with no telemetry patch or firmware
change authored here. The supplied builder was not executed, and the supplied
work/release equality is an artifact comparison, not an independent rebuild.
No flash, new tune, road/bench test, absolute timing/stack analysis, closed-loop
stutter proof or recovery test was performed. In particular, tracker 3200 versus
1999 is a material recursive control change whose physical stability cannot be
established by these instruction tests.
