# Real camera fixture manifest

The standardized camera/mode fixture set in this directory has not been supplied.
Routine successful unit/API/browser checks use clearly identified decoder/worker doubles.
Invalid-byte decoder rejection is not camera support.

For the RAM investigation, three real private CR3 samples were safely extracted from the
user's retained upload into ignored `test-results/memory-inputs/`. Their private manifest
records upload provenance, SHA-256 and expected visible dimensions. They are used by the
real memory benchmark harness, not distributed or substituted for this camera/mode matrix.
See docs/MEMORY_OPTIMIZATION.md for the measured evidence. Unknown camera/mode fields and
the missing standardized `tests/fixtures/manifest.json` keep the optional pytest gate skipped.

Supply user-owned or explicitly redistributable Canon CR3 samples, including landscape
and portrait, full RAW and compressed C-RAW, and each desired camera/recording mode.
For each fixture record relative filename, provenance/permission, camera, firmware/mode,
SHA-256, expected visible width/height after orientation, and known capture metadata.
Include a neutral/color reference if assessing rendering quality. Originals remain read-only.

| Camera | Recording mode | Orientation | Visible dimensions | Provenance / SHA-256 | Result |
|---|---|---|---|---|---|
| None supplied | RAW / C-RAW needed | Landscape + portrait needed | Unknown | Missing | BLOCKED |

Fixtures are excluded from source control by default. Do not download images with unclear
redistribution rights. Populate `manifest.json` following the real-fixture test contract once
licensed samples are available; real tests must fail on incorrect output, not be mocked.
