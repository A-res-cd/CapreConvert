from types import SimpleNamespace

import psutil
import pytest

from localraw.config import MiB
from localraw.jobs import Jobs
from localraw.memory import available_budget, process_memory
from localraw.storage import Workspace
from localraw.uploads import Uploads


def test_admission_reserves_future_growth_and_credits_current_rss():
    # Available excludes the resident 300+100 MiB already; reserving them again
    # incorrectly rejects a worker that fits in the unallocated headroom.
    workers = {
        "peer": {"budget": 500 * MiB, "rss": 300 * MiB},
        "current": {"budget": 256 * MiB, "rss": 100 * MiB},
    }
    assert available_budget(1000 * MiB, 256 * MiB, workers, "current") == 644 * MiB
    assert available_budget(1000 * MiB, 256 * MiB, workers) == 388 * MiB
    workers["current"]["rss"] = 300 * MiB
    # Don't turn an over-budget measurement into extra admission credit.
    assert available_budget(1000 * MiB, 256 * MiB, workers, "current") == 800 * MiB
    assert available_budget(128 * MiB, 256 * MiB, workers) == 0


def test_memory_tree_tolerates_a_child_exiting_and_keeps_windows_peak(monkeypatch):
    class Process:
        def __init__(self, pid):
            self.pid = pid

        def children(self, recursive):
            return [Process(2), Process(3)]

        def memory_info(self):
            if self.pid == 3:
                raise psutil.NoSuchProcess(3)
            return SimpleNamespace(rss=self.pid * 100, peak_wset=self.pid * 150)

    monkeypatch.setattr("localraw.memory.psutil.Process", Process)
    measured = process_memory(1)
    assert (measured.rss, measured.peak_rss, measured.processes) == (300, 450, 2)


@pytest.fixture
def supervisor(settings):
    workspace = Workspace(settings).open()
    try:
        yield Jobs(workspace, settings, Uploads(workspace, settings))
    finally:
        workspace.close()


def test_larger_second_image_waits_for_peer_instead_of_failing(supervisor, monkeypatch):
    sent = []
    monkeypatch.setattr("localraw.jobs.worker_rss", lambda pid: 100 * MiB)
    monkeypatch.setattr(
        "localraw.jobs.psutil.virtual_memory", lambda: SimpleNamespace(available=2048 * MiB)
    )
    current = {
        "process": SimpleNamespace(pid=2),
        "item": {"id": "second"},
        "budget": 256 * MiB,
        "requested_budget": 1024 * MiB,
        "error": None,
        "connection": SimpleNamespace(send=sent.append),
    }
    peer = {
        "process": SimpleNamespace(pid=1),
        "budget": 1024 * MiB,
        "error": None,
        "admitted": True,
    }
    active = {"first": peer, "second": current}
    job = {"warnings": [], "state": "converting"}
    supervisor._admit_render(job, current, active)
    assert not sent and current["item"]["memory"]["waiting"]
    assert current["error"] is None
    del active["first"]
    supervisor._admit_render(job, current, active)
    assert sent == [{"admitted": True}]
    assert current["admitted"] and not current["item"]["memory"]["waiting"]


def test_unmonitorable_worker_cannot_receive_memory_credit(supervisor, monkeypatch):
    def denied(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr("localraw.jobs.worker_rss", denied)
    task = {"process": SimpleNamespace(pid=1), "budget": 256 * MiB, "error": None}
    workers = supervisor._read_workers({"one": task})
    assert workers["one"]["rss"] == 0
    assert "could not monitor" in task["error"]


def test_disappearing_waiter_does_not_abort_sibling_workers(supervisor):
    def broken(message):
        raise BrokenPipeError("worker exited")

    task = {"connection": SimpleNamespace(send=broken), "error": None}
    supervisor._send_admission(task, True)
    assert "exited while waiting" in task["error"]


@pytest.mark.parametrize("cancelled, rss", [(True, 100 * MiB), (False, 300 * MiB)])
def test_cancelled_or_over_header_budget_worker_never_receives_render_grant(
    supervisor, monkeypatch, cancelled, rss
):
    sent = []
    monkeypatch.setattr("localraw.jobs.worker_rss", lambda pid: rss)
    monkeypatch.setattr(
        "localraw.jobs.psutil.virtual_memory", lambda: SimpleNamespace(available=4 * 1024 * MiB)
    )
    task = {
        "process": SimpleNamespace(pid=2),
        "item": {"id": "one"},
        "budget": 256 * MiB,
        "requested_budget": 800 * MiB,
        "error": None,
        "connection": SimpleNamespace(send=sent.append),
    }
    supervisor._admit_render(
        {"state": "cancelling" if cancelled else "converting", "warnings": []}, task, {"one": task}
    )
    assert sent == [{"admitted": False}] and task["error"]
    assert task["budget"] == 256 * MiB


def test_optional_diagnostics_failure_does_not_abort_conversion(supervisor, monkeypatch):
    def denied(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr("localraw.jobs.process_memory", denied)
    assert supervisor.memory_status()["diagnostics_available"] is False


def test_generic_worker_error_preserves_actionable_parent_memory_reason(supervisor):
    task = {"item": {"id": "one"}, "error": "Parent safety budget exceeded."}
    supervisor._message({}, task, {}, {"error": "Insufficient memory or workspace capacity."})
    assert task["error"] == "Parent safety budget exceeded."


def test_worker_can_cancel_while_parked_before_unpacking(monkeypatch, tmp_path):
    from localraw.worker import run_worker

    sent = []

    class Connection:
        closed = False

        def send(self, message):
            sent.append(message)

        def poll(self, timeout):
            return False

        def close(self):
            self.closed = True

    def fake_convert(*args):
        args[5](100)
        pytest.fail("A cancelled parked worker must not unpack.")

    monkeypatch.setattr("localraw.conversion.convert", fake_convert)
    connection = Connection()
    run_worker(
        "unused.cr3", str(tmp_path / "out.jpg"), {}, {}, connection, SimpleNamespace(is_set=lambda: True)
    )
    assert any("cancelled while waiting" in item.get("error", "") for item in sent)
    assert connection.closed
