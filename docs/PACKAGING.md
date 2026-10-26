# Packaging

Build each distribution on its target OS. From the project root on Windows:

```powershell
.\.venv\Scripts\python.exe scripts/build-package.py
```

The version comes from `localraw/__init__.py` (`__version__ = "1.0.0"`). The builder
adds the `v` prefix automatically. Set a new version there before the next release;
Python project metadata, executable name, folder and ZIP use the same value.
Versions such as `0.2.0rc1` are also supported. There is no cross-compilation.

For version 1.0.0 on Windows x64, this produces:

```text
dist/
  v1.0.0/
    CapreConvert-v1.0.0.exe
    _internal/
    release.json
    START_HERE.txt
  CapreConvert-v1.0.0-windows-x64.zip
  CapreConvert-v1.0.0-windows-x64.zip.sha256
```

The command builds in a temporary staging folder, smoke-checks the executable, creates
the ZIP, verifies its CRCs and executable entry, and writes a SHA-256 sidecar before
publishing these files. Existing releases are refused instead of overwritten. For a
separate test build of the same version, use `--output-dir dist/test-build`.
A per-version lock prevents concurrent builds into the same output directory.

Send the ZIP and its checksum together. Extract the ZIP before launching:

```powershell
.\dist\v1.0.0\CapreConvert-v1.0.0.exe
.\dist\v1.0.0\CapreConvert-v1.0.0.exe --lan
```

Keep the entire `v1.0.0/` folder. `_internal` holds Python, native libraries,
static assets, distribution metadata and upstream licenses. The end user needs no installed
Python. Workspace data is separate and survives replacing the application folder.
Finish jobs and close an older instance before starting a new version with the same
default port/workspace. The console displays the short-lived local link and optional LAN
pairing code. Access logging is disabled. `--no-browser` supports headless launch.

For a folder-only build or to recheck an existing release:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller packaging/localraw.spec --noconfirm
.\.venv\Scripts\python.exe scripts/smoke-package.py
```

Direct PyInstaller builds use the same `dist/v<version>/LocalRAW-v<version>.exe` naming,
but do not create the ZIP, checksum or release manifest. The smoke script accepts
`--dist-dir PATH` for a different folder, including older unversioned builds.

`packaging/entrypoint.py` dispatches frozen multiprocessing children before heavy imports.
The spec bundles rawpy's DLLs, Pillow/LittleCMS, NumPy, psutil, Uvicorn imports, static files
and installed notices. Fonts and their license are local assets; no runtime CDN is used.
The base build does not bundle ExifTool. A metadata-enabled release needs a tested native
ExifTool distribution and all its notices; set `exiftool` in JSON config.

The runtime smoke check removes Python from the child PATH, starts in an empty directory
with an isolated workspace and port, and checks health, authentication, native version
diagnostics, safe job behavior, preview/export route protection and all served static assets
against source bytes. It also verifies the application version matches source.
Provenance-documented real-camera conversion/cancellation benchmarks and a clean-machine run are
separate acceptance gates. See CODEX_HANDOFF.md for executed evidence.

The old `dist/LocalRAW/`, `dist-preview/`, `dist-styled/` and their unversioned build
caches were removed at the user's request after the versioned release passed verification.
The idle old application was closed first. Saved uploads, jobs and the separate workspace
were preserved. The versioned release includes the preview, selection and
repository-inspired styling updates.



## CapreConvert v1.0.0 rename and document engines

The v1.0.0 executable/ZIP/PE metadata use CapreConvert. Existing LocalRAW-named
v0.1.0/v0.2.0 artifacts remain unchanged. The localraw package/spec filename and default
LocalRAW workspace/cookie/environment identifiers are intentionally preserved; see
V0_3_MIGRATION.md. Both `capreconvert` and the legacy `localraw` console entry work.

The spec includes local CC icons, wordmark, fonts, python-docx template data, pypdf,
lxml native libraries and their installed notices. Windows smoke verifies numeric and
string PE product/version fields and the embedded icon frames against the original ICO.
No additional server/reloader or onefile launcher is introduced.

LibreOffice is an external setup dependency for DOCX-to-PDF, not part of the ZIP. Supply
`--libreoffice PATH` to the app (or JSON/LOCALRAW_LIBREOFFICE). A builder validation option
with the same name tests that external engine without bundling or persisting its path:

```powershell
.\.venv\Scripts\python.exe scripts/build-package.py --libreoffice .tools/libreoffice/program/soffice.com
```

The local .tools administrative image is development/test setup only. It was downloaded
from The Document Foundation and checksum-verified; no runtime download or system-wide
LibreOffice installation is performed by this application. A new recipient needs their
own local LibreOffice installation to enable that converter; PDF-to-DOCX and both RAW
workspaces do not depend on it. Default smoke always exercises actual text-PDF-to-DOCX;
when an explicit/detected renderer exists it additionally verifies actual DOCX-to-PDF.
It retains authenticated preview/export/download and corrupt-RAW safe-failure checks.


v0.4 bundles pypdfium2/PDFium native components, JPEG/PNG/WebP Pillow codecs, local assets
and the wheel's complete PDFium/build-dependency license files. Frozen smoke performs all
nine actual raster operations, image derivatives, DOCX content preview and PDF page rendering
when an external LibreOffice is supplied. LibreOffice remains external. Old release folders
and checksums must remain unchanged; the builder refuses existing release paths.


After compilation, the builder waits up to60s for default native-smoke memory headroom;
no runtime reserve is lowered. For an asset-only rebuild of an unpublished same-version
intermediate, --reuse-compiled PATH verifies release identity, every frozen application
module against current Python source and bundled dependency versions, then refreshes
local assets and runs the same strict native smoke/ZIP/CRC/checksum flow. Changed code,
dependencies or existing final release paths are refused. This avoids repeating memory-
heavy compilation for a text/CSS/JS-only refresh; it never skips release checks.


For tiny validation fixtures on constrained hosts, --smoke-memory-profile compact uses
stricter document384MiB/preview256MiB worker caps while keeping the768MiB safety reserve.
It does not change packaged defaults or skip native checks. --memory-profile compact is
the corresponding smoke-script flag. Record the profile; do not report default-policy
acceptance from compact validation. Older packages were removed at the user's request
following the verified v1.0.0 build; historical evidence remains in docs/test-results.
