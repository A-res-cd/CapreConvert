# CapreConvert implementation handoff

## Current v1.0.0 delivery

Homepage now has native grouped input/output selects and one Open converter action.
Explicit normalized source/target IDs and image/document catalog are additive capabilities;
support/availability comes only from the server. ZIP is a RAW container, JPG/JPEG one option.
Pending selection cannot change files/jobs/settings. Routes, history, aliases, previews,
direct/ZIP downloads and ownership remain. Sidebar has one Convert files entry plus
settings/history/preview links, preserving mobile/Escape/focus/collapse/theme behavior.

Changed formats.py/api.py metadata, static picker.js/converters.js/app.js/navigation.js/
index.html/styles.css, tests, README and UI/API documentation. Engines and defaults unchanged.
Version is1.0.0 from the single source; both console aliases remain. No commit or push.
Backend196 pass/2 source skips in153.30s; browser26 pass in98.01s; lint/format/Node/Prettier
pass. Actual native frozen codecs/documents/previews and browser direct/ZIP/auth checks
passed with compact test caps (384MiB documents,256MiB previews;768MiB reserve unchanged).
Production defaults remain untouched. Default-profile smoke was blocked by host RAM and
large real CR3 was not rerun; earlier real-camera evidence below is historical.

Release: dist/v1.0.0/CapreConvert-v1.0.0.exe and complete folder;
dist/CapreConvert-v1.0.0-windows-x64.zip plus .sha256 (43,245,368bytes;513files).
SHA-256:7e8b580a69a3c31f43248a74cbf6a4d7f226ff2aa92ec58aa0cb0534acfe2fc8.
CRC/hash passed. User explicitly requested deleting other versions: old v0.1-v0.4 packaged
releases and build caches were safely removed after v1 verification. Workspaces, original
inputs, source and historical evidence remain. V1_0_VALIDATION.md has commands/audit/gaps.


## v0.4.0 delivery (historical; packaged artifacts later removed by request)

Implemented nine everyday image operations (six JPEG/PNG/WebP pairs and three same-format
optimizations), nested immutable raster settings, explicit engine/preview/archive registry,
bounded supervised Pillow route, presets/resize/alpha/ICC/EXIF/privacy/savings, generic
Output preview, lazy PDFium pages and safe read-only DOCX paragraphs/tables. One selected
successful file downloads directly; multiple selected outputs use the existing ZIP contract.
Main additions: localraw/raster.py, previews.py; registry/models/config/jobs/worker/uploads/
API integration; shared browser converter/settings/previews/exports; pypdfium2 frozen hooks,
complete native notices; tests and benchmark/frozen-browser drivers. RAW/document encoders,
old artifacts, package/env/workspace/session/browser identities remain compatible.

Source checks and measurements are recorded in V0_4_VALIDATION.md. Windows sync/indexing
exposed transient atomic-manifest rename denial; bounded retries preserve the old committed
manifest, with transient/permanent-denial regression coverage. No commit or push.
Latest backend192 passed/2 source skips (camera manifest and environment-gated LibreOffice
API; native API passed in the configured191-pass run and frozen checks). Source Playwright
21 passed; lint/format pass. Frozen strict smoke passed all9 actual raster operations,
both native document engines, local PDFium/DOCX previews, typed direct downloads and ZIPs.
Frozen browser driver verified actual content/page/image previews, safe text, one/multi export,
refresh and unauthorized denial. Actual private legacy JPEG pixels equal earlier baseline;
landscape/portrait PNGs, exact selected ZIP, unchanged originals and cross-version lock pass.

All7 frozen benchmark cases passed default policy:1.53-3.19s/172-266MiB sampled tree for
moderate/large-image cases. PDF/DOCX previews about1s, cached about20ms. Earlier low-RAM
rejections were retained as evidence; reserves/concurrency were never weakened. Browser
verification prepares conversions before launching Chromium to fit this host's headroom.

