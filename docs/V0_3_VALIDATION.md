# CapreConvert v0.3.0 validation

## Delivered release

Public name: CapreConvert. Version: 0.3.0 from localraw/__init__.py.
Windows x64 artifacts:

- dist/v0.3.0/CapreConvert-v0.3.0.exe (keep its full folder/_internal).
- dist/CapreConvert-v0.3.0-windows-x64.zip (39,221,908 bytes; 37.40 MiB; 463 files).
- dist/CapreConvert-v0.3.0-windows-x64.zip.sha256.

SHA-256: e0d1be9348be96015f9f5e22e1374e7429cbf6f63752425130560e614b2c6b7a.
Original LocalRAW v0.1.0/v0.2.0 archive hashes remain unchanged. No old artifact was removed.
The release ZIP contains no private photos, test-results or LibreOffice administrative image.

## Scope and public branding

The new home offers DOCX→PDF, text-based PDF→DOCX, CR3→JPG and CR3→PNG. It retains the
paper/indigo/orange theme, bundled Fraunces fonts, light/dark modes and responsive sidebar.
Home heading/supporting copy/choice question match the request. Header, home links,
breadcrumbs, browser title/description, accessible labels, pairing/workspaces/empty states,
CLI help/startup/version, FastAPI identity and current setup/release metadata use CapreConvert.
Original local CC SVG/wordmark and seven-frame ICO are bundled. No branding/font fetch at runtime.
Windows ProductName/FileDescription/OriginalFilename and numeric/string version resources
were read from the actual EXE and checked; all seven embedded ICO frame hashes match source.

Historical LocalRAW release/validation names remain historical. Compatibility identifiers
are deliberately stable: localraw package, localraw-converter distribution, localraw console
alias, LOCALRAW_* environment settings, LOCALAPPDATA/LocalRAW/workspace, .localraw-workspace
marker/content, workspace.lock, localraw_session and existing browser preference keys.
The capreconvert entry point is added. No automatic workspace move or destructive migration.

## Executed source gates

```powershell
uv --cache-dir .cache/uv pip compile pyproject.toml --extra dev --generate-hashes --output-file requirements.lock --python .venv\Scripts\python.exe
uv --cache-dir .cache/uv pip sync requirements.lock --python .venv\Scripts\python.exe --require-hashes
uv --cache-dir .cache/uv pip install --no-deps --editable . --python .venv\Scripts\python.exe
$env:LOCALRAW_TEST_LIBREOFFICE = (Resolve-Path .tools/libreoffice/program/soffice.com).Path
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q
.\.venv\Scripts\python.exe -m pytest tests/e2e -q
.\.venv\Scripts\python.exe -m ruff check localraw tests scripts
.\.venv\Scripts\python.exe -m ruff format --check localraw tests scripts
```

Only three dependency additions: pypdf6.21.2, python-docx1.2.0 and lxml6.1.3. Existing locked
versions stayed unchanged. Backend: **148 passed, 1 skipped, 1 existing Starlette TestClient
deprecation warning in106.10s**. Final browser suite: **19 passed in63.95s**. Ruff lint/format
checks pass. Node syntax, Prettier and SVG parse checks pass. Light/dark desktop/320px home,
PNG workspace and document-workspace screenshots were reviewed under ignored test-results.
The one skipped gate requires the separate standardized camera/mode fixture manifest; it
does not negate the real private RAW checks below. Browser success fixtures use explicitly
named worker doubles; actual engine checks are separate and are not inferred from them.

Tests cover legacy request defaults and idempotency, typed paths/MIME/ZIPs, PNG exact RGB,
normalized orientation, unchanged JPEG transfer/quality, ownership/CSRF, quotas, cancellation,
new-format restart recovery, old JPEG/preview/ZIP/selected-export/session recovery, legacy
settings/entry aliases, and exclusive workspace ownership. Document adversarial checks cover
ZIP traversal/duplicates/encryption/expansion, external relationships/fields, active/macros/
embedded/SVG parts, disguised XML/entities, compressed PDF stream limits, page/text budgets,
scanned/encrypted inputs, quota/cancel cleanup and byte-equivalent OOXML serialization.

## Actual document engines

Real generated searchable PDFs were converted through supervised API workers to editable
DOCX paragraphs and decoded/validated. Real authored DOCX was converted through local
LibreOffice to a readable PDF, including both direct engine and supervised API checks.
Text/geometry/page count, output hashes, input preservation and generated-scratch cleanup
were checked. Documents and RAWs are never decoded in the HTTP request process.

