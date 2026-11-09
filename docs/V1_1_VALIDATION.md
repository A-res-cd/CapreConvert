# CapreConvert v1.1.0 validation

## Scope

ODF Text (.odt) ↔ Word (.docx), ODT ↔ PDF. The four new pairs require a local
LibreOffice installation. PDF → ODT uses existing bounded selectable-text extraction
to an intermediate DOCX, then LibreOffice's Writer ODT export. It has no OCR and does
not reconstruct original fonts, tables, images or page layout. No new Python or runtime
network dependency was added. The installed local LibreOffice is external to the ZIP.

The capability catalog drives upload extension acceptance and the existing picker.
ODT has protected, bounded plain-text previews; direct and selected ZIP exports retain
their existing ownership, admission, publication and retention rules. Original files and
the v1.0.0 release are preserved. All document parsing stays in supervised workers.

LibreOffice export filter names were checked against the
[official conversion filter table](https://help.libreoffice.org/latest/en-US/text/shared/guide/convertfilters.html):
`odt:writer8`, `docx:Office Open XML Text`, `pdf:writer_pdf_Export`.

## Executed source checks

- Real local LibreOffice unit round trip: DOCX → ODT → DOCX, ODT → PDF and PDF → ODT
  passed. Paragraphs, table cells, selectable text on two pages, result hashes, original
  hashes and scratch cleanup were checked. These are authored fixtures, not claims of
  fidelity for every third-party document.
- `LOCALRAW_TEST_LIBREOFFICE=.tools/libreoffice/program/soffice.com` with
  `.venv/Scripts/python.exe -m pytest tests/unit tests/integration -q`:
  **215 passed, 1 skipped in 221.70 s**. The skip is the separate standardized real-camera
  fixture gate. One existing Starlette/httpx deprecation warning remains.
- After adding seven further package-adversarial cases and the upload registry check:
  `pytest tests/integration/test_picker_capabilities.py tests/unit/test_odt.py -q -k 'not real_native'`:
  **22 passed, 1 deselected in 2.64 s**. The deselection avoids repeating the completed
  native round trip. Counts overlap the preceding suite and must not be added together.
- ODT adversarial checks reject traversal, ambiguous entries, symlinks, external links,
  scripts, embedded active objects, encrypted packages, XML entities, disguised XML,
  incorrect MIME types, missing structure, corrupt ZIPs and expanded byte overflows
  before native engine execution. Output and scratch cleanup/original hashes are checked.
- Ruff lint and formatting pass across 72 Python files. Modified browser modules pass
  Node syntax and cached local Prettier checks.
- `pytest tests/e2e -q`: **27 passed in 101.18 s**. Includes ODT catalog filtering,
  four explicit ODT deep links, disabled controls and setup messages without LibreOffice,
  mobile/keyboard navigation and previous image/document workflows. Existing UI workers
  use named conversion doubles; real engines are covered by native/frozen checks.
- Both installed console aliases report `CapreConvert 1.1.0` after an offline editable
  metadata refresh with no dependency changes.

## Frozen release checks

`python scripts/build-package.py --libreoffice .tools/libreoffice/program/soffice.com --smoke-memory-profile document512`
passed. Native packaged checks covered all six document routes, nine raster operations,
protected/cached DOCX/ODT text and PDF page previews, direct downloads, ZIPs and rejected
unauthenticated requests. Windows PE branding/version and seven icon frames passed.
Python was removed from the launched app's PATH. Corrupt RAW inputs failed safely;
this does not establish a new camera compatibility claim.

All 20 frozen application modules were independently compared with current source code
objects and matched. The packaged executable and both source aliases report version 1.1.0.
Independent archive CRC, root/path, file count and SHA-256 checks passed:

- `dist/v1.1.0/CapreConvert-v1.1.0.exe`, with the complete `_internal` folder.
- `dist/CapreConvert-v1.1.0-windows-x64.zip` — 43,250,806 bytes, 513 files.
- Corresponding `.zip.sha256` sidecar.
- SHA-256: `aaba781bd78fdb73e583372c10240a4e9f2c01b3f287ec719df3f06326bad9d9`.

The v1.0.0 ZIP retains its previously recorded SHA-256
`7e8b580a69a3c31f43248a74cbf6a4d7f226ff2aa92ec58aa0cb0534acfe2fc8`.
No prior release or user workspace was deleted, and no GitHub publication was performed.

`python scripts/validate-frozen-picker.py --executable dist/v1.1.0/CapreConvert-v1.1.0.exe --libreoffice .tools/libreoffice/program/soffice.com --memory-profile document512 --output test-results/v1-1-frozen-browser-validation.json`
passed against the actual frozen app. The browser opened DOCX → ODT through the picker,
rendered literal `<script>` characters safely as text, exported one selected ODT with exact
committed bytes, and restored the converter/preview after refresh. Existing native
DOCX/PDF/WebP workflows and exact multi-result ZIP checks also passed. Real document
previews were generated through protected API requests before Chromium opened to limit
RAM overlap; browser requests reused validated caches. The ODT screenshot was inspected.
No new-version converter or LibreOffice helper process remained after validation.
Detailed evidence: `test-results/package-smoke.json`,
`test-results/v1-1-frozen-browser-validation.json`, `test-results/v1-1-frozen-odt.png`.

## Acceptance limits

The first frozen smoke using the historical compact profile (document 384 MiB / preview
256 MiB, reserve 768 MiB) stopped PDF → ODT at its worker memory cap. No release was
published by that failed attempt. This pipeline retains PDF/Word libraries while LibreOffice
runs, so it needs more memory than the individual old document routes. A `document512`
test profile was added: document 512 MiB / preview 256 MiB, with the same 768 MiB reserve.
It changes child test configuration only; the app continues to ship 768 MiB / 384 MiB
defaults. Default-profile frozen validation needs additional host headroom and is not
established by a stricter-cap test.

PDF conversion remains text extraction; scanned pages require a separate OCR tool.
ODT content previews flatten paragraphs and table-cell text; they are not page renderings.
Fonts and format-specific features can change DOCX/ODT/PDF layout. Documents with active,
encrypted, externally linked or unsupported embedded resources are rejected.
Clean-machine installation, physical phones, secondary operating systems, broader camera
modes and comprehensive third-party document layout fidelity remain unverified.
This release changes no RAW rendering algorithms or production memory limits.
