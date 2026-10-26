# CapreConvert v0.4 migration

Finish running work and close older app; extract the whole v0.4.0 folder, keeping _internal.
Originals and old v0.1/v0.2/v0.3 releases stay untouched. No workspace relocation or destructive
migration. All v0.3 identity guarantees in V0_3_MIGRATION.md remain, including aliases,
environment variables, marker/lock, cookies, preferences, owners, routes and IDs.

Missing conversion continues to mean cr3_to_jpg; missing raster settings use defaults which
never apply to RAW/document engines. Old JPG rendering/default quality/dimensions are unchanged.
Old completed outputs keep direct download. Missing image/document preview details are derived
only in bounded workers on demand; a failure leaves the committed output usable. New PNG
preview extension fields default to legacy JPEG when absent. Verified preview caches survive
restart; stale/partial/corrupt cache files regenerate safely. Active jobs remain interrupted,
with explicit retained-input retry preserving their original settings.

One selected result now downloads directly for every registered output; multi-selection ZIP
and explicitly labelled all-as-ZIP retain existing endpoint contracts. Browser preference keys
are preserved. New jobs use nested immutable raster settings, typed paths/MIME and new IDs.
Older binaries cannot understand these jobs: use a separate backed-up workspace for rollback.
LibreOffice remains optional/external for DOCX-to-PDF. Basic DOCX preview needs no LibreOffice.
