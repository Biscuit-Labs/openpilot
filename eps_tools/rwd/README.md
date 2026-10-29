# EPS firmware images (`.rwd`)

This fork does not ship firmware images. The PTM builds change often (per-image revisions, A280-flat
and corrected PTM builds) and a stale image is worse than none, so each car's current build and its stock recovery
image live with the EPS firmware work, not here.

Copy the image you mean to flash, **and a verified stock recovery image for the same part number**, into this folder
(or better, a persistent copy such as `/data/media/0/eps_tools/rwd/`; the comma updater removes untracked and
ignored files under `/data/openpilot`). `.rwd` files are git-ignored so they can't be committed by accident. Then:

```bash
python3 ../check_rwd.py YOUR_FIRMWARE.rwd    # file checksum + decrypted firmware checksums must all PASS
python3 ../flash.py                          # guided flasher: auto-detects the bus, offers a dry run
```

The calibration for an image (in the lateral controller) must match the image you flash; reflash and update the
calibration in lockstep.
