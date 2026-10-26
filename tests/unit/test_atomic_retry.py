"""Windows transient rename-denial regression observed under workspace sync/indexing."""

import json
import os

import pytest

from localraw.storage import atomic_json


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing-denial retry")
def test_atomic_manifest_retries_without_exposing_partial(tmp_path, monkeypatch):
    from localraw import storage

    target = tmp_path / "manifest.json"
    atomic_json(target, {"generation": "old"})
    original = storage.os.replace
    calls = []

    def replace(source, destination):
        calls.append(1)
        assert json.loads(target.read_text()) == {"generation": "old"}
        if len(calls) < 3:
            raise PermissionError("Transient Windows reader")
        return original(source, destination)

    monkeypatch.setattr(storage.os, "replace", replace)
    monkeypatch.setattr(storage.time, "sleep", lambda _: None)
    atomic_json(target, {"generation": "new"})
    assert len(calls) == 3
    assert json.loads(target.read_text()) == {"generation": "new"}
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing-denial retry")
def test_atomic_manifest_permanent_denial_retains_prior_commit(tmp_path, monkeypatch):
    from localraw import storage

    target = tmp_path / "manifest.json"
    atomic_json(target, {"generation": "old"})
    waits = []

    def denied(*args):
        raise PermissionError("Still locked")

    monkeypatch.setattr(storage.os, "replace", denied)
    monkeypatch.setattr(storage.time, "sleep", waits.append)
    with pytest.raises(PermissionError):
        atomic_json(target, {"generation": "new"})
    assert len(waits) == 5
    assert json.loads(target.read_text()) == {"generation": "old"}
    assert not list(tmp_path.glob("*.part"))
