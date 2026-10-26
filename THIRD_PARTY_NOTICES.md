# CapreConvert distribution notices

The build collects installed distribution license files in its `notices` directory.
Review those files and the precise locked dependency versions before distribution.

- rawpy: MIT; bundles LibRaw (LGPL 2.1 or CDDL 1.0), plus native dependency notices.
  Retain upstream license files and comply with the selected LibRaw license, including
  the applicable source/relinking requirements. https://github.com/letmaik/rawpy
- Pillow: HPND and bundled codec/color-engine licenses (including LittleCMS).
  https://github.com/python-pillow/Pillow
- NumPy: BSD and bundled native runtime notices. https://numpy.org
- FastAPI/Uvicorn and their dependencies: retain their installed distribution notices.
- pypdf: BSD-3-Clause; text-based PDF parsing/extraction, no OCR engine bundled.
  https://github.com/py-pdf/pypdf
- python-docx: MIT; editable OOXML document creation and bundled template assets.
  https://github.com/python-openxml/python-docx
- lxml: BSD-3-Clause with libxml2/libxslt and other bundled native-library notices.
  Retain all license files shipped with its installed wheel. https://lxml.de/
- LibreOffice is an optional external installation for DOCX-to-PDF, not part of the
  CapreConvert distribution. Its own MPL/LGPL and third-party notices accompany its
  installation. https://www.libreoffice.org/about-us/licenses/
- pypdfium2 5.14.0: binding under Apache-2.0 OR BSD-3-Clause; bundled PDFium
  156.0.8076.0 uses BSD-3-Clause and additional third-party codec/font/runtime licenses.
  The complete installed wheel license tree, including BUILD_LICENSES, is copied into
  notices/pypdfium2. Keep those exact files with redistribution. No renderer is downloaded
  at runtime. Upstream: https://github.com/pypdfium2-team/pypdfium2 and
  https://pypdfium2.readthedocs.io/en/stable/readme.html . This is not a legal opinion.
- PyInstaller: GPL with bootloader exception; see its distribution license.
- ExifTool is optional and not bundled in the base build. A metadata-enabled distribution
  must include a tested target-specific ExifTool package and its Perl/ExifTool notices.
- Fraunces regular/italic variable fonts: Copyright 2018 The Fraunces Project Authors,
  SIL Open Font License 1.1. Unmodified font binaries are bundled locally with the complete
  license in `localraw/static/assets/Fraunces-OFL.txt` (also in the packaged static assets).
  Source: https://github.com/google/fonts/tree/main/ofl/fraunces

This is an inventory aid, not a claim that an unreviewed package is distribution-ready.
