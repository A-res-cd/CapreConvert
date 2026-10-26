# Validation and acceptance

Current release is CapreConvert v0.3.0. See V0_3_VALIDATION.md for executed commands,
148 backend/19 browser checks, native document/RAW/PNG validation, migration and frozen
release evidence. DOCX→PDF uses external local LibreOffice; PDF→DOCX is editable text
without OCR/layout reconstruction. Compatibility identifiers remain unchanged. The
following v0.2.0 results are retained as historical evidence, not renamed as v0.3.0.

## Historical v0.2.0 validation

Host: Windows 11 x64 (10.0.26200), Python 3.12.13; total physical RAM 7.4 GiB.
The previous fixed 3 GiB admission rule has been replaced by staged, dimension-aware
budgets and a configurable safety reserve. The current default reserve is 768 MiB,
header-inspection budget is 256 MiB, and total render budget is
`max(256 MiB, 128 MiB + 48 * visible_pixels)` per worker. These are admission policies,
not measured universal minimum RAM requirements. Available RAM is sampled; existing
worker RSS is credited and only peers' remaining growth is reserved. Sequential conversion
is the default. RSS monitoring and pressure handling are safeguards, not an OS memory sandbox.

Current optimization backend check: **101 passed, 1 skipped in 48.97 s** with
`python -m pytest tests/unit tests/integration -q`. Current browser regression:
**12 passed in 52.75 s** with `python -m pytest tests/e2e -q`. The optimized Windows
v0.2.0 build, frozen-app smoke, ZIP CRC and SHA-256 verification passed. The delivery
contains 301 files in a 32.58 MiB ZIP. The earlier styling regression suite passed
12 browser checks (210.35 s), then 2 targeted navigation/theme checks (5.96 s).
Exact commands and package evidence are recorded in CODEX_HANDOFF.md.

Automated API/browser conversions use a named deterministic spawned-worker double.
Rendering unit tests use a rawpy double to assert full-size/AHD/white-balance/gamma
parameters, single orientation, exact sRGB transfer, profile embedding and JPEG 4:4:4
sampling. Separate real native probes and source API benchmarks now use three private
CR3 files from a retained user upload. They remain local, are not redistributed, and
their provenance, SHA-256 hashes and expected visible dimensions are recorded in ignored
`test-results/memory-inputs/manifest.json`. The samples cover 5536 x 3692 and portrait
3692 x 5536 output; they do not establish a broad camera/recording-mode matrix.

The optional pytest real-camera gate remains explicitly skipped because
`tests/fixtures/manifest.json` has not been supplied with the required camera/mode fields.
That separate fixture gate must not be confused with the real private benchmark evidence.

| Memory probe | Baseline peak RSS | Optimized peak RSS | Observed result |
|---|---:|---:|---|
| Direct native conversion, one private 20.44 MP CR3 | 357.242 MiB | 357.109 MiB | Effectively unchanged overall peak; native rendering remains dominant |
| Synthetic 24 MP encode/validation/preview probe | 340.824 MiB | 274.109 MiB | 19.575% lower peak for this probe; not real RAW decoding |
| Isolated source CLI import, three-trial median | 45.79 MiB | 19.08 MiB | 26.71 MiB avoided by keeping FastAPI out of source spawn imports |

Probe JSON is under ignored `test-results/memory-probe-comparison.json` and
`test-results/source-main-import-*`. The before/after full-resolution JPEGs decoded to
identical RGB pixels, dimensions, orientation, quantization and sampling. Complete JPEG
hashes differ because the generated ICC profile has creation-time fields; the real
probe's only byte differences were two ICC timestamp bytes. This is not a change in
color processing or JPEG settings. Previews use scaled JPEG decoding and may differ.
The eight-scenario source API run has completed: idle, single-file, sequential batch,
multi-RAW ZIP and repeated sessions completed; cancellation cancelled safely; corrupt
input failed safely; the low-memory policy test rejected work as expected. The low-memory
case raises the configured reserve instead of exhausting host RAM. Original hashes were
unchanged. The same eight scenarios also passed against the optimized v0.2.0 Windows
package; normal workloads used the default configuration. Single, three-file batch, three-file ZIP and
three repeated conversions produced ten verified full-resolution JPEGs with RGB pixels,
ICC, normalized orientation, 4:4:4 sampling and hash checks. Metadata/GPS policy was retained.

