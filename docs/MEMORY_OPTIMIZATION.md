# RAM optimization: analysis and execution plan

## Phase 1: inspected baseline

The project uses FastAPI (no Flask), Python 3.12, rawpy/LibRaw, NumPy and Pillow.
One Uvicorn process runs without a development reloader. One global supervisor serializes
jobs and defaults to one spawned image process; at most two are configurable. A workspace
lock prevents duplicate ownership. PyInstaller uses onedir and freeze_support before app
imports. Versioned v0.1.0 is the immutable packaged baseline.

Uploads already stream to disk with bounded writes. ZIP inspection bounds the central
directory (32 MiB), entries (10,000), expansion, compression ratio and LZMA dictionaries.
One selected RAW is extracted to disk per worker, never the whole archive. Temporary extracted RAWs,
partial JPEGs and partial archives are cleaned on cancel/failure. File-backed authenticated
responses serve results; the browser uses bounded 1280px/320px previews, no base64 images.
No framework replacement or upload/archive rewrite is justified.

Current conversion: isolated worker opens RAW headers, requests pixel-based admission,
unpacks and develops full visible 16-bit linear sRGB using AHD and camera/auto WB, closes
LibRaw, encodes the exact sRGB transfer in rows, constructs a Pillow RGB image, writes a
full-resolution JPEG (quality unchanged, 4:4:4, ICC/EXIF), verifies and decodes it, then
creates reduced preview/thumbnail derivatives. Buffers remain in the child, not HTTP IPC.

Highest-impact issues:

- Fixed 2 GiB additional reserve plus 1 GiB bootstrap rejects any task below 3 GiB available,
  before looking at dimensions. This is policy, not measured image demand.
- Admission subtracts entire peer budgets from system available memory, which already
  excludes their resident memory. Existing current-worker RSS also receives no credit.
- The RGB construction transiently holds linear16 (6 B/pixel), RGB8 (3 B/pixel) and Pillow
  RGB storage (4 B/pixel). Converted row strips can avoid the full RGB8 intermediate.
- Preview generation explicitly loads the full JPEG before thumbnail(), preventing reduced
  JPEG draft decoding. This does not improve the exported image and increases worker peak.
- Error paths do not always close the Pillow image immediately.
- Source-mode spawn imports the HTTP stack through __main__ before worker dispatch.
  An isolated import probe found approximately 29 MiB avoidable import RSS on this host.
- Current supervisor samples worker RSS at 100 ms, but records no peak diagnostics or
  full application tree usage. It enforces worker caps without adapting to later system
  pressure. No actual fixture benchmark previously justified the 64 B/pixel budget.

## Baseline inputs and provenance

The user's retained upload contains 89 CR3 archive entries (a different upload from the
historically reported 88-file failed batch). Three representative members were extracted
with the existing safe bounded extractor into ignored test-results/memory-inputs/.
Its manifest records private user-upload provenance, member names and SHA-256 hashes.
Original upload/workspace remain read-only. Do not redistribute these private fixtures.
Camera/mode coverage is limited to the samples actually measured; no broad camera claim.

## Ordered implementation and gates

1. Capture immutable v0.1.0 runtime idle/admission behavior, and baseline conversion peak
   in an isolated guarded experiment if stock admission cannot start on this host.
2. Remove demonstrably unnecessary image copies/reloads; test exact RGB/full-JPEG equality
   and resource cleanup. Keep dimensions, WB, color transfer, quality and metadata unchanged.
3. Introduce a tested resource policy: configurable safety reserve, bounded header-probe
   budget, dimension-based render budget, only reserve unallocated worker headroom,
   sequential fallback, measured process-tree peaks, and bounded-rate pressure monitoring.
   Calibrate conservative estimates against the real samples; reject unsafe workloads.
4. Avoid source-worker HTTP imports; preserve API/UI, authentication, cancellation and
   streaming paths. Run backend/resource regressions, then browser workflow checks.
5. Run reproducible idle/single/batch/ZIP/repeat/cancel/corrupt/low-memory benchmarks with
   process counts, RSS/Windows peak where available, timing, disk and JPEG validation.
   Report stock-policy failures and controlled experiments separately. Never fabricate
   missing coverage or advertise a universal RAM minimum from a small sample.
6. Build a new v* onedir package, smoke/benchmark it and check ZIP/hash. Preserve existing
   versioned releases. Update packaging, configuration, benchmark evidence and handoff.

