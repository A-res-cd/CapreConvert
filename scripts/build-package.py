"""Build, smoke-check and ZIP a versioned native distribution. No cross compilation."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def reuse_compiled(source, bundle, release):
    """Refresh assets only when every frozen application module equals current source."""
    import importlib.metadata

    from PyInstaller.archive.readers import CArchiveReader

    source = source.resolve()
    manifest = json.loads((source / "release.json").read_text("utf-8"))
    for field, expected in (
        ("version", release.version),
        ("platform", release.system),
        ("architecture", release.architecture),
        ("executable", release.executable),
    ):
        if manifest.get(field) != expected:
            raise RuntimeError("Reusable bundle identity differs; perform a fresh build.")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise RuntimeError("Reusable bundles must not contain filesystem links.")
    archive = CArchiveReader(str(source / release.executable)).open_embedded_archive("PYZ.pyz")
    verified = 0
    for path in (ROOT / "localraw").glob("*.py"):
        if path.stem == "packaging":  # Build-only module, intentionally absent from runtime.
            continue
        name = "localraw" if path.stem == "__init__" else "localraw." + path.stem
        frozen = archive.extract(name)
        current = compile(path.read_bytes(), frozen.co_filename, "exec", dont_inherit=True, optimize=0)
        if current != frozen:
            raise RuntimeError(f"Frozen {name} differs from current source; perform a fresh build.")
        verified += 1
    for path in (source / "_internal").glob("*.dist-info"):
        distribution = importlib.metadata.Distribution.at(path)
        if importlib.metadata.version(distribution.metadata["Name"]) != distribution.version:
            raise RuntimeError("Bundled dependency version differs from the environment; rebuild.")
    shutil.copytree(source, bundle)
    shutil.copytree(ROOT / "localraw/static", bundle / "_internal/localraw/static", dirs_exist_ok=True)
    for name in ("README.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, bundle / "_internal" / name)
    return verified


def main():
    sys.path.insert(0, str(ROOT))
    from localraw import APP_NAME
    from localraw.packaging import package_names

    parser = argparse.ArgumentParser(
        description=f"Build a versioned {APP_NAME} folder, ZIP and SHA-256 file"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--libreoffice", type=Path, help="Explicit external engine for smoke validation only"
    )
    parser.add_argument(
        "--reuse-compiled",
        type=Path,
        help="Asset-only rebuild: require identical frozen Python code and dependency versions",
    )
    parser.add_argument(
        "--smoke-memory-profile",
        choices=("default", "compact"),
        default="default",
        help="Use stricter worker caps for tiny smoke fixtures without changing packaged defaults or safety reserves",
    )
    arguments = parser.parse_args()
    release = package_names()
    output = arguments.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / release.tag
    archive = output / release.archive
    checksum = output / (release.archive + ".sha256")
    for target in (destination, archive, checksum):
        if target.exists():
            parser.error(
                f"Release already exists: {target.name}. Bump localraw/__init__.py or choose another --output-dir."
            )
    lock = output / (".build-" + release.tag + ".lock")
    try:
        handle = lock.open("x", encoding="ascii")
    except FileExistsError:
        parser.error(
            f"A build for {release.tag} is already in progress (or its build lock needs manual review)."
        )
    stage = None
    try:
        handle.write(f"{APP_NAME} release build\n")
        handle.flush()
        stage = Path(tempfile.mkdtemp(prefix=".localraw-package-", dir=output)).resolve()
        if stage.parent != output:
            raise RuntimeError("Refusing a staging directory outside the release output directory.")
        work = ROOT / "build" / "releases" / release.tag / f"{release.system}-{release.architecture}"
        bundle = stage / "dist" / release.tag
        verified_modules = None
        if arguments.reuse_compiled:
            verified_modules = reuse_compiled(arguments.reuse_compiled, bundle, release)
        else:
            run(
                [
                    sys.executable,
                    "-m",
                    "PyInstaller",
                    str(ROOT / "packaging" / "localraw.spec"),
                    "--noconfirm",
                    "--distpath",
                    str(stage / "dist"),
                    "--workpath",
                    str(work),
                ]
            )
        if (
            bundle.resolve().parent != (stage / "dist").resolve()
            or not (bundle / release.executable).is_file()
        ):
            raise RuntimeError("PyInstaller did not produce the expected versioned executable.")
        metadata = {
            "application": APP_NAME,
            "version": release.version,
            "tag": release.tag,
            "platform": release.system,
            "architecture": release.architecture,
            "executable": release.executable,
            "archive": release.archive,
            "built_at": datetime.now(UTC).isoformat(),
            "build_mode": "verified-code-reuse" if arguments.reuse_compiled else "fresh",
            "verified_source_modules": verified_modules,
            "smoke_memory_profile": arguments.smoke_memory_profile,
        }
        (bundle / "release.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        (bundle / "START_HERE.txt").write_text(
            f"{APP_NAME} {release.tag} ({release.system}, {release.architecture})\n\n"
            f"Run {release.executable}. Keep the _internal folder beside it.\n"
            "No Python installation is needed to launch this bundled app.\n"
            f"Phone browsers: run {release.executable} --lan and use the console pairing code.\n"
            "Finish current jobs and close an older LocalRAW or CapreConvert instance before launching this copy.\n"
            "Your existing workspace, saved sessions and originals are separate from this application folder.\n"
            "PDF to DOCX uses bundled pypdf/python-docx/lxml and extracts text, without OCR or layout reconstruction.\n"
            "DOCX to PDF needs a separate local LibreOffice installation; LibreOffice is detected, not bundled.\n"
            "JPEG/PNG/WebP conversion and optimization use bundled local Pillow codecs.\n"
            "Output previews use local PDFium page rendering and read-only DOCX content.\n"
            "One selected output downloads directly; multiple selections download as a ZIP.\n"
            "Both document routes remain local; no document is uploaded to an Internet service.\n"
            "Setup, limits and notices: _internal/README.md and _internal/THIRD_PARTY_NOTICES.md.\n"
            "See validation documentation for executed camera/document checks; smoke alone is not clean-machine validation.\n",
            encoding="utf-8",
        )
        smoke = [sys.executable, str(ROOT / "scripts" / "smoke-package.py"), "--dist-dir", str(bundle)]
        if arguments.libreoffice:
            smoke += ["--libreoffice", str(arguments.libreoffice.expanduser().resolve())]
        smoke += ["--memory-profile", arguments.smoke_memory_profile]
        # PyInstaller can leave the host temporarily compressed/paging after its
        # compiler exits. Wait for default test admission; never weaken app limits.
        required_headroom = (
            768
            + (384 if arguments.smoke_memory_profile == "compact" else 768)
            + (96 if arguments.smoke_memory_profile == "compact" else 128)
        ) * 1024**2
        deadline = time.monotonic() + 60
        while psutil.virtual_memory().available < required_headroom:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Build completed, but strict smoke needs more available RAM. No release published; retry when headroom recovers."
                )
            time.sleep(0.5)
        run(smoke)
        staged_zip = stage / release.archive
        with zipfile.ZipFile(
            staged_zip, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True
        ) as zipped:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    if not path.resolve().is_relative_to(bundle.resolve()):
                        raise RuntimeError("Refusing an archive entry outside its application folder.")
                    zipped.write(path, path.relative_to(bundle.parent).as_posix())
        with zipfile.ZipFile(staged_zip) as zipped:
            if (
                zipped.testzip() is not None
                or f"{release.tag}/{release.executable}" not in zipped.namelist()
            ):
                raise RuntimeError("Packaged ZIP failed its integrity or executable check.")
        with staged_zip.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        staged_checksum = stage / checksum.name
        staged_checksum.write_text(f"{digest}  {release.archive}\n", encoding="ascii")
        # All final paths are generated, checked children of the explicit output directory.
        for target in (destination, archive, checksum):
            if target.resolve().parent != output or target.exists():
                raise RuntimeError("Release target changed during the build; refusing to overwrite it.")
        bundle.rename(destination)
        staged_zip.rename(archive)
        staged_checksum.rename(checksum)
        print(
            json.dumps(
                {
                    "version": release.tag,
                    "folder": str(destination),
                    "archive": str(archive),
                    "checksum": str(checksum),
                    "sha256": digest,
                    "smoke": "passed",
                    "zip_integrity": "passed",
                },
                indent=2,
            )
        )
    finally:
        handle.close()
        lock.unlink(missing_ok=True)
        if stage is not None and stage.exists():
            checked = stage.resolve()
            if checked.parent != output or not checked.name.startswith(".localraw-package-"):
                raise RuntimeError("Refusing to remove an unverified build staging directory.")
            shutil.rmtree(checked)


if __name__ == "__main__":
    main()