Release: dist/v0.4.0/CapreConvert-v0.4.0.exe and complete folder;
dist/CapreConvert-v0.4.0-windows-x64.zip plus .sha256 (43,248,152bytes;512files).
SHA-256:bbbc0125021d10d3afa7fbe03367df19d3bdb97383bfe1b9a2b5d8fcf19e29b0.
Builder and independent CRC/path/hash checks passed; old v0.1/v0.2/v0.3 hashes unchanged.
Final metadata-hint-only refresh verified all20 frozen runtime code objects/dependency versions,
then passed the complete strict smoke again. EXE/native files equal the native-validated bundle;
only app.js wording and release audit metadata differ. Full commands/results/gaps: V0_4_VALIDATION.md. LibreOffice external; PDF-to-DOCX text-only;
DOCX preview content-only; clean-machine/physical-phone/broad-camera/reference-colour gates
remain open. No private fixture or external office engine is packaged.


## CapreConvert v0.3.0 delivery (historical)

Delivered the new selection home, four converter workspaces, DOCX→PDF via external local
LibreOffice, text-based PDF→editable DOCX, full-size CR3→JPG/PNG, and app-wide public
CapreConvert branding. Original CC SVG/wordmark/ICO, browser/CLI/API identity, Windows
product/version/icon resources and new release names are local assets. Existing paper,
indigo/orange design, fonts, responsive themes, RAW previews and selected exports remain.

Compatibility identities were retained: localraw package/localraw-converter distribution,
LOCALRAW_* configuration, LocalRAW application-data workspace/marker/lock, localraw_session,
browser preference keys, API routes and legacy JPEG defaults. capreconvert console entry
is added; both actual installed aliases and frozen --version report CapreConvert0.3.0.
Representative old workspace/session/JPEG/preview/ZIP/export/retry recovery checks pass.
The frozen LocalRAW-v0.2.0 binary was also denied ownership of a live new-app workspace,
while the new app stayed healthy. No workspace move or destructive migration occurred.

Executed final gates: 148 backend tests passed, 1 standardized camera-fixture gate skipped,
one existing Starlette TestClient warning (106.10s); 19 browser tests passed (63.95s).
Real external LibreOffice was enabled for the full backend run. Ruff/format, Node,
Prettier, SVG checks and desktop/mobile/light/dark visual review passed.

New engine hardening covers bounded DOCX ZIP/XML, PDF decompression/page/text/output limits,
active/external content rejection, exact cleanup, editable OOXML and native rendering.
A real API failure exposed long Windows LibreOffice profile paths; verified same-file
8.3 CLI aliases fixed it without relocating data. A shorter-workspace diagnostic handles
unavailable aliases. Frozen DLL search reset and both actual document conversions passed
the packaged smoke with Python removed from the child PATH.

Current release: dist/v0.3.0/CapreConvert-v0.3.0.exe and
dist/CapreConvert-v0.3.0-windows-x64.zip plus .zip.sha256 (37.40MiB, 463 files).
SHA-256: e0d1be9348be96015f9f5e22e1374e7429cbf6f63752425130560e614b2c6b7a.
Staged build/smoke/PE product/version/seven-icon-frame checks, ZIP CRC/names and independent
SHA verification passed. Both old release hashes remain unchanged; private photos and
the external renderer are not in the ZIP.

Frozen real RAW validation passed default legacy JPEG (decoded pixels exactly equal to
the v0.2 baseline) and two PNGs, landscape5536x3692 and portrait3692x5536. Inline previews
remain JPEG; the two-selected-PNG ZIP matches exact full PNG bytes. Originals unchanged,
one converter, no partial/staged RAW leftovers. Default resource settings were kept;
an initial low-headroom rejection was retried only after available RAM recovered.

LibreOffice remains external. This workspace has a verified project-local26.8.1.1 image at
.tools/libreoffice/program/soffice.com; use the app's --libreoffice flag or JSON/legacy env
setting. It is not bundled/system-installed/downloaded at runtime. PDF→DOCX is text-only
without OCR/images/tables/precise layout; renderer/fonts affect DOCX→PDF layout. Clean-machine,
physical-phone/LAN, broader camera/layout, other-platform and reference color/ExifTool gates
remain open. Old binaries cannot safely understand new jobs for in-place downgrade.

Full commands/evidence/limits: V0_3_VALIDATION.md; compatibility: V0_3_MIGRATION.md.
Private ignored reports: test-results/package-smoke.json and
test-results/capre-v0.3-native-raw-validation.json. Historical LocalRAW evidence below keeps
its original names and observed results; the rebrand does not rename previous releases.

## RAM optimization and v0.2.0 delivery (historical)