No minimum RAM promise or speed/memory improvement is established by this analysis alone.
Measured results and limitations will be appended after execution.

## Implemented resource policy

The reserve is now an additional configurable 768 MiB of **currently available** RAM,
not another reservation of the OS's already-used pages. `memory_reserve_bytes` accepts
values from 256 MiB; its default is a conservative operational policy, not a measured
Windows requirement. A smaller reserve is an explicit host configuration decision.
`worker_memory_bytes` remains an optional total-worker cap, with a 256 MiB lower bound.

A fresh isolated worker receives a 256 MiB header-inspection cap. After actual visible
pixel dimensions are known, its total RSS budget is `max(256 MiB, 128 MiB + pixels * 48)`.
The fixed term covers interpreter/native/codec overhead; the dimension term conservatively
covers native AHD, RAW and transfer buffers. The three private samples are all 20.44 MP,
so this model remains provisional for other cameras, compression modes and dimensions.
For those samples the budget is about 1063.6 MiB versus an observed native peak near
357 MiB. A header or render overrun is stopped rather than silently increasing its cap.

System available memory already excludes resident application pages. For a new worker,
reserve only `max(0, peer_budget - peer_RSS)` for each peer. For an existing worker's
render request, credit its own already-resident RSS (bounded by its existing cap). One
unknown image is inspected at a time. A second requested worker starts only when a
comparable render can fit; if its actual dimensions need more memory, it parks before
unpacking until its peer finishes. Cancellation and total file timeout remain active.
This keeps the configured limit global across requests without launching duplicate servers.

RSS and system pressure are sampled every 0.5 s by default (`memory_poll_seconds`, range
0.25-5 s). A worker exceeding its cap is stopped. Sustained available memory below the
reserve for one second stops one worker; below 256 MiB triggers an immediate stop at the
next sample. This handles other applications allocating memory after admission, but is
not an OS allocation sandbox or a guarantee against instantaneous native allocation spikes.
No forced garbage collection or continuous busy polling was introduced.

Per-file diagnostics record budgets and worker peaks; Windows lifetime working-set counters
supplement samples. Authenticated `/api/v1/resources` reports available RAM, reserve,
application process-tree RSS, its **sampled** peak and worker counts without paths/PIDs.
Shared DLL pages can be counted in multiple processes. Failed optional aggregate diagnostics
are marked unavailable and never abort sibling conversions. Worker monitoring failures
stop only the affected worker. Original parent safety diagnoses survive generic IPC errors.

## File-processing changes and quality checks

The encoder uses a 64 KiB lookup table that is identical to the previous float32 transfer
for all 65,536 uint16 values. It fills the full-size Pillow RGB image through 128x2048
pixel tiles, avoiding an additional full-size RGB8 intermediate. All conversion-owned
Pillow images use explicit `close()`, including cancellation/error paths. Full-resolution
validation pixels are released before previews. Preview-only JPEG draft decoding avoids
another full-size allocation. RAW parameters, orientation, full visible dimensions,
quality, 4:4:4 subsampling and optional metadata behavior remain unchanged.

Tests compare the complete transfer domain and identical JPEG bytes at quality 70/95/100
with a common ICC profile; verify tile bounds, explicit resource cleanup, protected
resource diagnostics, cap/admission errors, single/parallel scheduling and memory-pressure
termination. Source-mode worker dispatch now avoids importing the HTTP stack; three
isolated import trials measured median 45.79 -> 19.08 MiB (26.71 MiB saved). Frozen worker
entry dispatch was already correct. Onedir packaging remains appropriate.

## Before/after allocation measurements

These are isolated allocation experiments under a separate supervising RSS/physical-memory
limit, **not** evidence that the v0.1.0 default API admitted the workload. Its stock
3 GiB guard rejected all real-photo API benchmark jobs on this host before decoding.
Both experiments used the same read-only input, output settings and 768 MiB starting
reserve, with a 256 MiB runtime abort floor. The actual baseline used a 1 GiB RSS cap;
optimized and synthetic experiments used a 512 MiB cap. No cap was reached.

| Probe | Baseline Windows worker peak | Optimized Windows worker peak | Finding |
|---|---:|---:|---|
| Private real 5536x3692 CR3 (20.44 MP) | 357.242 MiB | 357.109 MiB | Effectively unchanged; native AHD dominates |
| Explicit 6000x4000 synthetic transfer (24 MP), no RAW decoder work | 340.824 MiB | 274.109 MiB | 19.575% lower peak in transfer/encoding workload |

