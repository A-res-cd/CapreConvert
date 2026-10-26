# Image optimization and output previews

Static JPEG (.jpg/.jpeg), PNG and WebP are supported as all six cross-format and three
same-format operations. Actual decoded format must match; animation/multiple frames are
rejected. TIFF/BMP/HEIC/AVIF/OCR/other RAW/audio/video and document/raster ZIP input are deferred.
PDF preview page images are internal derivatives, not a PDF-to-image conversion feature.

Resize applies EXIF orientation first, then optional maximum width/height using LANCZOS,
keeping aspect ratio with no upscaling. Presets never resize. Effective settings are persisted.

| Preset | JPEG quality (4:4:4) | WebP lossy quality/method | PNG effort |
|---|---:|---|---:|
| Smaller | 80 | 75 / 4 | 9 |
| Balanced | 90 | 85 / 4 | 6 |
| High quality | 95 | 95 / 4 | 3 |

Explicit advanced values override the preset. PNG effort changes encoding effort without
quantization. WebP lossless is explicit and uses exact=True so fully transparent RGB values
are retained when no resize/colour transform changes them. Lossless means equivalence to
normalized output pixels, not original bytes. Recompression cannot restore lost detail.
WebP has a16383px codec edge limit: choose resize bounds for larger output dimensions.

RGB, RGBA, grayscale, palette (including transparency), LA and CMYK normalize to RGB/RGBA.
Valid embedded ICC is transformed to sRGB separately from alpha. Missing profiles assume
sRGB for RGB/grayscale; unprofiled CMYK uses Pillow conversion with a warning. Invalid or
incompatible profiles warn and use that deterministic fallback. Unusual/high-precision modes
reduce to8-bit RGB with a warning. PNG/WebP preserve alpha. WebP omits a fully opaque alpha channel, yielding RGB without changing pixel colours. JPEG explicitly composites over
the visible persisted background (#ffffff default). Resizing transparent pixels may change
hidden RGB through filtering, as part of normalization.

Only whitelisted capture EXIF is copied, with orientation=1. No stale dimensions, arbitrary
source chunks, private metadata or thumbnails. GPS is opt-in/off by default and requires
metadata preservation. Output embeds the sRGB profile. Preview derivatives carry no capture/
GPS data. Originals are never changed. Source/output bytes, dimensions, effective settings,
warnings and 100*(input-output)/input savings are available; negative savings is labelled larger.

Output preview uses committed converted outputs, not inputs. Reduced image previews keep
aspect/orientation and alpha over checkerboard. Newly encoded raster previews reuse already
validated output pixels (including lossy codec results), avoiding another full PNG/WebP decode.
The existing RAW encoder/preview behavior remains unchanged. Legacy missing previews can be
rendered on demand. PDFium renders only the requested PDF page (default1280px edge,2MP,
300pages,2MiB/page); DOCX shows safe read-only paragraphs/basic tables, not exact Word layout,
with50,000character/1,000cell/500block bounds and explicit truncation. DOCX images, fonts,
headers/footers and complex layouts are not rendered. No HTML injection or external fetches.
Unsupported preview kinds show file details and direct download.

All renderers are local. PDFium's native library and dependency notices ship in the frozen
build; LibreOffice remains external for conversion. Preview work uses supervised workers,
384MiB default cap (larger image budget where needed),30second timeout, quotas and at most
four pending requests. A shared execution lock prevents overlap with conversion workloads;
long-running conversions can make preview requests time out with retry instructions. Cache
keys include output hash, page, renderer/version/options; requests deduplicate. Cache is
retained only when verified, removed with the job, and never served to another owner.
Sampling is resource protection, not a hard OS/network sandbox. Direct file downloads do
not depend on preview, ZIP readiness, or another transcode. One selection is an actual file;
two or more selections use ZIP_STORED with exactly those committed outputs.
