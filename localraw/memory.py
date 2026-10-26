"""Conservative pixel budgets and resident-memory accounting; no image imports."""

from dataclasses import dataclass

import psutil

from .config import MiB

# Header inspection is bounded separately from the full native render. This is a
# cap, not an allocation or a claim that every image needs this much memory.
HEADER_MEMORY_BYTES = 256 * MiB
MIN_RESERVE_BYTES = 256 * MiB


def render_budget(pixels):
    """Total worker RSS cap, including interpreter/native fixed costs and AHD buffers.

    This conservative model is calibrated against the private samples documented in
    MEMORY_OPTIMIZATION.md, not a universal camera/recording-mode memory guarantee.
    """
    return max(HEADER_MEMORY_BYTES, 128 * MiB + pixels * 48)


@dataclass(frozen=True)
class ProcessMemory:
    rss: int
    peak_rss: int
    processes: int


def process_memory(pid):
    """Sum live working sets, including relevant child processes.

    Shared pages can be counted in more than one process. Windows peak working-set
    counters supplement samples, but sums of lifetime peaks aren't simultaneous.
    """
    root = psutil.Process(pid)
    rss = peak = count = 0
    for process in (root, *root.children(recursive=True)):
        try:
            info = process.memory_info()
            rss += info.rss
            peak += max(info.rss, getattr(info, "peak_wset", info.rss))
            count += 1
        except psutil.NoSuchProcess:
            continue
    return ProcessMemory(rss, peak, count)


def available_budget(available, reserve, workers, excluding=None):
    """Return room for one total-worker budget without double-counting live RSS.

    workers maps identifiers to {budget, rss}. System available already excludes
    resident pages: only peers' still-unallocated growth must be reserved. For a
    current worker, credit the resident pages it already owns when comparing a
    *total* RSS budget. Unknown/dead workers get no resident credit.
    """
    growth = sum(
        max(0, worker["budget"] - worker["rss"])
        for identifier, worker in workers.items()
        if identifier != excluding
    )
    current = workers.get(excluding, {})
    resident = min(current.get("rss", 0), current.get("budget", 0))
    return max(0, available - reserve - growth + resident)


def gibibytes(value):
    return f"{value / 1024**3:.2f} GiB"


def admission_error(available, required):
    return (
        f"Not enough available memory: {gibibytes(available)} available; "
        f"this stage needs about {gibibytes(required)} including the safety reserve. "
        "Close memory-heavy apps and retry the retained inputs. Larger RAW images need more memory."
    )
