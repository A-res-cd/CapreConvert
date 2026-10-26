"""Release names shared by PyInstaller, the release builder and smoke checks."""

import platform
import re
import struct
from dataclasses import dataclass

from . import APP_NAME, __version__


@dataclass(frozen=True)
class PackageNames:
    version: str
    system: str
    architecture: str

    @property
    def tag(self):
        return "v" + self.version

    @property
    def executable_stem(self):
        return APP_NAME + "-" + self.tag

    @property
    def executable(self):
        return self.executable_stem + (".exe" if self.system == "windows" else "")

    @property
    def archive(self):
        return f"{APP_NAME}-{self.tag}-{self.system}-{self.architecture}.zip"


def package_names():
    # Keep the tag safe as a single folder/filename component. Prereleases are supported.
    number = r"(?:0|[1-9][0-9]*)"
    if not re.fullmatch(rf"{number}\.{number}\.{number}(?:(?:a|b|rc){number})?", __version__):
        raise ValueError("Use a version such as 0.1.0 or 0.2.0rc1 in localraw/__init__.py, without v.")
    systems = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}
    system = systems.get(platform.system())
    machine = platform.machine().lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if not system or not architecture or struct.calcsize("P") != 8:
        raise ValueError("Packaging requires a supported 64-bit target OS and Python interpreter.")
    return PackageNames(__version__, system, architecture)


def windows_version_info():
    """Build-time PE resource; keep PyInstaller outside the runtime import graph."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    release = package_names()
    numeric = tuple(map(int, re.match(r"(\d+)\.(\d+)\.(\d+)", release.version).groups())) + (0,)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=numeric,
            prodvers=numeric,
            flags=2 if re.search(r"(?:a|b|rc)\d+$", release.version) else 0,
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904b0",
                        [
                            StringStruct("ProductName", APP_NAME),
                            StringStruct("FileDescription", APP_NAME),
                            StringStruct("InternalName", APP_NAME),
                            StringStruct("OriginalFilename", release.executable),
                            StringStruct("FileVersion", release.version),
                            StringStruct("ProductVersion", release.version),
                            StringStruct("Comments", "Private local document and RAW image conversion"),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