Implemented the requested investigation and memory changes in the existing FastAPI/rawpy
architecture. Phase 1 findings, ordered plan, policy rationale, measurements and limitations
are recorded in MEMORY_OPTIMIZATION.md. Only one HTTP server is present; there is no Flask
or development reloader. Existing uploads, ZIP staging, quotas, authenticated file-backed
downloads and bounded preview containers remain.

Highest-impact changes: exact 16-bit lookup transfer into bounded Pillow tiles (no extra
full RGB8 intermediate); explicit closure of pixel buffers on all paths; full validation
buffers freed before preview-only scaled JPEG decode; source worker imports avoid FastAPI.
The fixed 3 GiB startup floor was replaced with 256 MiB header inspection, conservative
pixel budgets, a configurable 768 MiB additional safety reserve and correct future-growth
accounting. Concurrency defaults to one and requested parallelism waits for headroom.
Bounded-rate monitoring records process-tree/worker peaks and stops unsafe workers under
caps/pressure. New authenticated GET /api/v1/resources is additive and exposes no paths/PIDs.
Dimensions, AHD, white balance, color transfer, JPEG quality/4:4:4 and metadata policy remain.

Before/after direct real 20.44 MP worker peak: 357.242 -> 357.109 MiB (effectively flat,
native AHD dominates). Explicit synthetic 24 MP transfer probe: 340.824 -> 274.109 MiB,
19.575% lower. Source import-only median: 45.79 -> 19.08 MiB across three trials.
Real full JPEGs differ only in two generated ICC timestamp bytes; decoded pixels,
geometry, quantization and sampling match. Single-pair timings are not stable speed claims.

Three real private retained-upload samples now have provenance/hashes/expected geometry
in ignored test-results/memory-inputs/manifest.json. They are not redistributed. The
separate standardized camera/mode pytest manifest is still missing, so that gate remains
skipped; it does not invalidate the separate actual private benchmark results.

Executed validation:
- `python -m pytest tests/unit tests/integration -q`: 101 passed, 1 skipped, one existing
  Starlette TestClient deprecation warning in 48.97 s.
- `python -m pytest tests/e2e -q`: 12 passed in 52.75 s. Ruff lint/format checks pass.
- Baseline immutable v0.1.0 API, optimized source API and optimized frozen API benchmarks
  cover idle, real single/batch/ZIP/repeat, cancellation, corrupt input and simulated
  low-memory policy. v0.1.0 rejected photos under its stock 3 GiB floor; both optimized
  targets completed all real conversion cases and exercised safe failures/cancellation.
- The packaged target verified 10 full-resolution JPGs including portrait geometry,
  ICC/orientation, SHA-256 and actual 4:4:4 sampling; all source hashes remained unchanged.
  Sample 1's six API exports match baseline decoded pixels/geometry/quantization/sampling.
- Packaged idle 78.60 MiB (baseline 78.35, effectively unchanged). Sampled app-tree peaks:
  single 417.40, batch 427.88, ZIP 436.95, repeat 413.16 MiB. Exactly one converter ran.
  Real admissions observed 2.219-2.302 GiB available RAM, below the old 3 GiB rule.
- Additional cancellation during native processing reached a 256.18 MiB worker peak,
  cancelled all three files in 2.390 s including grace, and left zero partial/staged RAWs
  or converter processes. Policy simulation did not exhaust actual OS memory.
- `python scripts/build-package.py`: v0.2.0 onedir build, frozen smoke (Python removed
  from child PATH), ZIP CRC/names and SHA-256 passed. Independent archive/hash verification
  passed; original v0.1.0 ZIP hash remains unchanged.

Current launch: dist/v0.2.0/LocalRAW-v0.2.0.exe. Share the full folder or
dist/LocalRAW-v0.2.0-windows-x64.zip (32.58 MiB, 301 files) with its .zip.sha256 sidecar.
SHA-256: bec79ec2b8219e16716d6e9fe43742c76a591fddec38a5f2b53311d9546d22ae.
Keep _internal beside the executable. No unversioned build was recreated.

Reproduction: MEMORY_BENCHMARKS.md and PACKAGING.md. Reports are under ignored test-results:
memory-baseline-v0.1.0-verified.json, memory-probe-comparison.json,
memory-optimized-source-v0.2.0.json, memory-optimized-v0.2.0.json,
memory-packaged-summary-v0.2.0.json and memory-cancel-under-load-v0.2.0.json.
The default single worker/reserve is demonstrated for these 20.44 MP photos on this
8 GB (7.4 GiB usable) Windows host. No universal minimum or broader camera/mode promise.
Clean-machine, physical-phone, secondary-platform, reference-scene and ExifTool gates remain.

