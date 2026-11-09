"""Explicit Windows host installation/update actions; never imported by HTTP routes."""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from .archives import _guard_directory, canonical, safe_relative
from .storage import atomic_json, file_hash

REPOSITORY = "A-res-cd/CapreConvert"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_ZIP = 512 * 1024**2
MAX_EXPANDED = 1024**3
MARKER = "CapreConvert per-user installation 1\n"


class DesktopError(Exception):
    pass


def version(tag):
    if not isinstance(tag, str) or not re.fullmatch(
        r"v(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})", tag
    ):
        raise DesktopError("Only stable vX.Y.Z releases are supported.")
    return tuple(map(int, tag[1:].split(".")))


def no_links(path):
    path = Path(path).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise DesktopError("Installation paths must not contain links or junctions.")


def install_root():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise DesktopError("Windows LOCALAPPDATA is unavailable.")
    return Path(base) / "CapreConvert"


@contextmanager
def temporary_directory(root, prefix):
    root = Path(root).resolve()
    no_links(root)
    directory = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
    try:
        if directory.resolve().parent != root or not directory.name.startswith(prefix):
            raise DesktopError("Invalid updater staging directory.")
        yield directory
    finally:
        no_links(directory)
        if directory.resolve().parent != root or not directory.name.startswith(prefix):
            raise DesktopError("Refusing to remove an unverified updater directory.")
        shutil.rmtree(directory)


