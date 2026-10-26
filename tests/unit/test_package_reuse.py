"""Asset rebuilds must reject stale frozen application code or dependencies."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("change", ["code", "dependency", "identity"])
def test_verified_reuse_refuses_stale_bundle_before_copy(tmp_path, monkeypatch, change):
    spec = importlib.util.spec_from_file_location("build_package", ROOT / "scripts/build-package.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    sources = tmp_path / "localraw"
    sources.mkdir()
    source = sources / "worker.py"
    source.write_text("def run():\n    return 42\n", encoding="utf-8")
    bundle = tmp_path / "existing"
    internal = bundle / "_internal"
    internal.mkdir(parents=True)
    metadata = {
        "version": "0.4.0",
        "platform": "windows",
        "architecture": "x64",
        "executable": "app.exe",
    }
    if change == "identity":
        metadata["version"] = "0.3.0"
    (bundle / "release.json").write_text(json.dumps(metadata), encoding="utf-8")
    frozen = compile(
        "def run():\n    return 41\n" if change == "code" else source.read_text(),
        "localraw/worker.py",
        "exec",
    )

    class ExplicitFrozenCodeDouble:
        def __init__(self, *args):
            pass

        def open_embedded_archive(self, *args):
            return self

        def extract(self, *args):
            return frozen

    monkeypatch.setattr("PyInstaller.archive.readers.CArchiveReader", ExplicitFrozenCodeDouble)
    if change == "dependency":
        distribution = internal / "numpy-0.0.dist-info"
        distribution.mkdir()
        (distribution / "METADATA").write_text("Name: numpy\nVersion: 0.0\n", encoding="utf-8")
    destination = tmp_path / "new-build"
    with pytest.raises(RuntimeError, match="differs"):
        builder.reuse_compiled(
            bundle,
            destination,
            SimpleNamespace(version="0.4.0", system="windows", architecture="x64", executable="app.exe"),
        )
    assert not destination.exists()
