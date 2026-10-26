# CapreConvert v0.4.0 ordered plan

Preserve localraw package/distribution, LOCALRAW_* configuration, workspace marker/lock,
sessions/cookies, API/ZIP contracts, browser keys, legacy missing conversion=cr3_to_jpg,
and immutable v0.1/v0.2/v0.3 artifacts. No commit or push.

Gates in order: A registry/immutable contracts; B supervised raster engine; C resize,
codec/alpha/colour/privacy semantics; D jobs/admission/recovery/API; E committed-output
image/PDF/DOCX previews; F direct export; G responsive browser; H measured baseline and
benchmarks; I engine/security/browser checks; J locked dependencies/frozen smoke/archive/hash.

Explicit engine, image/preview and archive capabilities replace overloaded is_raw decisions.
RAW settings/rendering remain unchanged. Raster settings are nested and apply only to raster.
Preview failure never changes committed conversion state; direct download is independent.
Preview jobs serialize with conversion through one shared execution lock, bounded request
admission, memory reserve/RSS/time/disk limits, download leases and content/version cache keys.
PDFium is bundled locally via pypdfium2 (Apache/BSD binding, BSD PDFium plus third-party
notices); review installed wheel license assets and frozen collection before publication.

Baseline: preserve v0.3 encoder/preview code and artifacts. Measure existing reopen-preview
path before considering reuse of processed pixels; do not optimize without evidence.
New codec defaults: balanced JPEG90/WebP85/PNG6; smaller80/75/9; high95/95/3.
Presets never resize; explicit advanced values override presets. WebP lossless exact=True.
Normalize EXIF orientation, sRGB colour (valid ICC transformed independently of alpha),
RGB/RGBA output; unprofiled CMYK uses Pillow fallback with warning. Invalid ICC warns and
uses deterministic mode conversion. Whitelist capture EXIF, GPS off unless explicitly enabled.
PNG/lossless WebP claims concern normalized pixels, not source bytes. Transparent JPEG
composites onto persisted visible #ffffff default. Static JPEG/PNG/WebP only; no raster ZIP.

Validation evidence and unresolved gates go in V0_4_VALIDATION.md. Native fixture tests,
resource/security/recovery, real PDFium/DOCX previews, browser direct/ZIP and frozen native
engines are required. Broad camera/clean-machine/physical-mobile acceptance remains separate.