@contextmanager
def managed(root):
    """Serialize mutations only inside an explicitly marked dedicated installation."""
    root = Path(root).absolute()
    no_links(root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".capreconvert-install"
    if not marker.exists():
        if any(root.iterdir()):
            raise DesktopError("Installation folder is not empty and has no CapreConvert marker.")
        marker.write_text(MARKER, encoding="ascii")
    no_links(marker)
    if marker.read_text("ascii") != MARKER:
        raise DesktopError("Installation marker is invalid.")
    no_links(root / "manager.lock")
    with (root / "manager.lock").open("a+b") as handle:
        import msvcrt

        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise DesktopError("Another installation or update is already running.") from exc
        try:
            for name in ("versions", "current.json", "current.json.part"):
                no_links(root / name)
            (root / "versions").mkdir(exist_ok=True)
            yield root
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def read_current(root, *, validate=True):
    root = Path(root).absolute()
    no_links(root / "current.json")
    no_links(root / ".capreconvert-install")
    if (root / ".capreconvert-install").read_text("ascii") != MARKER:
        raise DesktopError("No managed CapreConvert installation found.")
    path = root / "current.json"
    if path.stat().st_size > 4096:
        raise DesktopError("Installed version record is invalid.")
    record = json.loads(path.read_text("utf-8"))
    if not isinstance(record, dict) or record.get("schema") != 1:
        raise DesktopError("Installed version record is unsupported.")
    version(record.get("current"))
    bundle = root / "versions" / record["current"]
    no_links(bundle)
    if validate:
        validate_bundle(bundle, record["current"])
    return record, bundle


def validate_bundle(bundle, tag):
    version(tag)
    executable = f"CapreConvert-{tag}.exe"
    for relative in ("release.json", executable, "_internal/python312.dll"):
        no_links(bundle / relative)
        if not (bundle / relative).is_file():
            raise DesktopError("Application bundle is incomplete.")
    if (bundle / "release.json").stat().st_size > 16384:
        raise DesktopError("Release manifest exceeds its byte limit.")
    metadata = json.loads((bundle / "release.json").read_text("utf-8"))
    expected = {
        "application": "CapreConvert",
        "version": tag[1:],
        "tag": tag,
        "platform": "windows",
        "architecture": "x64",
        "executable": executable,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise DesktopError("Release manifest does not match this Windows x64 package.")
    return bundle / executable


def bundle_files(bundle, tag):
    allowed = {
        "_internal",
        "release.json",
        "START_HERE.txt",
        "Install CapreConvert.cmd",
        "Update CapreConvert.cmd",
        f"CapreConvert-{tag}.exe",
    }
    files = []
    for path in bundle.rglob("*"):
        no_links(path)
        relative = path.relative_to(bundle)
        if relative.parts[0] not in allowed or ".localraw-workspace" in relative.parts:
            raise DesktopError(
                "Application folder contains unexpected files. Extract a clean release ZIP."
            )
        if path.is_file():
            files.append((path, relative))
    return files


def probe(executable, tag):
    result = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode or result.stdout.strip() != "CapreConvert " + tag[1:]:
        raise DesktopError("The new application could not pass its launch check. Current version kept.")


def activate(root, source, tag, *, check=probe):
    """Copy to a new version folder, verify, then atomically select it. Never replace running code."""
    validate_bundle(source, tag)
    files = bundle_files(source, tag)
    destination = root / "versions" / tag
    no_links(destination)
    old_record = read_current(root)[0] if (root / "current.json").exists() else {}
    previous = old_record.get("current")
    if previous and version(tag) < version(previous):
        raise DesktopError("An older release will not replace the current installation.")
    if destination.exists():
        retained = {str(relative): path for path, relative in bundle_files(destination, tag)}
        if set(retained) != {str(relative) for _, relative in files} or any(
            file_hash(path) != file_hash(retained[str(relative)]) for path, relative in files
        ):
            raise DesktopError("This version is already installed with different contents.")
    else:
        with temporary_directory(root, "stage-") as staging:
            candidate = Path(staging) / tag
            candidate.mkdir()
            for path, relative in files:
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            check(validate_bundle(candidate, tag), tag)
            if (
                candidate.resolve().parent != staging
                or destination.resolve().parent != (root / "versions").resolve()
            ):
                raise DesktopError("Invalid installed version destination.")
            candidate.rename(destination)
    check(validate_bundle(destination, tag), tag)
    record = {
        "schema": 1,
        "current": tag,
        "previous": previous if previous != tag else None,
        "bootstrap": old_record.get("bootstrap", previous or tag),
    }
    if previous == tag:
        record = read_current(root)[0]
    atomic_json(root / "current.json", record)
    return destination


def rollback(root, *, check=probe):
    record, _ = read_current(root, validate=False)
    previous = record.get("previous")
    if not previous:
        raise DesktopError("No previous installed version is available.")
    executable = validate_bundle(root / "versions" / previous, previous)
    check(executable, previous)
    atomic_json(root / "current.json", {**record, "current": previous, "previous": record["current"]})


class GitHubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or parts.hostname
            not in {
                "github.com",
                "release-assets.githubusercontent.com",
                "objects.githubusercontent.com",
            }
        ):
            raise DesktopError("Update download redirected outside GitHub HTTPS.")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(url, maximum, destination=None, *, opener=None):
    """Bound metadata and downloads without credentials or unchecked redirects."""
    opener = opener or urllib.request.build_opener(GitHubRedirects())
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CapreConvert-Updater",
            "Accept": "application/vnd.github+json" if url == API else "application/octet-stream",
        },
    )
    with opener.open(request, timeout=30) as response:
        length = response.headers.get("Content-Length")
        if length and (not length.isdigit() or int(length) > maximum):
            raise DesktopError("Update download exceeds its size limit.")
        data, count = bytearray(), 0
        deadline = time.monotonic() + 300
        stream = destination.open("xb") if destination else None
        try:
            while chunk := response.read(64 * 1024):
                if time.monotonic() > deadline:
                    raise DesktopError("Update download timed out.")
                count += len(chunk)
                if count > maximum:
                    raise DesktopError("Update download exceeds its size limit.")
                if stream:
                    stream.write(chunk)
                else:
                    data.extend(chunk)
            if length and count != int(length):
                raise DesktopError("Update download was interrupted.")
        finally:
            if stream:
                stream.close()
        return bytes(data)