## Versioned packaging update (v0.1.0, historical)

`localraw/__init__.py` now supplies both Python project metadata and release names.
`scripts/build-package.py` builds and smoke-checks a staged native bundle, creates and
checks its ZIP, writes a SHA-256 sidecar, then publishes `dist/v<version>/` and
`dist/LocalRAW-v<version>-<platform>-<architecture>.zip`. The executable is named
`LocalRAW-v<version>.exe` on Windows. A release manifest and launch instructions travel
inside the folder. Existing releases are refused.
The smoke script discovers the versioned executable and checks its reported app version.
See PACKAGING.md for the build command and version source.

Executed: the versioned Windows x64 build and frozen-app smoke passed. Independent ZIP
CRC, folder-prefix, manifest/version and SHA-256 checks passed (301 files, 32.6 MiB ZIP).
The dynamic setuptools metadata resolves to 0.1.0; Ruff passed. A second build correctly
refused the existing release before touching it. SHA-256:
`263f713fbb405cae62b06a9ed1c564e5a311cd3cf4a4164be298087e8662df97`.

At the user's request, removed the obsolete `dist/LocalRAW`, `dist-preview`, `dist-styled`,
`build/localraw`, `build-preview` and `build-styled` directories after verification.
The old styled application had no children or active jobs (one failed 88-file batch),
and was closed before deleting its bundle. The separate workspace was preserved.

The reported memory failure was confirmed against the running configuration: 7.40 GiB
usable RAM, 0.71 GiB available during the check. Admission requires at least 3 GiB free
(2 GiB OS reserve plus 1 GiB worker), with a larger budget for larger images. Advised
closing heavy applications/restarting and retrying retained inputs. No memory guard was
lowered. Real-camera and clean-machine validation gates remain open.

## Repository styling update (previous delivery)

Styling reference is the verified latest GitHub push on `aresver-css`, commit
`075c146985a71b375967d824a7b16575a9bc3211` (2026-10-17 10:16:22 Asia/Manila).
The default `main` branch is older. Repository metadata, branch tips and public PushEvents
were checked; source details and exact tokens are in STYLE_REFERENCE.md.

Replaced the green theme with paper surfaces, indigo type, orange actions, ruled lines,
asymmetric card corners, outlined status stamps and locally bundled Fraunces fonts.
Added a compact header and collapsible sidebar with a keyboard/mobile drawer; existing
conversion, preview, selection and export IDs/flows remain. New navigation.js is local-only.
The font license is bundled; LocalRAW branding is retained.

Checks: `.venv\Scripts\python.exe -m pytest tests/e2e -q` — **12 passed** in 210.35 s.
Visual review fixed a transient upload-zone theme contrast; targeted navigation/theme tests
rerun — **2 passed** in 5.96 s. Light/dark/mobile screenshots inspected; Node, Ruff and
Prettier checks pass. No backend processing behavior changed; no extra RAW compatibility
claim is made. Existing missing-real-camera/physical-phone gates remain open.

The preview executable is running, so the latest Windows delivery is staged separately:
**dist-styled/LocalRAW/LocalRAW.exe**. Build passed (70.83 s), then
`.venv\Scripts\python.exe scripts/smoke-package.py --dist-dir dist-styled/LocalRAW` passed,
including byte-for-byte bundled CSS, JS, fonts and license assets. Finish current jobs and
close the previous app before launching the new copy with the default port/workspace.

## Preview/selection update (previous delivery)

Added the requested separate Preview & export container: large image viewer, previous/next
navigation, paginated thumbnails, per-photo checkboxes, Select all / Clear, counts, and
restoration of the viewed photo and selected IDs after refresh. A job-action link jumps
directly to it. Users develop the batch locally first, then choose which JPGs to export.
One selection downloads a full-resolution JPG; multiple selections prepare/download a ZIP
containing only those full-resolution JPGs with original folder paths. Existing individual
and whole-batch downloads remain available.