The packaged process-tree idle RSS was 78.60 MiB; sampled tree peaks were 417.40 MiB
(single), 427.88 MiB (batch), 436.95 MiB (ZIP) and 413.16 MiB (repeated sessions).
Exactly one converter ran at once, with the HTTP process and one Windows helper/console
process. Successful render admissions observed 2.219-2.302 GiB of system available RAM;
the lowest sampled available RAM during these workloads was 1.937 GiB. These observed
conditions demonstrate operation below the old 3 GiB rule for these samples, not a new
universal minimum. RSS includes shared-page double counting and sampled peaks can miss
short-lived maxima.

An additional packaged cancellation run waited until native work was underway. The
worker reached 256.18 MiB and the process tree 336.45 MiB; cancellation latency was
2.390 s. All three files were cancelled, no converter remained, and no staged RAWs or
partial outputs remained. See ignored `test-results/memory-optimized-v0.2.0.json`,
`test-results/memory-packaged-summary-v0.2.0.json` and
`test-results/memory-cancel-under-load-v0.2.0.json`. MEMORY_OPTIMIZATION.md records the
full benchmark comparison, measurement conditions and remaining limits.

Browser evidence: twelve Playwright Chromium headless 156 tests; desktop workflow, partial success,
both attachment downloads, refresh, retained-input retry, cancellation preserving success,
mobile-width 320/390 layouts, pairing, keyboard picker and theme persistence. All observed
page requests were same-origin; the conversion workflow also blocks outside-network requests.
Duplicate-name handling, settings preflight and restoring jobs beyond the first history page
are covered. Visual screenshots inspected: test-results/desktop-results.png
and test-results/mobile-390.png. No runtime Internet access is needed; the local host must
still be reachable. This is not a service-worker PWA and does not convert without the host.

Preview extension checks: bounded landscape/portrait/small derivatives, metadata stripping,
atomic thumbnail/preview pairs, full-JPG fallback, protected inline previews, exact selected
full-JPG ZIP contents, cache/lease/failure handling, restart preservation, viewer controls,
per-photo and bulk selection, persisted selections, cross-page export, 320px keyboard/touch
layout and downloads. Inspected test-results/preview-desktop.png and preview-mobile.png.
A worker-exit final-message race exposed by browser checks was fixed and covered by a
deterministic supervisor regression. Duplicate pytest module basenames were fixed by making
test directories explicit packages. The earlier complete suite passed after these fixes;
current optimization checks are listed above.
The launcher now checks the existing session before exchanging a new bootstrap; a real
page-navigation regression verifies that owned jobs and selected exports remain visible.
Styling evidence: latest pushed reference commit pinned and verified through GitHub's
PushEvent API; collapsed/expanded desktop navigation, keyboard/mobile drawer, local Fraunces
fonts, paper/indigo/orange light and dark themes, and settled screenshots were checked.

Additional hardening: exact upload lengths/retry cleanup; directory traversal/device/ADS/UNC
and link/encryption rejection; central-directory byte/count checks before ZipFile allocation;
CRC and output ZIP integrity; multiple ZIPs and Unicode/case collisions; CSRF/Host/Origin;
foreign IDs; idempotency race; queue, disk and memory admission; RSS termination; timeout,
crash, cleanup, input references, exclusive workspace, restart interruption and JPEG hashes.

| Acceptance target | Actual evidence | Outstanding |
|---|---|---|
| Windows source application | 101 backend and 12 browser checks passed; all eight private benchmark scenarios exercised | Broader real-workload coverage |
| Windows one-folder build | v0.2.0 build/smoke/ZIP/hash passed; all eight real-input benchmark scenarios exercised, plus native cancellation under load | Clean machine |
| Windows 10 | None | Target OS test |
| macOS / Linux | None | Install, build and full target checks |
| Android Chrome / iPhone Safari | Chromium width emulation only | Physical phones and same-LAN workflow |
| Camera/model/mode matrix | Three provenance-recorded private CR3 samples, landscape and portrait dimensions | Named camera/mode matrix, RAW/C-RAW coverage and full fixture contract |
| Real color/metadata/resource calibration | Real native RSS/timing probes and full-JPG pixel comparison; mathematical transfer checks | Broader sample calibration, reference scene and actual ExifTool metadata run |

No release-validated camera claim is made. Packaging and physical-device gates cannot be
inferred from mocks or viewport emulation. Refer to tests/fixtures/README.md for sample needs.