def latest(*, get=fetch):
    try:
        release = json.loads(get(API, 1024**2))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise DesktopError("No public release is available yet. Current version kept.") from exc
        raise
    tag = release.get("tag_name")
    version(tag)
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise DesktopError("The latest release is not a published stable release.")
    name = f"CapreConvert-{tag}-windows-x64.zip"
    assets = release.get("assets", [])
    result = {"tag": tag, "archive": name}
    for key, filename, maximum in (("zip", name, MAX_ZIP), ("checksum", name + ".sha256", 512)):
        matches = [asset for asset in assets if asset.get("name") == filename]
        expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}"
        if (
            len(matches) != 1
            or matches[0].get("browser_download_url") != expected
            or matches[0].get("state") != "uploaded"
            or type(matches[0].get("size")) is not int
            or not 0 < matches[0]["size"] <= maximum
        ):
            raise DesktopError("The latest release is missing its complete Windows ZIP or checksum.")
        result[key] = expected
        result[key + "_size"] = matches[0]["size"]
        if key == "zip":
            result["digest"] = matches[0].get("digest")
    return result


def unpack(archive_path, directory, tag):
    """Validate every application path before creating any archive-selected file."""
    allowed = {
        "_internal",
        "release.json",
        "START_HERE.txt",
        "Install CapreConvert.cmd",
        "Update CapreConvert.cmd",
        f"CapreConvert-{tag}.exe",
    }
    _guard_directory(
        archive_path, SimpleNamespace(zip_max_entries=10000, zip_directory_max_bytes=8 * 1024**2)
    )
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 10000:
            raise DesktopError("Update archive has too many entries.")
        names, members, expanded = set(), [], 0
        for entry in entries:
            relative = safe_relative(entry.orig_filename)
            parts = relative.split("/")
            normalized = canonical(relative)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if (
                parts[0] != tag
                or len(parts) < 2
                or parts[1] not in allowed
                or normalized in names
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                or entry.flag_bits & 1
                or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                or entry.file_size > 128 * 1024**2
            ):
                raise DesktopError("Update archive contains an unsafe or unexpected entry.")
            names.add(normalized)
            expanded += entry.file_size
            if expanded > MAX_EXPANDED:
                raise DesktopError("Expanded update exceeds its size limit.")
            members.append((entry, Path(*parts)))
        if shutil.disk_usage(directory).free < 2 * expanded + 256 * 1024**2:
            raise DesktopError("Not enough free disk space for the update.")
        for entry, relative in members:
            target = directory / relative
            if not target.resolve().is_relative_to(directory.resolve()):
                raise DesktopError("Unsafe update destination.")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            count = 0
            with archive.open(entry) as source, target.open("xb") as output:
                while chunk := source.read(64 * 1024):
                    count += len(chunk)
                    if count > entry.file_size:
                        raise DesktopError("Update member exceeds its declared size.")
                    output.write(chunk)
            if count != entry.file_size:
                raise DesktopError("Update member is incomplete.")
    bundle = directory / tag
    validate_bundle(bundle, tag)
    return bundle


def apply_update(root, release, *, get=fetch, check=probe):
    current, _ = read_current(root)
    if version(release["tag"]) <= version(current["current"]):
        return False
    with temporary_directory(root, "download-") as temporary:
        directory = Path(temporary)
        checksum = get(release["checksum"], 512).decode("ascii").strip()
        match = re.fullmatch(r"([a-fA-F0-9]{64})  " + re.escape(release["archive"]), checksum)
        if not match:
            raise DesktopError("Release checksum has an invalid filename or format.")
        digest = match[1].lower()
        if release.get("digest") and release["digest"] != "sha256:" + digest:
            raise DesktopError("GitHub and release checksums do not agree.")
        archive = directory / "update.zip"
        get(release["zip"], MAX_ZIP, archive)
        if archive.stat().st_size != release["zip_size"] or file_hash(archive) != digest:
            raise DesktopError("Downloaded update failed its checksum. Current version kept.")
        candidate = unpack(archive, directory, release["tag"])
        activate(root, candidate, release["tag"], check=check)
    return True


