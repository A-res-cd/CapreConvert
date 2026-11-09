"""Updater transaction/security tests; remote fixtures never execute downloaded code."""

import hashlib
import io
import json
import os
import stat
import sys
import urllib.error
import urllib.request
import zipfile
from types import SimpleNamespace

import pytest

from localraw import desktop


def bundle(path, tag):
    path.mkdir(parents=True)
    (path / "_internal").mkdir()
    (path / "_internal/python312.dll").write_bytes(b"DLL fixture")
    (path / f"CapreConvert-{tag}.exe").write_bytes(b"MZ fixture, never executed")
    (path / "release.json").write_text(
        json.dumps(
            {
                "application": "CapreConvert",
                "version": tag[1:],
                "tag": tag,
                "platform": "windows",
                "architecture": "x64",
                "executable": f"CapreConvert-{tag}.exe",
            }
        )
    )
    return path


@pytest.fixture
def installed(tmp_path):
    root = tmp_path / "installed"
    root.mkdir()
    (root / ".capreconvert-install").write_text(desktop.MARKER)
    (root / "versions").mkdir()
    source = bundle(tmp_path / "old", "v1.1.1")
    desktop.activate(root, source, "v1.1.1", check=lambda *a: None)
    return root


def release_fixture(tmp_path, tag="v1.2.0"):
    source = bundle(tmp_path / "new", tag)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in source.rglob("*"):
            if file.is_file():
                archive.writestr(tag + "/" + file.relative_to(source).as_posix(), file.read_bytes())
    data = payload.getvalue()
    name = f"CapreConvert-{tag}-windows-x64.zip"
    digest = hashlib.sha256(data).hexdigest()
    checksum = f"{digest}  {name}\n".encode()
    metadata = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": name + suffix,
                "state": "uploaded",
                "size": len(content),
                "browser_download_url": f"https://github.com/{desktop.REPOSITORY}/releases/download/{tag}/{name}{suffix}",
                "digest": "sha256:" + digest if not suffix else None,
            }
            for suffix, content in (("", data), (".sha256", checksum))
        ],
    }

    def get(url, maximum, destination=None):
        content = (
            json.dumps(metadata).encode()
            if url == desktop.API
            else checksum
            if url.endswith(".sha256")
            else data
        )
        assert len(content) <= maximum
        if destination:
            destination.write_bytes(content)
            return b""
        return content

    return metadata, get


def test_verified_update_atomic_pointer_originals_and_rollback(installed, tmp_path):
    _, get = release_fixture(tmp_path)
    original = installed.parent / "original-photo.cr3"
    original.write_bytes(b"original")
    release = desktop.latest(get=get)
    calls = []
    assert desktop.apply_update(installed, release, get=get, check=lambda p, t: calls.append((p, t)))
    record, current = desktop.read_current(installed)
    assert record == {"schema": 1, "current": "v1.2.0", "previous": "v1.1.1", "bootstrap": "v1.1.1"}
    assert current.name == "v1.2.0" and len(calls) == 2
    assert original.read_bytes() == b"original"
    assert (installed / "versions/v1.1.1/release.json").is_file()
    assert not list(installed.glob("download-*")) and not list(installed.glob("stage-*"))
    desktop.rollback(installed, check=lambda *a: None)
    assert desktop.read_current(installed)[0]["current"] == "v1.1.1"


def test_recovery_works_when_new_bundle_is_damaged(installed, tmp_path):
    source = bundle(tmp_path / "next", "v1.2.0")
    desktop.activate(installed, source, "v1.2.0", check=lambda *a: None)
    (installed / "versions/v1.2.0/release.json").unlink()
    desktop.rollback(installed, check=lambda *a: None)
    assert desktop.read_current(installed)[0]["current"] == "v1.1.1"


@pytest.mark.parametrize("failure", ["offline", "checksum", "digest", "length", "probe", "commit"])
def test_interrupted_update_keeps_current(installed, tmp_path, monkeypatch, failure):
    _, get = release_fixture(tmp_path)
    release = desktop.latest(get=get)
    before = (installed / "current.json").read_bytes()

    def broken(url, maximum, destination=None):
        if failure == "offline":
            raise urllib.error.URLError("offline fixture")
        if failure == "checksum" and url.endswith(".sha256"):
            return b"0" * 64 + b"  " + release["archive"].encode()
        return get(url, maximum, destination)

    if failure == "digest":
        release["digest"] = "sha256:" + "f" * 64
    if failure == "length":
        release["zip_size"] += 1
    if failure == "commit":
        monkeypatch.setattr(
            desktop, "atomic_json", lambda *a: (_ for _ in ()).throw(OSError("disk fixture"))
        )

    def check(*a):
        if failure == "probe":
            raise desktop.DesktopError("probe fixture")

    with pytest.raises((desktop.DesktopError, urllib.error.URLError, OSError)):
        desktop.apply_update(installed, release, get=broken, check=check)
    assert (installed / "current.json").read_bytes() == before
    assert desktop.read_current(installed)[1].name == "v1.1.1"
    assert not list(installed.glob("download-*")) and not list(installed.glob("stage-*"))


