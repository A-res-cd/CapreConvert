# CapreConvert API specification

All routes under `/api/v1`; `/health` also available for local process supervision.
Public health is minimal. POST sessions exchanges a bootstrap/pairing credential for an
HttpOnly SameSite cookie and CSRF token. Authenticated session recovery returns CSRF.

Authenticated capabilities expose application_name (CapreConvert), version 0.3.0, format
descriptors/engine availability and configured limits. POST uploads registers
filename and byte size, PUT uploads/{id}/content streams exact bytes, DELETE releases unused
uploads. POST jobs freezes upload IDs/settings; Idempotency-Key prevents duplicate jobs.
GET jobs, jobs/{id}, files, errors and summary restore session-owned work. Lists paginate.
POST cancel is idempotent. Results/{output_id} and archive return attachment streams;
archive returns 409 until committed. DELETE terminal jobs rejects active downloads.

Errors: `{error:{code,message,request_id,details}}`. Status codes 401 authentication,
403 security, 404 missing/foreign, 409 state, 413 size/quota, 422 validation,
429 queue/rate limit, 507 workspace capacity. No internal paths or stack traces in responses.

All timestamps are UTC Unix seconds. Mutations require exact Origin plus X-CSRF-Token,
except credential exchange (which still requires Origin). JSON requests are limited to
64 KiB before parsing. PUT content uses raw binary and registered exact byte counts.

| Method | Route after /api/v1 | Result |
|---|---|---|
| GET | /health | Public `{status:"ok"}` |
| POST | /sessions | `{credential}` → cookie, csrf_token, expires_at |
| GET | /sessions | Authenticated CSRF recovery after refresh |
| GET | /capabilities | Brand/version, conversions, decoder flags, input types, limits and metadata availability |
| GET | /resources | Authenticated system available RAM, reserve, sampled application-tree RSS/peak and worker counts |
| POST | /uploads | `{filename,size_bytes}` → 201 upload_id, expires_at |
| PUT | /uploads/{upload_id}/content | Binary → ready upload; incomplete 422, oversized 413 |
| DELETE | /uploads/{upload_id} | 204; retained job references / receiving state → 409 |
| POST | /jobs | `{upload_ids,settings}` → 202; optional Idempotency-Key header |
| GET | /jobs | Session-owned summaries, newest first |
| GET | /jobs/{job_id} | State, settings, exact counters, active stages, expiry, package status |
| GET | /jobs/{job_id}/files | Per-file states, names, warnings and opaque output IDs |
| POST | /jobs/{job_id}/cancel | Idempotent; queued work cancels immediately |
| GET | /jobs/{job_id}/errors | File and job errors/warnings |
| GET | /jobs/{job_id}/results/{output_id} | Successful typed JPG/PNG/WebP/PDF/DOCX attachment only |
| GET | /jobs/{job_id}/previews/{output_id} | Owned inline JPEG or alpha-preserving PNG preview; `?thumbnail=true` for thumbnail |
| POST | /jobs/{job_id}/exports | `{output_ids:[...]}` → 201 export_id, count, size_bytes; selected successful registered outputs |
| GET | /jobs/{job_id}/exports/{export_id} | Authorized selected-output ZIP attachment |
| GET | /jobs/{job_id}/archive | Committed ZIP attachment; 409 otherwise |
| GET | /jobs/{job_id}/summary | Separate JSON attachment including owned retry upload IDs |
| DELETE | /jobs/{job_id} | Terminal jobs only; active work/download leases → 409 |

List routes accept `offset >= 0`, `1 <= limit <= 100` and return
`{items,total,offset,limit}`. Defaults: jobs 25, files/errors 50. Foreign resource IDs return
404. Job settings are frozen: jpeg_quality 70–100 (95), filename_suffix (empty; safe letters,
numbers, spaces, underscores, hyphens; max 40), white_balance camera/auto (camera),
preserve_metadata (true), include_gps (false), concurrency 1–2 (1; host maximum enforced).
The UI initializes concurrency from the configured host default. Identical key/payload
retries return the original job; conflicting payload returns 409. Keys are max 128 characters.

v0.3.0 adds immutable `settings.conversion`: `cr3_to_jpg` (default for legacy requests),
`cr3_to_png`, `docx_to_pdf`, or `pdf_to_docx`. Uploads accept CR3/ZIP/DOCX/PDF, but job
creation rejects inputs not matching the selected conversion before scheduling. ZIP inputs
are supported only for RAW workflows. New file records carry `output_extension` and
`media_type`; legacy JPEG records remain readable without those fields. Documents include
`pages` instead of image dimensions. Result paths and MIME types derive from validated job
settings, never client-controlled output paths. Generic whole/selected ZIPs preserve
committed output bytes and source folders.

