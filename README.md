# CapreConvert

CapreConvert converts documents, Canon RAW photos and everyday image files on your computer. Files stay local, and original inputs are left unchanged.

## Supported formats

| Input | Output |
| --- | --- |
| JPG / JPEG | PNG, WebP, or an optimized JPG |
| PNG | JPG, WebP, or an optimized PNG |
| WebP | JPG, PNG, or an optimized WebP |
| Canon CR3 | JPG or PNG |
| DOCX | PDF, using a local LibreOffice installation |
| PDF | DOCX, using selectable text from the PDF |

Image conversions include resizing, compression presets, transparency controls and metadata options. Resizing keeps the aspect ratio and does not upscale. The results show file sizes, dimensions and whether the output is smaller or larger.

CR3 conversions also accept ZIP archives containing CR3 files. For other formats, select individual files rather than a ZIP.

## Run the Windows build

1. Extract `CapreConvert-v1.0.0-windows-x64.zip`.
2. Keep the extracted folder together, including `_internal`.
3. Run `CapreConvert-v1.0.0.exe`.

The app opens in your browser. Python is included in the Windows build, so a separate Python installation is not needed. Close an older instance before starting another copy with the same workspace.

### DOCX to PDF

Install [LibreOffice](https://www.libreoffice.org/download/) on the computer running CapreConvert, then restart the app. LibreOffice and its installer are not included in the current package. All other conversions work without it.

If LibreOffice is installed somewhere the app cannot find, pass its executable path:

```powershell
.\CapreConvert-v1.0.0.exe --libreoffice "C:\Program Files\LibreOffice\program\soffice.com"
```

## Using the app

Choose an input file type and an output file type, then click **Open converter**. Add files, adjust the settings and start the batch. Successful results remain available if another file fails or you cancel the remaining work.

The **Output preview** panel shows converted images, PDF pages or read-only DOCX text and tables. Image previews are reduced in size; DOCX previews do not reproduce Word's page layout.

Use **Download** for an individual result. Selecting one result downloads that file directly; selecting several creates a ZIP. **Download all as ZIP** includes every successful result in the batch. Downloads still work when a preview is unavailable.

For phone access, start the app with `--lan`, open the address printed in the console and enter the pairing code. Keep both devices on a trusted local network and leave the host computer awake.

## Run from source

Requires Python 3.12 and `uv`. From the project folder in PowerShell:

```powershell
uv venv --python 3.12 .venv
uv pip sync requirements.lock --python .venv\Scripts\python.exe --require-hashes
uv pip install --no-deps -e . --python .venv\Scripts\python.exe
.\.venv\Scripts\capreconvert.exe
```

The existing `localraw` command also works. Settings can be supplied through `--config`, and `--workspace` selects a different data folder. The default workspace is `%LOCALAPPDATA%\LocalRAW\workspace`.

## Limitations

- PDF to DOCX extracts text. It does not perform OCR or preserve images, tables, fonts or the original page layout.
- DOCX to PDF depends on the fonts installed on the host. Documents with encrypted, active, embedded or externally linked content may be rejected.
- Image conversions support static JPEG, PNG and WebP files. Animated images and other image formats are not supported.
- Recompressing an image cannot restore lost detail or guarantee a smaller file. PNG and lossless WebP preserve the normalized output pixels, rather than the original file bytes.
- CR3 support varies by camera and recording mode. RAW capture metadata uses optional ExifTool support. GPS metadata is off by default.
- Large files need available RAM and disk space. If a conversion is rejected for low memory, close other applications and retry the retained inputs.

## Development

Run backend checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q
```

Run browser checks:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest tests/e2e -q
```

Build a Windows package:

```powershell
.\.venv\Scripts\python.exe scripts/build-package.py
```

Builds use the version in `localraw/__init__.py` and are written under `dist/v<version>/`. Existing releases are not overwritten.

Third-party licenses and bundled components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