@pytest.mark.parametrize(
    "failure", ["draft", "prerelease", "tag", "missing", "duplicate", "foreign_url", "oversize"]
)
def test_release_metadata_cannot_choose_arbitrary_code(tmp_path, failure):
    metadata, _ = release_fixture(tmp_path)
    if failure in {"draft", "prerelease"}:
        metadata[failure] = True
    elif failure == "tag":
        metadata["tag_name"] = "v1.2.0/../../escape"
    elif failure == "missing":
        metadata["assets"].pop()
    elif failure == "duplicate":
        metadata["assets"].append(metadata["assets"][0])
    elif failure == "foreign_url":
        metadata["assets"][0]["browser_download_url"] = "https://example.com/evil.exe"
    else:
        metadata["assets"][0]["size"] = desktop.MAX_ZIP + 1
    with pytest.raises(desktop.DesktopError):
        desktop.latest(get=lambda *a: json.dumps(metadata).encode())


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "v1.2.0/../escape",
        "v1.2.0/_internal/../../escape",
        "v1.2.0/C:/evil",
        "v1.2.0/_internal/CON",
        "v1.2.0/photo.cr3",
        "v1.0.0/release.json",
    ],
)
def test_archive_paths_rejected_before_file_creation(tmp_path, name):
    archive = tmp_path / "update.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("v1.2.0/release.json", "{}")
        zipped.writestr(name, "bad")
    directory = tmp_path / "stage"
    directory.mkdir()
    with pytest.raises((ValueError, desktop.DesktopError)):
        desktop.unpack(archive, directory, "v1.2.0")
    assert not list(directory.iterdir())


@pytest.mark.parametrize("kind", ["symlink", "duplicate", "oversized_directory"])
def test_special_archive_entries_rejected(tmp_path, kind, monkeypatch):
    archive = tmp_path / "update.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        entry = zipfile.ZipInfo("v1.2.0/_internal/link")
        if kind == "symlink":
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipped.writestr(entry, "bad")
        if kind == "duplicate":
            zipped.writestr("v1.2.0/_INTERNAL/LINK", "duplicate")
    directory = tmp_path / "stage"
    directory.mkdir()
    if kind == "oversized_directory":
        monkeypatch.setattr(
            desktop,
            "_guard_directory",
            lambda *a: (_ for _ in ()).throw(ValueError("directory fixture")),
        )
    with pytest.raises((ValueError, desktop.DesktopError)):
        desktop.unpack(archive, directory, "v1.2.0")
    assert not list(directory.iterdir())


def test_versions_compare_numerically_and_same_release_does_not_download(installed):
    assert desktop.version("v1.10.0") > desktop.version("v1.9.0")
    assert not desktop.apply_update(installed, {"tag": "v1.1.1"}, get=lambda *a: pytest.fail("network"))
    with pytest.raises(desktop.DesktopError):
        desktop.version("v01.1.0")


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/file",
        "https://github.com.evil.example/file",
        "https://user:pass@github.com/file",
        "https://github.com:444/file",
    ],
)
def test_redirects_require_github_https(url):
    with pytest.raises(desktop.DesktopError):
        desktop.GitHubRedirects().redirect_request(
            urllib.request.Request(desktop.API), None, 302, "", {}, url
        )


def test_no_public_release_is_actionable():
    def missing(*a):
        raise urllib.error.HTTPError(desktop.API, 404, "fixture", {}, None)

    with pytest.raises(desktop.DesktopError, match="No public release"):
        desktop.latest(get=missing)


@pytest.mark.parametrize("headless", [True, False])
@pytest.mark.skipif(os.name != "nt", reason="Windows launch flags")
def test_installed_launch_forwards_paths_and_preserves_normal_console(installed, monkeypatch, headless):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        sys, "argv", ["app.exe", "--launch-installed", "--workspace", "C:/path with spaces"]
    )
    monkeypatch.setattr(desktop, "install_root", lambda: installed)
    launches = []
    monkeypatch.setattr(
        desktop.subprocess, "Popen", lambda args, **kwargs: launches.append((args, kwargs))
    )
    desktop.command(
        SimpleNamespace(check_updates=False, launch_installed=True, update=False, no_browser=headless)
    )
    args, options = launches[0]
    assert args[1:] == ["--workspace", "C:/path with spaces"]
    assert options["creationflags"] == (desktop.subprocess.CREATE_NO_WINDOW if headless else 0)


@pytest.mark.skipif(os.name != "nt", reason="Windows installation lock")
def test_managed_root_lock_and_nonempty_guard(tmp_path):
    with desktop.managed(tmp_path / "install"):
        with pytest.raises(desktop.DesktopError, match="already running"):
            with desktop.managed(tmp_path / "install"):
                pass
    other = tmp_path / "originals"
    other.mkdir()
    (other / "photo.jpg").write_bytes(b"original")
    with pytest.raises(desktop.DesktopError, match="not empty"):
        with desktop.managed(other):
            pass
    assert (other / "photo.jpg").read_bytes() == b"original"


@pytest.mark.skipif(os.name != "nt", reason="Real Windows shell shortcut integration")
def test_real_windows_shortcut_creation_in_test_folder(installed, tmp_path):
    directory = tmp_path / "shortcuts"
    directory.mkdir()
    desktop.shortcuts(installed, directory=directory)
    assert {p.name for p in directory.iterdir()} == {
        "CapreConvert.lnk",
        "Update CapreConvert.lnk",
        "Restore previous CapreConvert.lnk",
    }
    assert all(p.stat().st_size > 0 for p in directory.iterdir())