def shortcuts(root, *, desktop=True, directory=None):
    """Use Windows known folders and COM; script text is constant, paths travel via env."""
    record, bundle = read_current(root)
    executable = validate_bundle(bundle, bundle.name)
    bootstrap = record.get("bootstrap", record["current"])
    recovery = validate_bundle(root / "versions" / bootstrap, bootstrap)
    script = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath('Programs'))
if ($env:CAPRE_DESKTOP -eq '1') { $places += [Environment]::GetFolderPath('DesktopDirectory') }
if ($env:CAPRE_SHORTCUT_DIR) { $places = @($env:CAPRE_SHORTCUT_DIR) }
foreach ($place in $places) {
  foreach ($item in @(@('CapreConvert','--launch-installed'), @('Update CapreConvert','--launch-installed --update'), @('Restore previous CapreConvert','--launch-installed --rollback-update'))) {
    $path = Join-Path $place ($item[0] + '.lnk')
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $env:CAPRE_EXE
    $link.Arguments = $item[1]
    if ($item[0] -eq 'Restore previous CapreConvert') { $link.TargetPath = $env:CAPRE_RECOVERY_EXE; $link.Arguments = '--rollback-update' }
    $link.WorkingDirectory = Split-Path $env:CAPRE_EXE
    $link.IconLocation = $env:CAPRE_EXE + ',0'
    $link.WindowStyle = 7
    $link.Save()
  }
}
"""
    environment = dict(
        os.environ,
        CAPRE_EXE=str(executable),
        CAPRE_RECOVERY_EXE=str(recovery),
        CAPRE_DESKTOP="1" if desktop else "0",
        CAPRE_SHORTCUT_DIR=str(directory) if directory else "",
    )
    powershell = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        env=environment,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def message(text, *, question=False):
    import ctypes

    return (
        ctypes.windll.user32.MessageBoxW(None, text, "CapreConvert", 0x40 | (0x04 if question else 0))
        == 6
    )


def command(arguments):
    """Host-only actions. Normal launch never checks the network or requires installation."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        raise DesktopError("Desktop installation and updates require the packaged Windows app.")
    if arguments.check_updates:
        from . import __version__

        release = latest()
        print(
            json.dumps(
                {
                    "installed_version": __version__,
                    "latest_version": release["tag"][1:],
                    "update_available": version(release["tag"]) > version("v" + __version__),
                    "repository": REPOSITORY,
                }
            ),
            flush=True,
        )
        return
    root = install_root()
    if arguments.launch_installed:
        _, bundle = read_current(root)
        forwarded = [arg for arg in sys.argv[1:] if arg != "--launch-installed"]
        subprocess.Popen(
            [str(validate_bundle(bundle, bundle.name)), *forwarded],
            cwd=bundle,
            # A normal launch inherits the shortcut's minimized console so users
            # can close the host. Headless checks and updater dialogs stay hidden.
            creationflags=subprocess.CREATE_NO_WINDOW if arguments.update or arguments.no_browser else 0,
        )
        return
    with managed(root):
        if arguments.install:
            from . import __version__

            activate(root, Path(sys.executable).parent, "v" + __version__)
            shortcuts(root)
            message(
                "Installed. Use the CapreConvert desktop shortcut to launch.\nUse Update CapreConvert for future releases."
            )
        elif arguments.rollback_update:
            rollback(root)
            shortcuts(root)
            message(
                "Previous application version restored. Close any running instance before launching it.\nWorkspace and original files were unchanged."
            )
        else:
            record, _ = read_current(root)
            release = latest()
            if version(release["tag"]) <= version(record["current"]):
                message("CapreConvert is up to date (" + record["current"] + ").")
            elif message(
                f"CapreConvert {release['tag']} is available.\nDownload and install it from GitHub now?\n\nClose the app before launching the new version. Your files stay unchanged.",
                question=True,
            ):
                apply_update(root, release)
                shortcuts(root)
                message(
                    "Update installed. Close any running CapreConvert window, then use your desktop shortcut.\nYour previous version remains available through Restore previous CapreConvert."
                )
