# CapreConvert v0.4.0 validation

Version comes from localraw/__init__.py. No commit or push. Older v0.1/v0.2/v0.3 release
ZIPs retain their SHA-256 values recorded in test-results/v04-prior-releases.json.

Implemented: all six cross-format static JPG/PNG/WebP operations plus three same-format
optimizations; unchanged CR3 JPG/PNG and document engines. Nested immutable raster settings,
colour/alpha/orientation/privacy normalization, resize/presets/codec controls, savings,
committed-output image/PDF/DOCX previews and generic direct/selected exports. See
OPTIMIZATION_PREVIEWS.md, V0_4_MIGRATION.md and API_SPECIFICATION.md for exact semantics.

## Source checks executed

- uv hashed compile/sync installed pypdfium2 5.14.0 (PDFium156.0.8076.0). Existing dependency
  pins remained. Editable package/console aliases both report CapreConvert0.4.0.
- Full backend with LOCALRAW_TEST_LIBREOFFICE configured:189 passed,1 standardized camera
  fixture gate skipped,1 existing Starlette/HTTPX deprecation warning in220.81s. After this,
  two Windows manifest retry regressions were added: the next configured full run passed
  191 checks/1 camera skip in238.80s. Final run after opaque-alpha WebP regressions:
  192 passed,2 skipped,1 existing warning in145.32s. The second skip is the API native
  LibreOffice test without LOCALRAW_TEST_LIBREOFFICE in that run; it passed in the configured
  run, and both actual document API engines passed again in the frozen smoke/browser driver.
  The final run includes the two new opaque RGBA WebP lossy/lossless cases.
- Playwright full suite:21 passed in84.12s. Real raster browser conversions plus desktop/
  320px controls, alpha, direct/ZIP, refresh and existing RAW/document flows. Native PDFium
  pages and OOXML content render in supervised workers; RAW/document conversion browser
  fixtures remain explicit doubles. Actual source document engines run separately.
- Focused latest cache/engine/recovery tests:32 passed in16.16s; cache schema/restart tests:
  6 passed in14.98s; manifest/foundation/legacy/raster-preview integration:16 passed in16.24s.
  These overlap suites and are not added to the full-suite total.
- Ruff lint/format, Node syntax and Prettier checks passed. Final commands:
  `.venv\Scripts\python.exe -m ruff check localraw tests scripts packaging/entrypoint.py`,
  `.venv\Scripts\python.exe -m ruff format --check localraw tests scripts`,
  `npx --offline prettier@3.6.2 --check localraw/static/index.html localraw/static/app.js localraw/static/converters.js localraw/static/previews.js localraw/static/styles.css`.
  Source/frozen aliases and actual package --version report CapreConvert0.4.0.

Tests include all actual raster codecs, .jpeg alias/mismatch, resize/orientation/no-upscale,
transparent JPEG background, RGBA/palette/grayscale/CMYK/ICC, transparent hidden RGB in
lossless WebP, metadata/GPS, animation/truncation/bombs/budgets/cancellation/atomicity,
preview-failure isolation, safe DOCX tables/text, lazy PDF bounds/rendering, cache corruption/
restart/deduplication, shared scheduling/quotas, ownership and exact selected-output bytes.
Existing RAW ZIP, legacy manifests/cookies/settings/IDs/lock and recovery checks remain.

Actual API benchmarks exposed transient Windows PermissionError during atomic manifest
replacement in this synced workspace. Added six bounded rename attempts (total620ms wait),
retaining old committed JSON throughout. Regression verifies recovery and permanent denial
without partial publication. No originals or outputs are rewritten by this retry.

## Measurements (observations, not universal requirements)

Windows11 x64 build26200, Python3.12.13, Pillow12.3.0, pypdfium2 5.14.0,
pypdf6.21.2, python-docx1.2.0, psutil7.2.2; physical RAM about7.4GiB usable.
Keep default1 worker,768MiB reserve and adaptive admission. No reserve/concurrency tuning.
Private photo derives from provenance-documented CR3 in ignored test-results/memory-inputs;
no private originals or outputs are redistributed.

Commands:

```powershell
.venv\Scripts\python.exe scripts/benchmark-v04.py --output test-results/v04-source-benchmark.json
.venv\Scripts\python.exe scripts/benchmark-v04.py --large-only --output test-results/v04-source-large-retry.json
.venv\Scripts\python.exe scripts/benchmark-previews-v04.py
```

Initial source six moderate cases completed in1.40-3.34s, sampled app-tree peaks153.7-218.7MiB:
opaque photo JPEG-to-PNG, PNG-to-WebP, WebP-to-JPEG, same-JPEG smaller, transparent lossless
WebP and JPEG background composition. Actual dimensions/settings/output sizes, input hashes,
minimum available RAM and peak workspace bytes are in v04-source-benchmark.json.
A10.67MP large-photo retry resized to1600x1067 in1.956s,251.09MiB sampled tree peak,
325337output bytes. The20.44MP full-size source and some later repetitions were safely
rejected under low host headroom. Final source report v04-source-final-benchmark.json has
five successes/two memory-policy rejections; these are not presented as successful conversions.
A transient earlier benchmark500 was traced to the manifest replacement issue fixed above.

