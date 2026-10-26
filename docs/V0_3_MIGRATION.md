# CapreConvert v0.3 migration

CapreConvert is the new application name. v0.3 adds CR3 to PNG, PDF to DOCX and DOCX
to PDF alongside the existing CR3 to JPG flow. Existing JPG quality, dimensions,
metadata choices, preview selection and result downloads remain available.

## Updating the Windows application

1. Finish active conversions and close the older LocalRAW or CapreConvert instance.
2. Extract the complete `CapreConvert-v0.3.0-windows-x64.zip`.
3. Keep `_internal` beside `CapreConvert-v0.3.0.exe`, then launch the executable.
4. Reopen the same browser/host address to resume the existing browser session and
   saved batch selection. If the session expired or browser data was cleared, pair again.

The default workspace remains `%LOCALAPPDATA%/LocalRAW/workspace`. Do not rename or
move it for the rebrand. New and old versions use the same exclusive workspace lock;
they must not run simultaneously against that directory. Originals remain untouched.
Older `dist/v0.1.0` and `dist/v0.2.0` deliveries and archives are preserved.
This is a forward migration: older executables do not understand the new v0.3 job
settings and document/PNG formats. Use a separate backed-up workspace when testing a
rollback; keeping the old binaries does not establish safe in-place downgrade support.

Completed old JPEGs, previews, whole-result ZIPs and prepared selection ZIPs retain
their IDs and paths. Older batches without previews still retain their full-resolution
downloads; retry retained inputs to generate previews. Unfinished work is marked
interrupted on restart and temporary partial outputs are cleaned up. Retry explicitly.
Creating PNG output from an older JPEG batch requires a new conversion from its retained
RAW inputs; existing JPEG output is never silently replaced or re-encoded.

## Compatibility identifiers

These technical identities intentionally retain their existing spelling. Their stability
keeps configuration, ownership and saved history working across the public-name change.

| Identity | Retained value |
|---|---|
| Python import/module entry point | `localraw`, `python -m localraw` |
| Python distribution metadata | `localraw-converter` |
| Existing console alias | `localraw` (the new `capreconvert` alias is also declared) |
| Default workspace directory | `LocalRAW/workspace` under the application-data directory |
| Workspace marker and lock | `.localraw-workspace`, `workspace.lock` |
| Browser authentication cookie | `localraw_session` |
| Configuration environment variables | `LOCALRAW_*` |
| Browser preferences | `localraw-job`, `localraw-theme`, `localraw-navigation`, `localraw-preview:<job-id>` |

The public app name, executable product information, browser wordmark and new release
filenames use CapreConvert. The original CC mark is generated from geometric arcs;
`scripts/generate-icon.py` produces the matching multi-resolution Windows ICO without
downloaded artwork or fonts. Windows product/file metadata derives from the same version
source as the executable name and ZIP, `localraw/__init__.py`.

Legacy requests and persisted jobs without `settings.conversion` retain CR3 to JPG
semantics. Public job responses expose the explicit default `cr3_to_jpg`; their original
persisted settings dictionaries do not require a destructive rewrite. Existing
idempotency keys continue returning the original job when the normalized request is
unchanged, and reject changes such as a different output format. Ownership checks and
session/CSRF rules remain in force.

## Document engines and offline operation

PDF to DOCX uses bundled `pypdf`, `python-docx`, their DOCX template data and native
`lxml` dependencies. It extracts searchable text into paragraphs. It does not provide
OCR for scanned pages or promise preservation of complex page layout, tables or images.

DOCX to PDF requires a separately installed local LibreOffice executable. LibreOffice
is detected from explicit configuration, common local installations or the executable
search path; it is not bundled in the CapreConvert ZIP and is not downloaded at runtime.
Set `libreoffice` in the existing JSON config, or use the compatible
`LOCALRAW_LIBREOFFICE` environment variable, when automatic detection is insufficient.
The UI reports availability, so users can see whether this conversion is ready.
Both document routes run locally, without uploading content to an Internet service.

## Building and checking the package

```powershell
.\.venv\Scripts\python.exe scripts/generate-icon.py
.\.venv\Scripts\python.exe scripts/build-package.py
```

Expected outputs are `dist/v0.3.0/CapreConvert-v0.3.0.exe`,
`dist/CapreConvert-v0.3.0-windows-x64.zip` and the matching `.sha256` sidecar. The builder
stages the complete folder, checks runtime behavior and Windows version/icon resources,
then creates and verifies the ZIP and checksum. Existing releases are refused instead
of overwritten. The document smoke generates its own small searchable PDF and verifies
the returned DOCX text and ZIP integrity. When an external LibreOffice is available,
the smoke also renders that DOCX back to PDF and verifies readable text.

To validate an explicit external LibreOffice without bundling it:

```powershell
.\.venv\Scripts\python.exe scripts/smoke-package.py --libreoffice 'C:\Program Files\LibreOffice\program\soffice.exe'
```

`scripts/build-package.py` accepts the same `--libreoffice` option for its staged smoke.
Neither command changes the application's persisted configuration.

Migration checks are in `tests/unit/test_legacy_migration.py`. They seed representative
old manifests and byte fixtures, then verify session resumption, identical retained
downloads, interruption cleanup, idempotency, owned retries and workspace exclusion.
They are persistence checks, not proof of real-camera compatibility. Executed release
and document validation results belong in CODEX_HANDOFF.md and VALIDATION.md.