The single-pair durations were 8.282 -> 5.985 s for real CR3 and 3.500 -> 1.297 s for
synthetic transfer. They are observations, not repeat-trial performance guarantees. Host
background activity and caches were not controlled. A sampled 50 ms tree peak missed the
brief baseline native peak; the table compares Windows kernel lifetime peaks instead.

Decoded RGB, dimensions, orientation, JPEG quantization and sampling match exactly for
both probes. Bounded byte comparison found only two changed bytes in the actual JPEG
and one in the synthetic JPEG: the generated ICC creation timestamp. All other JPEG,
EXIF and profile bytes match. This is output-equivalence evidence for these inputs, not
reference-scene color calibration or coverage of every metadata/camera mode.

Reproducible reports and source snapshot (ignored, private local artifacts):
`test-results/memory-probe-comparison.json`,
`test-results/memory-{baseline,optimized}/{real,synthetic}/report.json`, and
`test-results/memory-baseline/conversion.py`. Use `scripts/probe-conversion-memory.py`
for another isolated allocation experiment, or the API harness documented in
MEMORY_BENCHMARKS.md for production admission and full application behavior.

## Source API benchmark and automated checks

The default v0.2.0 source application completed all eight benchmark scenarios with no
configuration overrides: idle, one CR3, three sequential CR3s, a three-CR3 nested ZIP,
three repeated jobs, cancellation, actual corrupt-decoder rejection and simulated
low-memory policy rejection. Ten committed full-resolution JPEGs passed geometry,
RGB/orientation/ICC/hash checks. Six repeated outputs of sample 1 match the isolated
baseline's decoded pixels, quantization and geometry. Portrait samples were 3692x5536;
the landscape sample was 5536x3692. Source files remained unchanged and no partial or
extracted-RAW staging files remained. The policy simulation raised the configured reserve;
it did not exhaust the host's physical RAM.

| Source scenario | Outcome | Sampled app-tree peak | Max conversion workers | Workspace peak |
|---|---|---:|---:|---:|
| Idle | Ready | 74.01 MiB | 0 | <0.01 MiB |
| Single CR3 | Completed | 412.62 MiB | 1 | 37.84 MiB |
| Sequential three-CR3 batch | Completed | 426.25 MiB | 1 | 118.26 MiB |
| Nested ZIP, three CR3s | Completed | 423.03 MiB | 1 | 118.26 MiB |
| Three repeated jobs | Completed | 398.23 MiB | 1 | 70.48 MiB |
| Cancellation | Cancelled, clean staging | 116.18 MiB | 1 | 70.30 MiB |
| Deliberate corrupt bytes | Decoder rejection | 115.63 MiB | 1 | <0.01 MiB |
| Simulated low-memory policy | Safely rejected | 74.28 MiB | 0 | <0.01 MiB |

Minimum available physical RAM during successful source native workloads was 1.89 GiB.
The normal host background load was not fixed; this is the observed remaining RAM, not
an advertised minimum required to start. The v0.1.0 baseline API reported about 78.35 MiB
idle and rejected real jobs with zero converter workers under its stock fixed guard.
Its failed workload peaks cannot be compared as if it had performed the same conversions.
Reports: `test-results/memory-baseline-v0.1.0-verified.json`,
`test-results/memory-optimized-source-v0.2.0.json` and
`test-results/memory-api-source-comparison-v0.2.0.json`.

Checks executed: `python -m pytest tests/unit tests/integration -q`: 101 passed,
1 skipped, one existing Starlette TestClient deprecation warning (48.97 s).
`python -m pytest tests/e2e -q`: 12 passed (52.75 s). Ruff lint and format checks pass.
The skipped standardized camera/mode fixture gate is distinct from the real private API
benchmarks; the private inputs lack the broader matrix and are not redistributed.

Recommended configuration on the measured 8 GB (7.4 GiB usable) Windows host is the default
single worker and 768 MiB reserve for files comparable to these 20.44 MP samples. This is
now demonstrated with real originals under the recorded background load. Higher-resolution
or different-camera files may require more memory; the provisional estimate, live pressure
checks and per-worker caps still apply. No universal installed/free RAM minimum or stable
speedup is established from three images and one machine. Keep the reserve and benchmark
representative camera files with the reusable harness before making a hardware promise.

