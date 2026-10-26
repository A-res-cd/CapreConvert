"""Windows spawn imports the source CLI without needing the web-server modules."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_spawn_cli_import_does_not_load_server_or_decoder():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; import localraw.__main__; "
            "print(json.dumps([name for name in sys.modules "
            "if name.split('.')[0] in {'fastapi', 'uvicorn', 'rawpy', 'numpy', 'PIL'} "
            "or name in {'localraw.app', 'localraw.jobs'}]))",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == []


def test_source_cli_help_remains_available():
    result = subprocess.run(
        [sys.executable, "-m", "localraw", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "CapreConvert: private local document and RAW image conversion" in result.stdout
    assert "--no-browser" in result.stdout
    assert "--workspace" in result.stdout


def test_source_cli_reports_public_brand_and_single_version():
    result = subprocess.run(
        [sys.executable, "-m", "localraw", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout.strip() == "CapreConvert 1.0.0"