Workers create bounded 1280px previews and 320px thumbnails, omitting capture/GPS EXIF and
retaining sRGB ICC and normalized orientation. They never replace full-resolution exports.
Preview failure preserves successful full JPGs. Ownership/CSRF, quotas, atomic packages,
one global selection-packaging lock, three-entry export caches, deletion leases and restart
preservation cover the new endpoints. Older batches without derivatives can be retried for
previews. Fixed a worker-exit race that could discard a final IPC error/result message.
Launcher links now restore an existing valid browser session before exchanging a new
bootstrap credential, keeping owned batches and export preferences visible after updating.

Executed checks for this update:
- `.venv\Scripts\python.exe -m pytest tests/unit/test_previews.py tests/integration/test_preview_exports.py -q`: 12 passed.
- `.venv\Scripts\python.exe -m pytest tests/unit/test_supervisor.py tests/e2e -q`: 10 passed after fixing the worker-exit race.
- `.venv\Scripts\python.exe -m pytest -q`: **81 passed, 1 skipped, 1 warning in 81.73 seconds**.
- Ruff lint and formatting checks: pass; Node syntax and Prettier checks: pass.
- Preview desktop/mobile screenshots inspected. Successful images still use the explicitly
  named test worker/decoder doubles; the missing real-CR3 gate remains skipped.
- A fresh-launch-link browser regression verifies that an existing valid session retains
  owned batches and export choices. Ten browser tests now cover the complete workflow.

The previous `dist/LocalRAW/LocalRAW.exe` was found running. Its loaded distribution and
ongoing work were left intact. Updated build target: **dist-preview/LocalRAW/LocalRAW.exe**.
Build: `.venv\Scripts\python.exe -m PyInstaller packaging/localraw.spec --noconfirm --distpath dist-preview --workpath build-preview`.
Smoke: `.venv\Scripts\python.exe scripts/smoke-package.py --dist-dir dist-preview/LocalRAW`.
Final updated build passed (48.69 seconds). Final smoke passed with Python removed from
the child PATH, a temporary working directory/workspace, the new protected preview/export
routes, and byte-for-byte source/static asset comparison. Finish jobs and close the old app
before launching the updated executable with the default port/workspace. Packaging details:
PACKAGING.md. The original running distribution was not replaced or stopped.

Changed source: localraw/conversion.py, jobs.py, api.py, config.py, models.py;
static/index.html, styles.css, app.js, and new previews.js. Added derivative/API/browser
tests and the supervisor regression; updated docs and the configurable smoke script.

## Original baseline delivery (historical record)

Implemented on 2026-10-25 in the designated FileConverter directory. Initial inspection
found an empty directory, with no code, AGENTS.md or planning docs. Planning docs were
created before application code. The supplied AGENTS.md communication style was retained.

## Delivered

- Full-size CR3 rendering through rawpy/LibRaw in per-image spawned workers: AHD,
  camera/auto white balance, one orientation application, explicit sRGB transfer,
  matching embedded ICC, 8-bit JPEG 4:4:4, quality 70–100, validated atomic publication.
- Sequential streamed binary uploads, multiple direct files and ZIPs, nested folders,
  selected extraction/CRC, mixed-content feedback, deterministic case/Unicode collisions.
- Persisted session-owned queue, progress stages/counters, cancellation, partial success,
  JPEG/ZIP/report attachment downloads, retention, deletion leases, restart interruption,
  explicit retained-input retries and reference protection.
- Localhost bootstrap, explicit LAN pairing, separate browser owners, CSRF, Origin/Host
  validation, rate limits, bounded bodies, private workspace and exclusive instance lock.
- Resource admission/reservations, disk checks, worker timeout/crash/RSS protection,
  archive directory/dictionary guards, partial cleanup and retained JPEG integrity hashes.
- Responsive accessible keyboard/touch workflow, mobile layouts, dark mode, exact upload
  byte progress, batch history pagination and restoration after refresh. No external assets.
- Windows launchers, target-OS one-folder spec, bundled native libraries/assets/notices.

## Phase status

