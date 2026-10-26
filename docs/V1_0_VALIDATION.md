# CapreConvert v1.0.0 validation

Scope: capability-driven homepage input/output picker, simplified sidebar, version1.0.0,
and user-authorized removal of older packaged releases after the new package verifies.
Existing conversion engines, defaults, download contracts, workspace/session/config IDs
and original inputs remain unchanged. No commit or push.

Source gates executed:
- Backend: `.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q`:
  196 passed,2 skipped,1 existing Starlette/HTTPX warning in153.30s. Skips are the
  standardized real-camera fixture manifest and API LibreOffice test without its optional
  environment variable; actual native document engines are tested by frozen smoke below.
- Browser: `.venv\Scripts\python.exe -m pytest tests/e2e -q`:
  26 passed in98.01s. Five new picker checks cover grouped explicit capabilities,
  pairs/aliases/no ZIP, target filtering/retention/clear/auto-select, optimization hints,
  loading/failure/retry, ambiguous engines, empty registry, route synchronization, pending
  upload/job/settings isolation, mobile layout/keyboard/focus and sidebar active state.
  Existing RAW ZIP, image/document previews, direct one-file and exact multi-file ZIP,
  history/refresh/Back/Forward/theme/drawer/Escape/preference checks remain passing.
- Focused schema/default/CLI checks:19 passed in1.44s; focused picker5 passed in13.93s.
  These overlap the full suites and are not added to their totals.
- Ruff lint/format, Node module syntax and Prettier checks pass. Reviewed desktop1440px
  light/dark and mobile320px screenshots (test-results/capre-home-*.png and v1-picker-mobile.png).

The capabilities endpoint adds formats:[{id,label,short_label,category}] and explicit
source_format/target_format on conversion entries; existing keys/IDs/defaults/routes stay.
JPG/JPEG share jpg. ZIP remains a RAW upload container. Support and availability come only
from server entries. Duplicate engine pairs disable Open converter rather than picking an
arbitrary engine. Supported unavailable pairs show setup guidance; unrelated pairs work.
Capabilities remain authenticated: unpaired browsers get pairing guidance, never fallback
support choices. Strings use safe DOM text/Option APIs.

Pending selections live in picker.js and do not write workspace/job/upload/settings state.
Explicit Open converter follows the existing route/reset/recovery flow. Deep links and
Back/Forward synchronize the picker. Unknown IDs show Home with an error. Sidebar has one
Convert files link and existing settings/history/preview links. Mobile drawer and preferences
are retained. Obsolete cards, pair sidebar links, card styles and raster pair list were removed.
Source presentation metadata no longer duplicates the supported pair matrix.

## Packaged Windows release

Fresh PyInstaller compilation completed. Two default smoke preflight attempts were blocked
by host RAM around0.75-1.24GiB. No production setting or safety reserve was reduced. The
complete compiled checkpoint was reused only after checking all20 frozen application code
objects against current source and matching bundled dependency versions. Same native smoke
checks then passed with explicitly stricter caps for the tiny fixtures:

```powershell
.venv\Scripts\python.exe scripts/build-package.py --reuse-compiled .cache/v1-compilation-checkpoint --libreoffice .tools/libreoffice/program/soffice.com --smoke-memory-profile compact
.venv\Scripts\python.exe scripts/validate-frozen-picker.py --executable dist/v1.0.0/CapreConvert-v1.0.0.exe --libreoffice .tools/libreoffice/program/soffice.com --memory-profile compact --output test-results/v1-frozen-browser-validation.json
```

Compact validation caps document worker trees at384MiB and preview workers at256MiB;
it keeps the768MiB safety reserve, default conversion concurrency, image budgets, timeouts
and processing settings. Packaged app defaults remain768MiB documents/384MiB previews.
The compact profile is a test-only flag, not persisted runtime configuration. Default-profile
native smoke on this host remains memory-blocked; do not claim it passed. Real large-CR3
conversion was not repeated for this UI-only change; prior provenance evidence remains
historical, with unchanged RAW engine/defaults and source regression/native corrupt-RAW
checks. No new camera compatibility claim is made.

Final frozen smoke passed version/PE product/seven-icon checks, all9 actual raster codec
operations, both actual document API engines, image/PDF/DOCX preview generation, typed
direct download lengths/bytes and selected ZIP checks. Served assets including picker.js
match source bytes; Python was removed from child PATH. Report:test-results/package-smoke.json.
Frozen browser driver passed native picker opening from advertised groups, real converted
DOCX safe text, PDF visual preview, lossless WebP alpha, direct one-file and exact multi-file
ZIP, refresh selection and unauthorized result/preview denial. Report records compact profile.
LibreOffice remains external and was explicitly configured for these checks.

Artifacts (513files;43,245,368byte ZIP):
- dist/v1.0.0/CapreConvert-v1.0.0.exe with complete _internal folder.
- dist/CapreConvert-v1.0.0-windows-x64.zip.
- dist/CapreConvert-v1.0.0-windows-x64.zip.sha256.

SHA-256:7e8b580a69a3c31f43248a74cbf6a4d7f226ff2aa92ec58aa0cb0534acfe2fc8.
Builder and independent ZIP CRC/root-path/checksum checks passed.

## Authorized cleanup

After the new package and frozen browser checks passed, removed v0.1.0/v0.2.0/v0.3.0/
v0.4.0 folders, corresponding ZIPs/checksums, their build/releases caches and the old v0.4
intermediate backup (17 targets). Also removed the temporary v1 compilation checkpoint.
Each resolved path stayed inside this workspace, matched a fixed allowlist and contained no
workspace marker, filesystem link or unexpected release files. Old archive hashes/CRC and
folder inventories were checked first; no older executable was running during cleanup.
Source, docs, historical evidence, fixtures, originals and application workspaces were kept.
Audit:test-results/v1-cleanup-plan.json, v1-old-release-hashes.json, v1-artifact-cleanup.json.


Remaining broad acceptance: clean machine, physical phone/LAN, secondary platform and broad
named-camera/mode/reference-colour coverage. Source RAW/document browser conversions use
explicit worker doubles; native frozen checks are separate. No universal RAM guarantee.
