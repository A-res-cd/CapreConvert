# Reproducible memory benchmarks

Run `scripts/benchmark-memory.py` against the baseline and optimized application on the
same machine, with the same private CR3 files and settings. It launches a separate local
application with an empty dedicated workspace, random port, no browser and independent
session. It never connects to or changes a running user's workspace.

The harness uses the existing authenticated API and actual decoder. It streams uploads
in 1 MiB chunks, constructs input ZIPs on disk, and downloads results to temporary files.
No RAW or ZIP payload is loaded into a Python bytes object in the harness. Application
workspaces and intermediate benchmark files are removed after the application exits;
the input files and JSON report remain.

## Input provenance

Keep private CR3 files outside public source and packages. Supply either a JSON manifest
beside them or `--data-dir PATH --provenance "source and permission description"`.
The data-directory form scans direct CR3 children and records their hashes before work.
Manifest input paths must resolve inside the manifest directory, and every file must
have an explicit provenance description and matching SHA-256. Optional expected output
dimensions describe the full visible image after orientation:

```json
[
  {
    "filename": "private-sample.cr3",
    "provenance": "User-owned local photograph; private benchmark, no redistribution",
    "sha256": "<actual SHA-256>",
    "camera": "<known camera>",
    "mode": "<known RAW or C-RAW mode>",
    "width": 5536,
    "height": 3692
  }
]
```

If no real inputs are supplied, idle, corrupt-input and simulated policy rejection can
still run. Real single, batch, ZIP, repeat and cancellation scenarios are recorded as
blocked. Synthetic inputs never substantiate real-camera compatibility.

## Commands

Windows examples, using the private extracted samples recorded for this investigation:

```powershell
# Preserved baseline: its original fixed guard is kept intact.
.\.venv\Scripts\python.exe scripts/benchmark-memory.py --executable dist/v0.1.0/LocalRAW-v0.1.0.exe --manifest test-results/memory-inputs/manifest.json --label baseline --output test-results/memory-baseline.json

# Optimized source before packaging.
.\.venv\Scripts\python.exe scripts/benchmark-memory.py --manifest test-results/memory-inputs/manifest.json --label optimized-source --output test-results/memory-optimized-source.json

# Optimized packaged build after building v0.2.0.
.\.venv\Scripts\python.exe scripts/benchmark-memory.py --executable dist/v0.2.0/LocalRAW-v0.2.0.exe --manifest test-results/memory-inputs/manifest.json --label optimized-v0.2.0 --output test-results/memory-optimized-v0.2.0.json

# Focused cancellation during native processing, rather than initial import/header work.
.\.venv\Scripts\python.exe scripts/benchmark-memory.py --executable dist/v0.2.0/LocalRAW-v0.2.0.exe --manifest test-results/memory-inputs/manifest.json --scenarios cancel --cancel-after 2 --output test-results/memory-cancel-under-load-v0.2.0.json
```

Reports refuse overwrite: use a new label/output for another measurement. `--scenarios`
accepts a subset of `idle single batch zip repeat cancel corrupt low-memory`.
Defaults are 200 ms sampling, 3 seconds idle, up to 3 distinct input photos, 3 repeated
jobs, one conversion worker and JPEG quality 95. `--batch-size`, `--repetitions`,
`--idle-seconds`, `--cancel-after`, `--timeout` and `--interval` are configurable.

`--config PATH` supplies explicit application settings and records every override in the
report. The harness controls workspace, port and local HTTP launch, so those fields
must be omitted from the config. Baseline guard overrides must be identified as controlled
experiments; they do not demonstrate that the original default could accept a job.

## Recorded evidence and limits

Each workload records sampled server/process-tree RSS peaks, per-process Windows lifetime
peak working sets, minimum system available memory, maximum process and conversion-worker
counts, workspace disk peak, upload/conversion/cancellation durations, terminal states,
file errors, retained temporary files and post-deletion workspace size. Newer application
resource diagnostics are included when available; older versions return 404 and are tolerated.

The tree includes the launched application and descendants, excluding this benchmark
driver and a browser. Ordinary Windows launcher/conhost children count toward process
and RSS totals; multiprocessing spawn command lines identify conversion workers.
Summed RSS can count shared DLL pages more than once. A sampled peak is a lower bound
at the chosen interval. Windows lifetime peaks belong to individual processes and must
not be summed as a simultaneous process-tree peak. Background host activity is not
controlled; compare repeated trials and the reported available memory before drawing
broad hardware conclusions.

Successful full-resolution JPEGs are decoded after workers exit in the benchmark driver.
Checks cover RGB mode, expected dimensions when supplied, normalized EXIF orientation, 4:4:4 sampling,
ICC presence, committed/downloaded SHA-256, decoded-pixel SHA-256, and quantization/ICC
hashes. Compare decoded pixels and quantization hashes across before/after runs to detect
rendering or quality changes. ICC profile creation timestamps can change the profile and
whole-JPEG hash even when rendered pixels are identical. This does not replace camera-mode,
color-reference or detailed metadata validation.

Corrupt input is deliberately invalid bytes. The report distinguishes actual decoder
rejection from earlier memory admission rejection. Low-memory mode starts a second
isolated application whose configured reserve exceeds physical RAM; this tests safe policy
rejection without exhausting the host. It does not demonstrate real OS paging/OOM behavior.
Cancellation reports a missed test when the job finishes or is rejected before cancellation.
The default 0.5-second delay can cancel while a worker is importing or inspecting its header.
For cancellation under native load, use a longer delay and inspect the admitted render
budget and worker RSS in the report; elapsed time alone does not prove that rendering began.

Executed measurements and conclusions for this change are in MEMORY_OPTIMIZATION.md
and CODEX_HANDOFF.md. Do not infer a universal minimum RAM requirement from three private
photos or from admission policy values.