| Phase | Implementation/check status | Remaining acceptance gate |
|---|---|---|
| 1 Foundation | Implemented; startup/config/workspace/health/static checks pass | None for this host |
| 2 Conversion | Implemented; rendering-contract, transfer/profile, atomicity and corrupt-native-input checks pass | Real RAW/C-RAW fixtures |
| 3 ZIP | Implemented; nested/mixed/multi-archive, malicious inputs, CRC and output integrity pass | Real camera ZIP batches |
| 4 API | Implemented; ownership, upload retry, queue, cancellation, crash, timeout, idempotency and recovery pass | Real-camera throughput |
| 5 Frontend | Implemented; six Chromium browser tests pass | Physical Android/iPhone |
| 6 Reliability | Implemented; adversarial and deterministic resource tests pass | Real RSS calibration; no hard OS sandbox claimed |
| 7 Packaging | Windows one-folder built; refreshed-build smoke passed | Clean machine, real frozen conversion/cancel |
| 8 Final validation | Full automated suite passes; visual/offline-request checks performed | Camera matrix, benchmarks, secondary OS and real phones |

Implementation is delivered; release acceptance is incomplete. Do not describe the converter
as camera-compatible or release-validated until the remaining real-fixture gates pass.

## Actual environment and versions

Windows 11 x64, build 10.0.26200; system Python 3.13.6 was available but not used as baseline.
Project Python: 3.12.13 x64. Node 22.18.0. Locked runtime: FastAPI 0.162.0, Uvicorn 0.54.0,
pydantic 2.14.1, rawpy 0.27.1, **loaded LibRaw 0.22.1**, Pillow 12.3.0, NumPy 2.5.4,
psutil 7.2.2. Checks/build: pytest 9.1.1, HTTPX 0.28.1, Playwright 1.64.1 / Chromium
headless 156.0.8078.4, PyInstaller 6.22.3. requirements.lock pins/hashes all 37 dependencies.
No ExifTool or real CR3 samples were supplied. ExifTool field mapping was tested with doubles.

Physical RAM: 7.4 GiB; one observed available-memory reading was 0.81 GiB. Production
admission requires 2 GiB for OS/server plus at least 1 GiB for a worker, increasing to
64 bytes/pixel. The app correctly refuses work when this cannot fit. Close other apps for
real conversion. Admission doubles in tests only authorize tiny deterministic test files;
they do not weaken the production reserve or substantiate real resource use.

## Executed commands and results

Commands below run from the project root in PowerShell. Paths are exact relative paths.

