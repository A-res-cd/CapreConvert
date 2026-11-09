# v1.1.0 ordered implementation

1. Extend the capability registry and immutable settings with ODT ↔ DOCX and ODT ↔ PDF.
2. Validate bounded ODT packages in workers before LibreOffice; retain isolated profiles,
   cancellation, resource admission, original preservation and atomic publication.
3. Add protected ODT content previews and picker descriptions, using existing export routes.
4. Run adversarial/package, native document, API and browser regressions; record actual results.
5. Build v1.1.0, run frozen native conversion smoke, verify archive/checksum and record limits.

ODF text means .odt; Word means .docx. PDF → ODT extracts selectable text via the existing
PDF → DOCX engine, then exports ODT through local LibreOffice. No OCR/layout reconstruction.
LibreOffice remains an external local installation. Previous releases remain intact.
