# v1.1.1 desktop installation and updater

## Behavior and trust boundary

The complete Windows bundle installs per-user under LocalAppData/CapreConvert/versions.
Desktop/Start-menu shortcuts launch the selected installed version, check for updates,
or restore the previous version. Normal launches retain the minimized host console so
users can stop the server before opening an update. Headless checks/updater helpers stay hidden.
The first installed manager is retained for recovery even if a newer bundle is damaged.

Only explicit host CLI update actions contact the fixed public A-res-cd/CapreConvert GitHub
release API. No update HTTP endpoint or automatic startup/background network check was added.
Conversion workers and session ownership are unchanged. No dependency was added.
The release requires exact stable version/asset names and GitHub HTTPS URLs, bounded
metadata/downloads, SHA-256 sidecar agreement and GitHub digest agreement when provided.
Archive directory bounds, canonical paths, entry types, expanded bytes, CRCs and bundle
identity are checked. The candidate executable must report its expected version before an
atomic current-pointer switch. Complete older versions remain; workspaces/originals are separate.
No running user process is killed. Checksums protect integrity within the trusted GitHub
channel; binaries are not independently code-signed. Future releases must preserve workspace
compatibility or document manual migration; app rollback does not migrate workspace schemas.

## Source checks

- Full unit/integration suite: **255 passed, 3 skipped in 92.82 s**, one existing
  Starlette/httpx deprecation warning. Conditional native/fixture gates are separate from
  the executed packaged native engine checks below.
- After final console forwarding and guarded staging cleanup changes, targeted updater/CLI
  checks: **39 passed in 3.13 s** (overlaps the full suite).
- Checks include valid update/rollback, damaged new bundles, failed commit/probe, interrupted
  and corrupt downloads, digest mismatch, unexpected release metadata, path traversal,
  duplicate/special ZIP entries, GitHub HTTPS redirect policy, numeric versions, no-op updates,
  dedicated-directory/Windows lock rules, CLI launch argument forwarding and real Windows
  COM shortcut creation in isolated test directories.
- Ruff lint/format and git diff whitespace checks pass. Normal CLI import remains free of
  the web server/RAW decoder graph.
- Actual public GitHub metadata was read and validated: latest was v1.1.0 with the expected
  Windows ZIP and SHA-256 assets. No release was created or changed.

## Release validation notes

The first packaging attempt stopped at the existing RAM preflight, publishing no release.
After the user freed RAM, default-policy native smoke passed on an intermediate bundle.
The minimized-console launch refinement was then added and rebuilt for the final artifact.
Packaged defaults/reserve were never lowered. Test compilation checkpoints are unpublished.

The rebuilt default-profile smoke later stopped at document admission when host availability
fell to 1.43 GiB against an approximately 1.46 GiB stage requirement. The final native smoke
passed with the existing `document512` test profile (512 MiB document / 256 MiB preview,
768 MiB reserve). Production remains 768 MiB document / 384 MiB preview / 768 MiB reserve.
Final default-profile acceptance is not inferred from the intermediate default pass.

The final unpublished compilation checkpoint was reconstructed from 511 checked entries in
the fresh PyInstaller COLLECT table. All 21 frozen application code objects matched current
source; the builder additionally verified dependency versions before reusing that compilation.
It then ran the full native smoke rather than skipping gates. All six real document routes,
nine raster operations, protected previews/direct downloads/ZIPs, corrupt RAW rejection,
Windows PE version/branding and seven icon frames passed with Python removed from child PATH.

`python scripts/validate-desktop.py --bundle dist/v1.1.1 --previous-bundle dist/v1.1.0 --output test-results/v1-1-1-desktop-validation.json`
passed. It used real frozen bundles and a local future-release transport fixture to test
checksum/extraction/probes/atomic activation/rollback. It created actual Windows COM shortcuts
in test folders, resolved the launch target, started the installed frozen server through
`--launch-installed` with a separate workspace, and stopped only test-installation processes.
Fresh installation and retained recovery-manager records passed. The final frozen
`--check-updates` command successfully read live GitHub over HTTPS, reporting local 1.1.1 and
public latest 1.1.0. Interactive confirmation dialogs were not automated.

## Delivered artifacts

- `dist/v1.1.1/CapreConvert-v1.1.1.exe`, complete `_internal`, install/update CMD entrypoints.
- `dist/CapreConvert-v1.1.1-windows-x64.zip`: **43,269,953 bytes, 515 files**.
- Matching `.zip.sha256`: `6e18d5f3ae10ca52df1170b8fcbf3ccc61bd571f2d01f79938055ca07dcedb7a`.

Independent CRC, checksum, archive-root/path and installer-entrypoint checks pass. Existing
v1.0.0 and v1.1.0 release ZIP hashes remain unchanged. No user workspace/original was removed,
no user application was terminated, no real Desktop/Start-menu shortcut was overwritten during
QA, and no commit, push or GitHub publication was performed. Evidence is in
`test-results/package-smoke.json` and `test-results/v1-1-1-desktop-validation.json`.

## Remaining acceptance limits

This is Windows x64 per-user installation. Clean-machine/SmartScreen/corporate-policy,
physical-phone and secondary-platform acceptance remain open. Live installation of a future
public release cannot be exercised until that release exists; a local transport fixture with
real packaged binaries validates the update transaction separately from live GitHub/TLS.
Users of v1.1.0 and earlier need one manual upgrade/install to obtain the updater. Each
future latest stable release must contain the standard ZIP and matching checksum.
LibreOffice stays external and is not installed or updated by this updater.