| Command | Actual result |
|---|---|
| `uv venv --python 3.12 .venv` | Downloaded Python 3.12.13 x64; environment created |
| `uv pip compile pyproject.toml --extra dev --generate-hashes --output-file requirements.lock` | Resolved and pinned 37 packages |
| `uv pip sync requirements.lock --python .venv\Scripts\python.exe --require-hashes` | All 37 installed successfully |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_foundation.py -q` | Initial phase gate: 4 passed |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_conversion.py -q` | Initial phase gate: 9 passed |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_archives.py -q` | Initial phase gate: 23 passed |
| `.venv\Scripts\python.exe -m pytest tests/integration -q` | Initial gate: 6 passed after deterministic admission setup |
| `.venv\Scripts\python.exe -m playwright install chromium` | Chromium/FFmpeg installed successfully |
| `.venv\Scripts\python.exe -m pytest tests/e2e -q` | Latest isolated browser run: 6 passed in 18.94 s |
| `.venv\Scripts\python.exe -m pytest -q` | **Final source suite: 64 passed, 1 skipped, 1 warning in 32.38 s** |
| `.venv\Scripts\python.exe -m ruff check localraw tests scripts packaging/entrypoint.py` | Pass |
| `.venv\Scripts\python.exe -m ruff format --check localraw tests scripts packaging/entrypoint.py` | 31 files formatted; pass |
| `node --check localraw/static/app.js` | Pass |
| `node --check localraw/static/api.js` | Pass |
| `npx --offline prettier@3.6.2 --check localraw/static/index.html localraw/static/styles.css localraw/static/app.js localraw/static/api.js` | All files pass |
| `.venv\Scripts\python.exe -m localraw --port 80 --no-browser` | Expected rejection: port must be at least 1024 |
| `.venv\Scripts\python.exe -m PyInstaller packaging/localraw.spec --noconfirm` | Final Windows one-folder rebuild passed (43.59 seconds) |
| `.venv\Scripts\python.exe scripts/smoke-package.py` | Final smoke passed with Python removed from child PATH and an empty working directory; served assets match source bytes |

One skipped test is the explicit real-camera gate: no tests/fixtures/manifest.json exists.
Starlette TestClient warns that HTTPX support is deprecated; HTTPX 0.28.1 remains operational.
PyInstaller warned about optional tzdata, which this application does not use (timestamps are
UTC epoch seconds and formatted by browsers). Native decoder imports succeeded in the build.

Failures found and corrected during implementation: initial API tests hit the real RAM
admission floor; first browser attempt preceded Chromium download completion; two hardening
test doubles needed correction; one newly inserted archive test needed its boundary moved;
smoke environment handling needed case-independent SYSTEMROOT lookup. Final executed gates
listed above passed. Failed intermediate runs were never treated as passing evidence.

## Validation limits and artifacts

Real rawpy was exercised against corrupt bytes and safely rejected them. All successful API
and UI images use an explicitly named spawned-worker double; rendering contracts use a rawpy
double. No camera model, compressed RAW mode, real orientation, color quality, camera metadata,
resource benchmark or real packaged conversion has been substantiated. See tests/fixtures/README.md
for required user-owned/licensed portrait and landscape RAW/C-RAW samples, camera/mode,
provenance, SHA-256 and expected visible dimensions. No unclear-rights files were downloaded.

Chromium desktop and 320/390px mobile layouts were exercised; screenshots were inspected.
The full browser conversion test permits only same-origin network requests and verifies that
all observed requests are local. This requires the host to stay reachable; no service worker
or browser-only converter is claimed. Physical iPhone Safari, Android Chrome, Windows 10,
macOS, Linux, disconnected-host behavior and a clean Windows machine remain untested.

Artifacts: test-results/desktop-results.png, mobile-320.png, mobile-390.png and package-smoke.json.
Build: dist/LocalRAW/LocalRAW.exe plus the complete _internal folder. Upstream notices are in
_internal/notices. Review THIRD_PARTY_NOTICES.md before redistribution; optional ExifTool is
not bundled. The base converter stays usable without it and reports metadata omissions.

## Decisions and operational limits

- API times are UTC Unix seconds. Polling: 1 second active, 5 seconds hidden; terminal jobs stop.
- One FIFO supervisor handles a batch at a time, with up to 2 spawned file workers globally.
  Memory accounting is conservative and may reduce concurrency. RSS sampling is not a sandbox.
- Cancellation signals workers, then terminates after the default 2-second grace. Queued jobs
  cancel immediately. Validated successes remain downloadable and can be packaged after cancel.
- Uploads expire after 1 hour if unreferenced; terminal jobs after 24 hours. Cleanup runs every
  10 minutes, including while conversions run. Downloads retain deletion leases.
- Restart marks active work interrupted and never automatically repeats it. JPEG hashes are
  checked; staging/uncommitted files and .part files are removed. Corrupt manifests are ignored.
- Additional archive guards: 32 MiB central-directory data before entry-list allocation and
  64 MiB maximum LZMA dictionary. Unsupported-file feedback counts every skipped entry while
  retaining only the first 100 names per archive to bound manifests. Nested ZIPs are skipped.
- Windows workspace ACLs retain the current user and SYSTEM; POSIX mode 0700. Choose a dedicated
  workspace. No server endpoint accepts arbitrary host paths.
- Base metadata uses whitelisted EXIF fields, ASCII/truncated text with specific warnings,
  normalized Orientation=1, and opt-in GPS. Actual ExifTool integration needs a tested executable.
- No automatic firewall/router changes. LAN HTTP lacks transport confidentiality. See SECURITY.md
  for private-network firewall, guest Wi-Fi isolation, VPN, interface, sleep and mobile-upload notes.

## Startup and packaging

Local: `.\.venv\Scripts\python.exe -m localraw`

LAN: `.\.venv\Scripts\python.exe -m localraw --lan`

Build: `.\.venv\Scripts\python.exe -m PyInstaller packaging/localraw.spec --noconfirm`

Built app: `.\dist\LocalRAW\LocalRAW.exe` (add `--lan` for paired phone browsers).
Keep the entire application folder. The default workspace is the current user's application-data
LocalRAW/workspace directory; `--workspace` and `--config` allow validated overrides.

Important implementation files: localraw/app.py, api.py, jobs.py, worker.py, conversion.py,
archives.py, security.py, uploads.py, storage.py, config.py, models.py, metadata.py,
static/index.html, static/styles.css, static/app.js and static/api.js. Build/setup files:
pyproject.toml, requirements.lock, packaging/localraw.spec, scripts/ and README.md.