Preview microprobe executes reopen baseline before reuse candidate on the same opaque PNG,
including mandatory full validation in both paths:0.834s versus0.618s (one pair, about26%
less wall time),75.37/75.34MiB worker lifetime peaks (effectively unchanged). New raster
previews reuse validated committed-output pixels, preserving lossy codec appearance and
avoiding a second full decode; RAW path remains untouched. No universal speed/RAM promise.

Actual PDFium first page918x1188:0.968s,122.39MiB sampled parent+worker, cached0.0168s.
Actual DOCX paragraphs/table:0.970s,118.92MiB sampled tree, cached0.0161s. These isolated
preview measurements seed real encoded committed files to exclude conversion time, not
mock parsers. Report: v04-preview-benchmark.json. Sampling may miss brief temporary files;
peak managed workspace includes retained input/output and is not solely scratch. Updated
harness records sampled .part/document scratch separately for subsequent frozen benchmarks.
Output ZIP remains ZIP_STORED. Binary release ZIP compression is a separate packaging choice.


Final frozen benchmark (all7 completed, default reserves/concurrency):

```powershell
.venv\Scripts\python.exe scripts/benchmark-v04.py --executable dist/v0.4.0/CapreConvert-v0.4.0.exe --output test-results/v04-frozen-benchmark.json
.venv\Scripts\python.exe scripts/benchmark-previews-v04.py --output test-results/v04-preview-final-benchmark.json
```

| Frozen case | Wall seconds | Sampled tree MiB | Output bytes | Sampled temporary bytes |
|---|---:|---:|---:|---:|
| Photo JPEG to PNG | 2.148 | 201.83 | 2243712 | 2243712 |
| Photo PNG to WebP | 3.193 | 232.00 | 180792 | 459253 |
| Photo WebP to JPEG | 1.836 | 236.84 | 428005 | 721445 |
| Same JPEG smaller | 1.642 | 200.43 | 323128 | 328157 |
| Transparent PNG to lossless WebP | 1.528 | 193.04 | 796 | 1362 |
| Transparent PNG to JPEG background | 1.529 | 172.06 | 60000 | 0 |
| Large10.67MP JPEG resized1600px | 1.943 | 266.26 | 325337 | 1114730 |

Source dimensions/settings/effective settings, actual output dimensions, bytes/savings,
original hashes, peak managed-workspace use and minimum free RAM are in the report.
Temporary0 means no partial file was observed at0.1s cadence, not proof no temporary
write occurred. Small photo inputs are2400x1601; graphics1600x1200; large input4000x2668.
These native codecs process real photo pixels, not decoder mocks.
Final isolated preview repeat: PDF1.005s/113.68MiB with0.0193s cache; DOCX0.992s/118.88MiB
with0.0204s cache. Reopen/reuse probe0.855/0.622s with75.63/75.68MiB worker peaks (no
meaningful RAM reduction). Samples confirm reduced decode work, not universal speed claims.

## Packaging and remaining gates

Executed:

```powershell
.venv\Scripts\python.exe scripts/build-package.py --libreoffice .tools/libreoffice/program/soffice.com
.venv\Scripts\python.exe test-results/validate-v0_4-raw.py --executable dist/v0.4.0/CapreConvert-v0.4.0.exe --output test-results/capre-v0.4-native-raw-validation.json
.venv\Scripts\python.exe scripts/validate-frozen-v04.py --executable dist/v0.4.0/CapreConvert-v0.4.0.exe --libreoffice .tools/libreoffice/program/soffice.com --output test-results/v04-frozen-browser-validation.json
```

Strict staged frozen smoke passed all nine actual raster codecs, actual PDF-to-DOCX,
actual external LibreOffice DOCX-to-PDF, PDFium visual page and bounded DOCX content
previews, image derivatives, direct MIME/length/bytes, ZIP bytes, ownership, PE version/
product/seven icon frames and served static byte equality. Python was removed from the
frozen child's PATH and its working directory was isolated. All18 PDFium/build dependency
license files are bundled under notices/pypdfium2; native pdfium.dll and both version JSON
assets are present. LibreOffice is not bundled. Report: test-results/package-smoke.json.
The first staged attempt hit the old60s smoke harness deadline during cold LibreOffice;
no release was published. The harness now permits the unchanged300s production timeout
plus30s supervision, and the strict rebuild passed. Opaque-alpha WebP was separately
fixed to normalize its codec-omitted alpha band before validation; pixels stay unchanged.