LibreOffice26.8.1.1 was obtained as a project-local administrative image, not a system-wide
installation and not bundled in the release. Its official MSI SHA-256 was checked against
The Document Foundation: c6298b10cfa1748bcbedad94c62ce771e240e5021bfd6d7a967cd571b04b5312.
Source: https://www.libreoffice.org/download/ . Runtime discovery never downloads it.

The first 30-second cold native test was too short; a120-second test allowance passed
(roughly35s cold export). Production timeout remains300s. A real supervised API test also
exposed LibreOffice's silent exit0/no-output behavior with long Windows profile/cache paths.
Same-file Windows8.3 CLI aliases fixed that without moving inputs/profiles/workspaces.
If aliases cannot keep the renderer's profile paths short enough, an actionable shorter
--workspace error replaces silent failure. Macro/active content, link updates and online
update checks are disabled in a fresh per-job profile; unsupported linked/active DOCX is
rejected. This is not an OS/network sandbox.

## Frozen build and smoke

```powershell
.\.venv\Scripts\python.exe scripts/build-package.py --libreoffice .tools/libreoffice/program/soffice.com
```

Build/staged frozen smoke/ZIP CRC/name checks/SHA-256 passed. The smoke removed Python from
the executable child PATH, used an isolated workspace/port and compared every served static
asset with source bytes. It verified authenticated routes, CapreConvert0.3.0, native decoder
versions, Windows PE product/version/icon resources, actual text-PDF→DOCX and actual
DOCX→PDF with external LibreOffice, plus corrupt RAW→PNG rejection and safe deletion.
This exercises bundled python-docx templates, lxml/pypdf and the frozen external-DLL search
reset. Separate independent archive/hash checks also passed.
Report: test-results/package-smoke.json (ignored local evidence).

## Frozen real RAW and cross-version lock checks

```powershell
.\.venv\Scripts\python.exe test-results/validate-v0_3-raw.py --executable dist/v0.3.0/CapreConvert-v0.3.0.exe --output test-results/capre-v0.3-native-raw-validation.json
```

Private provenance/hashes/geometry are recorded in test-results/memory-inputs/manifest.json;
photos are not redistributed. The final run used default production resource settings.
One first attempt correctly rejected when only1.73GiB was available and the stage estimate
required1.74GiB including the reserve. After background headroom recovered, the unchanged
same validation passed; no safety reserve/budget was lowered.

| Case | Result | Geometry | Sampled app-tree peak | Min remaining available RAM |
|---|---|---|---:|---:|
| Legacy API request, no conversion setting | Real JPEG success | 5536x3692 | 444.54MiB | 1.599GiB |
| PNG two-photo batch + selected ZIP | Two real PNG successes, exact selected-file bytes | 5536x3692 and3692x5536 | 419.93MiB | 1.620GiB |

RGB format, full dimensions, normalized orientation, embedded ICC, committed/downloaded
hashes and JPEG derivative previews passed. The legacy JPEG's decoded pixel hash equals
the preserved v0.2.0 baseline exactly. Selected PNG ZIP CRC/names/hash checks prove original
full PNGs are exported, not reduced previews. Exactly one conversion worker ran. Original
hashes stayed unchanged; no partial/staged RAW remained. These are samples, not a universal
minimum-RAM or broad-camera guarantee.

During this actual frozen run, immutable LocalRAW-v0.2.0.exe was launched against the live
CapreConvert workspace. It failed specifically with 'already in use'; the new app remained
healthy. This supplements substantive representative-legacy-workspace recovery tests and
proves the old/new binaries share the lock rather than merely comparing marker strings.

## Setup and acceptance gaps

DOCX→PDF requires a local external LibreOffice. On this workspace the validated engine is
.tools/libreoffice/program/soffice.com. To use it:

```powershell
.\dist\v0.3.0\CapreConvert-v0.3.0.exe --libreoffice .tools/libreoffice/program/soffice.com
```

Recipients install/configure their own LibreOffice. Without it that workspace reports setup
instructions; PDF→DOCX and both RAW modes remain available. PDF→DOCX is text-only, without
OCR or original font/image/table/precise-layout reconstruction. DOCX fonts/layout depend on
the renderer and installed fonts. Broad document/layout/password/active-content support is
not claimed. Clean-machine, physical-phone/LAN, Windows10/secondary-platform, broad named
camera/RAW/C-RAW matrix and reference color/ExifTool acceptance remain open. Existing old
binaries do not understand new job formats: forward compatibility is tested, not safe
in-place downgrade; use a separate backed-up workspace for rollback.
