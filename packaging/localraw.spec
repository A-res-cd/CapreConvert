# Build on the target operating system. One folder; no cross compilation.
from pathlib import Path
import importlib.metadata
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from localraw.packaging import package_names, windows_version_info
release = package_names()
raw_data, raw_binaries, raw_hidden = collect_all("rawpy")
docx_data, docx_binaries, docx_hidden = collect_all("docx")
pdf_data, pdf_binaries, pdf_hidden = collect_all("pypdfium2_raw")
data = [(str(root / "localraw" / "static"), "localraw/static"),
        (str(root / "README.md"), "."), (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
data += raw_data
data += docx_data + pdf_data
pdf_distribution = importlib.metadata.distribution("pypdfium2")
for entry in pdf_distribution.files or []:
    if "licenses" in Path(str(entry)).parts:
        source = Path(pdf_distribution.locate_file(entry))
        if source.is_file():
            data.append((str(source), str(Path("notices/pypdfium2") / Path(str(entry)).parent)))
for name in ("fastapi", "uvicorn", "Pillow", "rawpy", "psutil", "pypdf", "python-docx", "lxml", "pypdfium2"):
    data += copy_metadata(name, recursive=True)

# Keep exact installed upstream licenses, including native dependency notices when provided.
for distribution in importlib.metadata.distributions():
    name = distribution.metadata["Name"]
    for item in distribution.files or []:
        path = Path(str(item))
        if ".." in path.parts:
            continue
        if any(word in path.name.lower() for word in ("license", "copying", "notice")):
            source = Path(distribution.locate_file(item))
            if source.is_file() and source.suffix not in {".py", ".pyc"}:
                data.append((str(source), str(Path("notices") / name / path.parent)))

analysis = Analysis([str(root / "packaging" / "entrypoint.py")], pathex=[str(root)],
    binaries=raw_binaries + docx_binaries + pdf_binaries, datas=data,
    hiddenimports=raw_hidden + docx_hidden + pdf_hidden + collect_submodules("pypdfium2") + collect_submodules("uvicorn") + collect_submodules("pypdf")
        + ["localraw.conversion", "localraw.worker", "localraw.documents", "lxml.etree", "localraw.raster", "localraw.previews", "PIL.WebPImagePlugin"],
    excludes=["tkinter", "pytest", "httpx", "playwright", "IPython", "rawpy.enhance"],
    noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name=release.executable_stem, console=True,
          icon=str(root / "packaging" / "assets" / "capreconvert.ico"),
          version=windows_version_info() if release.system == "windows" else None,
          debug=False, strip=False, upx=False)
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name=release.tag)
