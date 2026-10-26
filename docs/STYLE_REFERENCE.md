# Styling reference

Requested repository: https://github.com/A-res-cd/capstone_repository.git

Latest pushed commit verified through GitHub's repository metadata and PushEvent API:
`075c146985a71b375967d824a7b16575a9bc3211`, branch `aresver-css`, pushed
2026-10-17 10:16:22 Asia/Manila (02:16:22 UTC). Default `main` points to the older
`d296f6a7cb23c16ab20d0939898c5c0bef902759`; it is not the styling reference.

Reference source files inspected at that exact commit:
- app/static/css/base/root.css and global.css
- components/_header.css, _nav.css, _buttons.css, _forms.css, _detail-card.css,
  _record-card.css and _review-paper.css
- pages/_home.css, _archive.css, _repository.css and _analytics.css
- templates/base.html, index.html and partials/header.html / navbar.html

Implementation direction: paper #FAF9F4 / #FDFCF7, indigo #2E3F92 / #1B1C8F,
orange #F39C12 / #E67E22, theme-aware dark surfaces, Segoe UI body and locally bundled
Fraunces display type. Use ruled paper, warm headers, asymmetric card corners, subtle
offset shadows, outlined status stamps, and a compact collapsible navigation shell.
LocalRAW's conversion, pairing, batch, preview and selected-export workflows stay intact.
Retain 44px targets, keyboard navigation and reduced-motion behavior. Orange action labels
use dark ink for contrast. No CAPRE branding, accounts or runtime font/CDN dependency.

Reference clone lives in ignored .reference/ for read-only source inspection. No reference
application code is executed. Windows delivery is staged separately because the previous
preview build is currently running.

Local font sources (unmodified Google Fonts distributions, OFL 1.1 included):
- https://github.com/google/fonts/blob/main/ofl/fraunces/Fraunces%5BSOFT,WONK,opsz,wght%5D.ttf
  SHA-256: 177ff6c0f14e5550a3c624247cd1189611d4eb65d000b14944c63d967958abbb
- https://github.com/google/fonts/blob/main/ofl/fraunces/Fraunces-Italic%5BSOFT,WONK,opsz,wght%5D.ttf
  SHA-256: b24448c43702fac4ee856781d461a0dfba8d8e594b6e8e190234b75fed2c0e01

Executed validation: `python -m pytest tests/e2e -q` — 12 passed in 210.35 seconds,
covering existing conversion/preview/export flows and new navigation. After visual review,
removed the upload-zone background transition to keep theme changes readable; reran the
two navigation/theme/mobile checks — 2 passed in 5.96 seconds. Screenshots capture settled
transitions and were inspected in both themes and mobile navigation. Node syntax, Ruff and
Prettier checks pass. Artifacts: test-results/style-light.png, style-dark.png,
style-mobile-navigation.png, preview-desktop.png and preview-mobile.png.

Windows build: dist-styled/LocalRAW/LocalRAW.exe, built successfully in 70.83 seconds.
`python scripts/smoke-package.py --dist-dir dist-styled/LocalRAW` passed: native diagnostics,
protected API routes and all bundled static/font assets match source bytes, with Python
removed from the child PATH. The running preview distribution was left intact.
