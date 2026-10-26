import time
from collections import deque

from localraw.config import GiB
from localraw.jobs import Jobs
from localraw.storage import Workspace
from localraw.uploads import Uploads


def test_final_worker_message_arriving_between_poll_and_exit_is_preserved(settings, monkeypatch):
    workspace = Workspace(settings).open()
    try:
        supervisor = Jobs(workspace, settings, Uploads(workspace, settings))
        messages = deque()

        class Connection:
            def poll(self):
                return bool(messages)

            def recv(self):
                return messages.popleft()

        class ExitingProcess:
            checked = False

            def is_alive(self):
                if not self.checked:
                    messages.append({"error": "Final decoder error must survive exit."})
                    self.checked = True
                return False

        item = {"id": "test", "state": "decoding"}
        job = {"state": "converting", "settings": {"concurrency": 1}}
        failures = []

        def start(job, item, active):
            active[item["id"]] = {
                "process": ExitingProcess(),
                "connection": Connection(),
                "item": item,
                "budget": GiB,
                "started": time.monotonic(),
                "cancel_at": None,
                "result": None,
                "error": None,
            }
            return True

        monkeypatch.setattr(supervisor, "_start_file", start)
        monkeypatch.setattr(supervisor, "_finish_file", lambda job, task: failures.append(task["error"]))
        supervisor._supervise(job, deque([item]))
        assert failures == ["Final decoder error must survive exit."]
    finally:
        workspace.close()
