from types import SimpleNamespace

import pytest

from localraw.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(workspace=tmp_path / "private", min_free_bytes=0)


@pytest.fixture
def ample_memory(monkeypatch):
    # Parent admission double only. No test image allocates meaningful memory.
    monkeypatch.setattr(
        "localraw.jobs.psutil.virtual_memory", lambda: SimpleNamespace(available=16 * 1024**3)
    )
