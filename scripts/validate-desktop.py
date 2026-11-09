"""Real Windows bundle install/shortcut/launch checks; future-release transport is a fixture."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localraw import desktop  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--previous-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Report already exists")
    bundle, previous = args.bundle.resolve(), args.previous_bundle.resolve()
    tag, old_tag = bundle.name, previous.name
    archive = bundle.parent / f"CapreConvert-{tag}-windows-x64.zip"
    checksum = archive.with_suffix(".zip.sha256")
    digest = desktop.file_hash(archive)
    report = {
        "version": tag,
        "checks": [],
        "future_release_transport": "local fixture with real frozen ZIP; no GitHub release created",
    }
    with desktop.temporary_directory(ROOT / ".cache", "desktop-qa-") as directory:
        appdata = directory / "appdata"
        root = appdata / "CapreConvert"
        with desktop.managed(root):
            desktop.activate(root, previous, old_tag)
            name = archive.name
            metadata = {
                "tag_name": tag,
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": name + suffix,
                        "state": "uploaded",
                        "size": file.stat().st_size,
                        "browser_download_url": f"https://github.com/{desktop.REPOSITORY}/releases/download/{tag}/{name}{suffix}",
                        "digest": "sha256:" + digest if not suffix else None,
                    }
                    for suffix, file in (("", archive), (".sha256", checksum))
                ],
            }

            def get(url, maximum, destination=None):
                if url == desktop.API:
                    return json.dumps(metadata).encode()
                source = checksum if url.endswith(".sha256") else archive
                assert source.stat().st_size <= maximum
                if destination:
                    import shutil

                    shutil.copyfile(source, destination)
                    return b""
                return source.read_bytes()

            desktop.apply_update(root, desktop.latest(get=get), get=get)
            assert desktop.read_current(root)[0]["current"] == tag
            report["checks"].append(
                "actual older/new frozen bundles: checksum, strict extraction, candidate launch probe and atomic activation"
            )
            links = directory / "shortcuts"
            links.mkdir()
            desktop.shortcuts(root, directory=links)
        script = "$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut($env:CAPRE_LINK); @{target=$l.TargetPath;arguments=$l.Arguments}|ConvertTo-Json -Compress"
        shell = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run(
            [str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env=dict(os.environ, CAPRE_LINK=str(links / "CapreConvert.lnk")),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        link = json.loads(result.stdout)
        executable = desktop.validate_bundle(root / "versions" / tag, tag)
        assert Path(link["target"]) == executable and link["arguments"] == "--launch-installed"
        assert len(list(links.glob("*.lnk"))) == 3
        report["checks"].append(
            "real Windows COM desktop launch/update/recovery shortcut files and resolved launch target"
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = dict(os.environ, LOCALAPPDATA=str(appdata))
        launch = subprocess.Popen(
            [
                link["target"],
                link["arguments"],
                "--no-browser",
                "--workspace",
                str(directory / "workspace"),
                "--port",
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            with httpx.Client(trust_env=False, timeout=2) as client:
                deadline = time.monotonic() + 40
                while True:
                    try:
                        response = client.get(f"http://127.0.0.1:{port}/health")
                        if response.json() == {"status": "ok"}:
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("Installed shortcut launcher did not start the server")
                    time.sleep(0.1)
            assert (directory / "workspace/.localraw-workspace").exists()
            report["checks"].append(
                "actual frozen --launch-installed forwarding starts the offline server using separate workspace"
            )
        finally:
            for process in psutil.process_iter(["exe"]):
                try:
                    if (
                        process.info["exe"]
                        and Path(process.info["exe"]).resolve() == executable.resolve()
                    ):
                        process.terminate()
                        process.wait(timeout=10)
                except psutil.NoSuchProcess:
                    pass
            launch.wait(timeout=10)
        with desktop.managed(root):
            desktop.rollback(root)
            assert desktop.read_current(root)[0]["current"] == old_tag
        report["checks"].append(
            "real retained older executable passes rollback probe; pointer restored; running processes stopped only inside test installation"
        )
        with desktop.managed(directory / "fresh-install") as fresh:
            desktop.activate(fresh, bundle, tag)
            links = directory / "fresh-shortcuts"
            links.mkdir()
            desktop.shortcuts(fresh, directory=links)
            assert desktop.read_current(fresh)[0]["bootstrap"] == tag
        report["checks"].append(
            "fresh full per-user bundle install and retained original recovery launcher"
        )
    online = subprocess.run(
        [str(bundle / f"CapreConvert-{tag}.exe"), "--check-updates"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    report["live_github"] = json.loads(online.stdout)
    assert report["live_github"]["repository"] == desktop.REPOSITORY
    report["checks"].append(
        "frozen stdlib HTTPS/GitHub release metadata check without web server or installer"
    )
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