`conversions` capabilities contain `id`, `label`, `input_extensions`, `output_extension`,
`media_type`, `is_raw`, `available`, `setup_message`, and `limitations`. DOCX-to-PDF is
available only when the host discovers/configures local LibreOffice. This exposes no local
executable path. Text-based PDF-to-DOCX extracts editable paragraphs/page breaks; no OCR,
image/table/precise-layout reconstruction. Document upload/output/expanded/page/text/content
limits appear in `limits`; parsing/rendering stays in supervised child processes.

Legacy settings without `conversion`, saved cookies, routes and idempotency keys remain
compatible. Missing format defaults to JPEG without rewriting historical request hashes.
The application identity changes publicly while the internal cookie/workspace identifiers
remain stable; see V0_3_MIGRATION.md.

RAW file records include optional `preview` dimensions/size/hash with nested `thumbnail` metadata.
An optional `memory` object reports the worker budget, measured peak RSS, admission headroom,
and whether an image is waiting for a peer to release memory. These are diagnostics, not
new lifecycle states. `/resources` includes no paths, process IDs or job ownership data;
`diagnostics_available=false` marks an unavailable aggregate measurement. Windows per-file
worker lifetime peak counters supplement parent samples; other platforms use RSS samples.
Only committed successful images have previews. Preview absence does not prevent JPG export.
Preview GETs use inline disposition and deletion leases; full-resolution results remain attachments.
Export POST uses the existing Origin/CSRF checks and runs bounded packaging outside the event
loop. Empty/duplicate selections return 422; missing, failed or foreign output IDs return 404.
Selection order normalizes to job order and repeated identical sets reuse a prepared ZIP.
One selection ZIP is built globally at a time (409 if busy), with quota reservations, atomic
publication and a job lease. Up to `export_cache_per_job` ZIPs (default 3) are retained; cache
eviction never deletes an active download. Export artifacts expire with their parent job.


## v0.4 additive contracts

Nine raster conversion IDs: jpg_to_png, png_to_jpg, jpg_to_webp, png_to_webp,
webp_to_jpg, webp_to_png, jpg_to_jpg, png_to_png, webp_to_webp. .jpeg aliases JPEG.
Capabilities retain is_raw and all old keys, adding engine (raw/raster/document),
preview_kind (image/pdf/docx/none), archive_input, direct_export, settings_fields and
selection_export=one_direct_multiple_zip. Only RAW contracts accept input ZIPs.

settings.raster is immutable and defaults to preset=balanced, max_width/max_height=null,
jpeg_quality/webp_quality/png_compression=null (preset values), webp_lossless=false,
background=#ffffff. Bounds: resize1..32768, JPEG70..100, WebP1..100, PNG0..9.
Raster-only options never alter RAW/document behavior. Legacy omitted conversion stays
cr3_to_jpg. Files add source_bytes, source_width/source_height (raster), effective_settings,
orientation-normalized width/height, warnings and savings_percent. Negative savings means
an increase. Existing success size_bytes is output bytes; legacy source bytes may be absent.

GET /jobs/{job_id}/output-preview/{output_id}?page=1 accepts only owned committed output
IDs, never paths. Images/PDF pages return reduced inline image/png, X-Preview-Pages and
X-Preview-Cached. PDF pages are one-based and rendered lazily. DOCX returns constrained
JSON {kind,blocks:[{type:paragraph,text}|{type:table,rows}],truncated,notice,cached}.
Unsupported renderers return details with kind=none. Failure uses 422 PREVIEW_FAILED,
resource/timeout 503, full queue429, quota507; download remains independent. Previews
share global conversion admission, leases, bounded workers and retention. Cache identity
includes output hash, renderer/version, options and page; validated caches survive restart.

Existing /exports POST/GET and /archive always return ZIPs. Browser dispatches one selected
successful ID to /results/{output_id}, and multiple to /exports. One-result primary Download
uses /results regardless of ZIP/preview readiness. No transcoding occurs during download.


## v1.0 picker metadata (additive)

Authenticated capabilities add formats:[{id,label,short_label,category}], with category
images/documents. Conversion entries add source_format and target_format normalized IDs.
JPG/JPEG share jpg; ZIP is only a CR3 input container, never a format option. Existing
keys, IDs, routes and legacy cr3_to_jpg defaults remain. Picker support/availability comes
only from advertised pairs; labels/ID parsing/extensions do not establish format identity.
Duplicate pair variants are ambiguous in the picker and disable Open converter; explicit
advertised deep links still identify an engine unambiguously. No conversion semantics change.