## Packaged v0.2.0 validation

The onedir Windows x64 release built successfully and passed its frozen runtime smoke
with Python removed from the child PATH, including native versions, static asset byte
comparison, authenticated resource diagnostics and actual corrupt-decoder rejection.
The ZIP passed CRC/name checks and its SHA-256 sidecar matched independently.
Output: `dist/v0.2.0/LocalRAW-v0.2.0.exe`, plus the 32.58 MiB/301-file
`dist/LocalRAW-v0.2.0-windows-x64.zip` and `.zip.sha256`. SHA-256:
`bec79ec2b8219e16716d6e9fe43742c76a591fddec38a5f2b53311d9546d22ae`.
The preserved v0.1.0 ZIP hash is unchanged. No unversioned distribution was created.

The packaged application then completed all eight production API benchmark scenarios
with default settings and no installed Python on its child PATH:

| Packaged scenario | Outcome | Sampled app-tree peak | Max converter workers |
|---|---|---:|---:|
| Idle | Ready | 78.60 MiB | 0 |
| Single CR3 | Completed | 417.40 MiB | 1 |
| Sequential three-CR3 batch | Completed | 427.88 MiB | 1 |
| Nested ZIP, three CR3s | Completed | 436.95 MiB | 1 |
| Three repeated jobs | Completed | 413.16 MiB | 1 |
| Cancellation | Cancelled safely | See report | 1 |
| Deliberate corrupt bytes | Actual decoder rejection | See report | 1 |
| Simulated low-memory policy | Safely rejected | See report | 0 |

Ten full-resolution JPEGs passed RGB, expected geometry, normalized orientation, ICC,
SHA-256 and actual JPEG 4:4:4 component-sampling checks. Six sample-1 outputs match the
baseline's decoded pixels, dimensions, quantization and sampling exactly; generated ICC
timestamps explain whole-file hash differences. Original hashes remained unchanged, and
all cases left zero partial or staged RAW files. Application trees contained at most
three processes: one HTTP server, one converter, and one Windows helper/console process. There
were no duplicate servers or converter workers.

Production pixel admissions observed 2.219-2.302 GiB available RAM, below the previous
3 GiB floor. Minimum remaining available RAM during the real packaged workloads was
1.937 GiB. This substantiates these samples on this 8 GB host under the recorded load,
not a universal minimum or success under arbitrary pressure.

Packaged workers reported Windows lifetime peaks of 366.07-366.69 MiB, separate from
the simultaneous sampled app-tree peaks above. Frozen-runtime overhead makes these
slightly higher than the isolated source-only conversion probes; these metric scopes
must not be mixed into a before/after percentage.

An additional focused cancellation ran for two seconds into native processing: the
worker reached a Windows lifetime peak of 256.18 MiB and the app tree reached 336.45 MiB.
Cancellation returned HTTP 200, completed in 2.390 s (including the configured 2 s grace),
cancelled all three files, left no partial/extracted RAWs and reported zero converters
afterward. This supplements the default early-header cancellation scenario.

Reports: `test-results/memory-optimized-v0.2.0.json`,
`test-results/memory-packaged-summary-v0.2.0.json`,
`test-results/memory-api-packaged-comparison-v0.2.0.json`, and
`test-results/memory-native-cancellation-v0.2.0.json`.

Build/test instructions remain in PACKAGING.md and MEMORY_BENCHMARKS.md. No PyInstaller
mode or dependency changes were needed: onedir and early frozen-worker dispatch were
already correct. Clean-machine, other-platform, physical-phone, broader RAW/C-RAW/camera
matrix and reference-scene/ExifTool validation remain open. A versioned package and these
real local results do not constitute a broad release-validation claim.

v0.4 raster workers retain the same admission reserve/concurrency. Header inspection is
bounded before decode; total raster RSS budget is max256MiB,128MiB+40*source_pixels,
including orientation/ICC/alpha/resize/codec/validation/preview overlap. This is conservative,
not a universal memory requirement. WebP is inspected via bounded RIFF headers before
Pillow's whole-encoded-stream open. Source dimensions drive budget even if resizing output.
PDF/DOCX preview workers serialize with conversion and use384MiB default cap,30s timeout,
quotas and bounded request queue; larger legacy image previews request dimension budgets.
Measured v0.4 results and low-headroom rejections: V0_4_VALIDATION.md. No RAW defaults,
reserves, concurrency or ZIP_STORED policy changed.
