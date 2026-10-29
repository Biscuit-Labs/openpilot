# Vendored Jetlink (comma side)

| | |
| --- | --- |
| Upstream | https://github.com/zoompilot/jetlink |
| Revision | `3d4f6710d36c5601395916a885defd2f381ad474` (tag `v0.8.10`, `jetlink.openpilot.API == 3`) |
| Previously | `4b747aebad3d8d96ab26d76f1668f2b2ecb1b667` (0.8.5, API 2), as Zoompilot `develop` `02be6b631d` pinned it; updated 2026-10-29 |
| License | MIT, see `LICENSE` |

Only what the comma runs is vendored, byte-for-byte from that revision:

* `jetlink/` the Python package (numpy is its only third-party dependency), including the root helper
  `jetlink/comma/jetlink-root.sh` that `jetlink.comma.root` runs under `sudo -n` (it moved into the package in 0.8.8)
* `scripts/comma/jetlink-root.sh` upstream's forwarder to it, for an owner from an older Jetlink still running across an update
* `LICENSE`

The iOS/Android/macOS apps, the Swift server (`JetlinkKit`), tests and docs are not vendored; the server is
installed separately on the inference host and must be the **same release** as this package (the wire protocol is
version-exact: `jetlink.protocol.VERSION == 3`). Pair this package with Jetlink 0.8.10 on the host.

`starpilot/jetlink_adapter` puts this directory on `sys.path` and in the environment of the processes it starts.
Nothing here is imported unless the link is enabled, except by the optional `jetlinkd` owner.

## Updating

Do not bump independently of the Jetlink server and the Zoompilot adapter contract. To update:

1. Replace `jetlink/` with `<jetlink>/jetlink/` (no `__pycache__`) and copy `scripts/comma/jetlink-root.sh` and LICENSE.
2. Re-apply `LOCAL_MODIFICATIONS.patch` (`patch -p1`), fixing any hunk by hand, and regenerate the patch from the result
   (`tests/test_join.py` checks it reverses cleanly).
3. Check `jetlink.openpilot.API` against `starpilot.jetlink_adapter.API`, read the release's CHANGELOG **Forks** section, and
   re-run `jetlink.openpilot.conformance` (`starpilot/jetlink_adapter/tests/test_adapter.py`).
4. The warp pickles (`starpilot/jetlink_adapter/models/`) are the fork's own build (`starpilot/jetlink_adapter/warp.py`) and do
   not depend on the Jetlink version; rebuild them only for a tinygrad bump. Re-validate the allowlisted big model.
5. Update the revision above.

## Local modifications

Three small additions to `jetlink/openpilot/joining.py`, kept as `LOCAL_MODIFICATIONS.patch` (apply with
`patch -p1 < LOCAL_MODIFICATIONS.patch` after re-vendoring). They are additive and use hooks Jetlink already reads with a
`getattr` fallback, so they can be offered upstream:

1. `join().build()` calls `op.validate_spec(spec)` when the adapter has one. The fork's adapter refuses any server model
   whose SHA-256 and exact layout it has not validated (`starpilot/jetlink_adapter/profiles.py`); the join then fails like
   any other build failure and the small model keeps driving. Without this hook an unvalidated model would be promoted
   and its output parsed with the wrong generation flags.
2. `JoiningModelState.demote_invalid()`: modeld found the large model's output unusable (non-finite or implausible) and
   hands back through Jetlink's own bad-output path (`BAD_OUTPUT`, 0.8.8+: counted as lag, the link kept), without reaching
   into private methods.
3. `JoiningModelState.last_demotion` / `last_failure`: why the last handback or failed build happened, for the status line.

No other file is changed. The wire protocol, the server contract and `jetlink.openpilot.API` are untouched.