Native private CR3 validation passed default legacy JPEG with settings={} (no conversion
field) and two PNGs:5536x3692 landscape and3692x5536 portrait. JPEG decoded pixel SHA equals
the earlier v0.2/v0.3 baseline exactly:
45371b618cafa25e2af0c1b8fb4c5e680bde9e435134b80f2db611bcea835999.
JPEG7.469s/347.09MiB sampled app-tree peak; two PNGs25.094s/435.88MiB. Full RGB/ICC/
orientation/dimensions, direct hashes and exact selected PNG ZIP passed; originals unchanged,
no partial/staged RAWs left. Actual immutable v0.2 executable was denied the live v0.4
workspace lock while the new app stayed healthy. These sample checks do not establish a
named-camera/mode matrix.

Frozen Playwright driver passed actual converted DOCX safe content (literal script text
never executes), actual converted PDF image preview, one-result primary/direct bytes,
lossless WebP alpha/gallery, one selected file, exact multi-file ZIP, refresh selection and
unauthorized result/image/PDF preview denial. It initially hit a legitimate1.45GiB available
versus1.46GiB document admission estimate with Chromium open. It now prepares actual
conversions before opening Chromium, then validates all displays/downloads with default
production reserves unchanged. Report: v04-frozen-browser-validation.json; reviewed screenshots
v04-frozen-docx.png and v04-frozen-pdf.png. Source mobile raster screenshots v04-raster-320.png
and v04-raster-1440.png were also inspected.

Artifacts (512files;43,248,152byte ZIP, about41.25MiB):
- dist/v0.4.0/CapreConvert-v0.4.0.exe and its complete _internal folder.
- dist/CapreConvert-v0.4.0-windows-x64.zip.
- dist/CapreConvert-v0.4.0-windows-x64.zip.sha256.

SHA-256:bbbc0125021d10d3afa7fbe03367df19d3bdb97383bfe1b9a2b5d8fcf19e29b0.
Builder and independent CRC/path/hash verification passed; no private fixtures or .tools
image is packaged. All three old archive hashes are unchanged. No accidental overwrite.
Report: v04-artifact-verification.json. No commit or push.

Main implementation files: localraw/formats.py, models.py, config.py, worker.py, raster.py,
previews.py, jobs.py, api.py, uploads.py, archives.py and storage.py; static/converters.js,
app.js, previews.js, index.html and styles.css; packaging/localraw.spec, requirements.lock,
scripts/smoke-package.py and release/benchmark drivers. Migration is additive; all legacy
identities and JPEG defaults remain. See V0_4_MIGRATION.md.

Remaining broader acceptance: clean Windows machine, physical phone/LAN, secondary OS,
named-camera/RAW/C-RAW matrix and reference colour/ExifTool coverage. Standardized fixture
manifest remains absent; separate private real-camera checks do not establish broad support.
LibreOffice is external, PDF-to-DOCX remains text-only/noOCR/layout reconstruction, DOCX
preview is bounded content rather than exact pages. Preview scheduling can wait behind a
long conversion and return retry; direct download remains available. RSS checks are sampled,
not a hard OS/network sandbox. Low host free RAM can block large native measurements.


## Final asset-only rebuild audit

A final metadata-control wording fix distinguishes native raster metadata from optional RAW
ExifTool support. Its desktop/mobile source browser checks passed (2 in16.22s). Compilation
under host memory pressure caused one subsequent strict smoke memory rejection and one
preflight headroom timeout; neither published an artifact or lowered production limits.
The builder waits up to60s for default smoke headroom (document budget+reserve+128MiB HTTP
overhead). The final asset refresh reused the already native-validated compiled bundle via:

```powershell
.venv\Scripts\python.exe scripts/build-package.py --reuse-compiled .cache/v04-before-metadata-copy/v0.4.0 --libreoffice .tools/libreoffice/program/soffice.com
```

This option refuses different release/platform/architecture identities, filesystem links,
changed frozen Python code or dependency versions. It compiled and compared all20 runtime
source modules with frozen code objects before refreshing current local assets. Three
stale-code/dependency/identity rejection checks passed in1.19s. The final strict native
smoke reran all9 raster operations, both document engines, all previews/direct downloads/
ZIP checks and passed; this option does not skip smoke or relax resource admission.

Independent comparison proves every file in the final onedir bundle matches the native-RAW,
benchmark and frozen-browser validated bundle byte-for-byte except release.json (audit/time)
and static/app.js (metadata hint). EXE, all20 runtime modules, DLLs, renderer/data assets,
preview UI and codecs are identical. Final new ZIP CRC/hash and all3 older hashes verified
again in v04-artifact-verification.json. Final SHA above supersedes the intermediate build.
No uncommitted staging/build lock or test converter/office process remains.

Stable conversion IDs: cr3_to_jpg, cr3_to_png, docx_to_pdf, pdf_to_docx (retained);
jpg_to_png, png_to_jpg, jpg_to_webp, png_to_webp, webp_to_jpg, webp_to_png,
jpg_to_jpg, png_to_png, webp_to_webp (new).
