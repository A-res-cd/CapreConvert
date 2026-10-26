# Ordered implementation

Current work: CapreConvert v1.0.0. Follow V1_0_PLAN.md for the picker, regression, packaging
and explicitly authorized old-release cleanup gates. v0.4.0 work below is historical.

Previous release: CapreConvert v0.4.0. Follow [V0_4_PLAN.md](V0_4_PLAN.md), gates A-J:
contracts, raster engine/semantics, resources/recovery, committed previews/direct exports,
browser, measured performance, verification, versioned packaging and evidence.
Historical release records below remain intact.

The CapreConvert v0.3.0 extension follows the ordered plan in V0_3_PLAN.md: preserve
identities and legacy contracts, add format-aware jobs, validate document/PNG engines,
integrate API/resources/recovery, build the new home/workspaces and public branding,
then run migration/hardening/browser gates before packaging. v0.1.0/v0.2.0 artifacts
remain immutable historical LocalRAW releases. Executed v0.3.0 gates will be recorded
in CODEX_HANDOFF.md when complete.

1. Foundation: settings, dependencies, ownership, lifecycle, page, health. Gate: unit smoke.
2. RAW engine: isolated worker, rendering, metadata, atomic JPEG. Gate: deterministic tests;
   mark actual camera checks blocked if no fixtures, continue independent implementation.
3. ZIP: inspection, selected extraction, collision handling, committed ZIP. Gate: ZIP tests.
4. API: sessions, staged bytes, scheduler, downloads, cancel/restart. Gate: integration tests.
5. UI: full browser workflow and recovery. Gate: executed Playwright checks.
6. Hardening: adversarial/resource/reliability tests. Gate: full automated suite.
7. Packaging: launchers, spec/native assets, freeze support. Gate: target Windows build/smoke.
8. Validation/report: final commands and evidence; distinguish implementation from release
   acceptance. Broader camera/mode fixtures, clean-machine and physical-mobile tests remain
   explicit acceptance gaps; local private benchmark inputs are now available.

Progress and command results: docs/CODEX_HANDOFF.md.

Delivered: phases 1–6 implementation and automated gates; phase 7 Windows one-folder build
and smoke launch. Original source suite: 64 passed, 1 explicitly skipped real-fixture gate.
Phase 8 automated/browser/visual checks executed. Physical-phone, clean-machine,
secondary-platform and broad camera/mode acceptance remain open; see CODEX_HANDOFF.md
and VALIDATION.md.

Preview/selective-export extension delivered: dedicated viewer/gallery, persisted selection,
full-JPG/specific-subset ZIP exports, protected derivatives, resource bounds and restart/session
preservation. That extension's full suite passed 81 tests with one skipped fixture gate.
Styling and versioned packaging followed; v0.1.0 Windows build/smoke passed. Old
unversioned build folders were later removed at the user's request.

Memory optimization extension follows the same gates: inspect and record the baseline,
reduce buffer overlap, implement adaptive admission, run resource/adversarial tests, then
validate the source UI and versioned package. Implemented exact tiled sRGB conversion,
explicit image-buffer closure, scaled preview decoding, lazy source-worker imports,
dimension-aware budgets, future-growth accounting, pressure handling and memory diagnostics.
No exported JPEG quality, visible dimensions, rendering or metadata policy was reduced.

Current backend gate: **101 passed, 1 skipped in 48.97 s**. The skipped pytest camera gate
requires its own `tests/fixtures/manifest.json`; it does not negate the separate real
private benchmarks now available. Three private retained-upload CR3 inputs have recorded
provenance, hashes and expected landscape/portrait dimensions in ignored
`test-results/memory-inputs/manifest.json`. Direct real 20.44 MP peak was essentially flat
(357.242 to 357.109 MiB); a synthetic 24 MP encode-stage probe fell from 340.824 to
274.109 MiB (19.575%). Before/after full-resolution JPEG decoded pixels and encoding
settings match; only generated ICC creation-time bytes differ. These results do not
establish a universal RAM minimum or a broader camera/mode support claim.

The eight-scenario source API benchmark run completed: idle, real single-file, sequential
batch, multi-RAW ZIP and repeated sessions completed; cancellation, corrupt-input rejection
and a configured low-memory policy rejection behaved as expected. Originals' hashes were
unchanged. The low-memory case changes the reserve rather than exhausting physical RAM.
Current browser regression passed **12 tests in 52.75 s**. Optimized v0.2.0 packaging
and frozen-app smoke, ZIP CRC and SHA-256 verification passed (301 files, 32.58 MiB ZIP).
All eight benchmark scenarios also passed against the package; normal workloads used the
default configuration. Single/batch/ZIP/repeated workloads produced ten verified full-resolution
4:4:4 JPEGs, exactly one converter at a time. Idle process-tree RSS was 78.60 MiB and
successful workload peaks were 413.16-436.95 MiB. Render admissions observed
2.219-2.302 GiB available RAM, below the old fixed requirement for these samples.
Additional native cancellation under load reached 256.18 MiB worker RSS and 336.45 MiB
tree RSS, then cancelled all three files in 2.390 s with no partial/staged leftovers or
remaining converter. The HTTP process and one Windows helper/console process are included
in process-tree measurements. Full evidence is in CODEX_HANDOFF.md and MEMORY_OPTIMIZATION.md.
Clean-machine, physical-phone, broader camera/mode, secondary-platform and reference
color/ExifTool acceptance remain open; completed local benchmark gates do not imply them.

CapreConvert v0.3.0 extension completed its ordered gates: 148 backend checks passed,
one standardized camera-fixture gate skipped; 19 browser checks passed; actual document
engines, PNG output/exports, forward legacy recovery, both console aliases and cross-binary
workspace exclusion verified. The versioned frozen build, PE branding/icon/version checks,
both real document conversion smokes, real JPG/PNG fixtures, ZIP CRC and checksum passed.
No original/release/workspace identity was removed or silently moved. Exact artifact paths,
commands and remaining acceptance gaps are in V0_3_VALIDATION.md and CODEX_HANDOFF.md.

CapreConvert v0.4.0 follows [V0_4_PLAN.md](V0_4_PLAN.md), in gates A-J. Executed evidence belongs in V0_4_VALIDATION.md.


v0.4.0 gates A-J delivered: nine real raster codecs/optimizations, registry/immutable settings,
bounded worker/resources/recovery, image/PDF/DOCX committed previews, direct/ZIP browser
workflow, measured reuse-vs-reopen probe, native/frozen/browser checks and versioned package.
Latest backend192 pass/2 source skips (native API separately passed with configured engine),
21 browser pass; strict frozen smoke and real private JPG/PNG checks pass. Seven default-policy
frozen benchmark cases complete, CRC/SHA verified, older releases unchanged. Broader acceptance
gaps remain explicitly recorded in V0_4_VALIDATION.md.


v1.0.0 picker/navigation/refactor and authorized release cleanup complete. Backend196 pass/
2 skips, browser26 pass; native frozen smoke/browser/export checks pass under documented
compact caps with unchanged reserve/defaults. Default smoke RAM blocker, artifacts/hash,
remaining broad acceptance and cleanup audit are recorded in V1_0_VALIDATION.md.
