import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from localraw.app import create_app
from localraw.config import Settings
from localraw.errors import Problem
from localraw.storage import Workspace, atomic_json


def test_invalid_settings():
    for values in (
        {"port": 80},
        {"default_concurrency": 2, "max_concurrency": 1},
        {"raw_max_bytes": 0},
        {"tls_cert": "cert"},
        {"unknown": 2},
    ):
        with pytest.raises(ValidationError):
            Settings(**values)


def test_health_and_local_page(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/health").json() == {"status": "ok"}
        page = client.get("/")
        assert page.status_code == 200
        assert "https://" not in page.text
        assert client.get("/static/styles.css").status_code == 200
        assert client.get("/docs").status_code == 404


def test_exclusive_workspace(settings):
    first = Workspace(settings).open()
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            Workspace(settings).open()
    finally:
        first.close()
    Workspace(settings).open().close()


def test_atomic_manifest_and_quota(settings):
    workspace = Workspace(settings).open()
    try:
        atomic_json(workspace.root / "state.json", {"version": 1})
        assert not list(workspace.root.glob("*.part"))
        workspace.reserve("first", 1024)
        with pytest.raises(Problem):
            workspace.reserve("second", settings.workspace_quota_bytes)
        workspace.release("first")
    finally:
        workspace.close()


def test_workspace_requires_dedicated_directory(settings):
    settings.workspace.mkdir()
    original = settings.workspace / "original.CR3"
    original.write_bytes(b"user original")
    with pytest.raises(RuntimeError, match="dedicated"):
        Workspace(settings).open()
    assert original.read_bytes() == b"user original"
