import stat
import struct
import zipfile

import pytest

from localraw.archives import OutputNames, extract_selected, inspect_archive, package_outputs


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return path


def test_nested_mixed_and_selected_extraction(tmp_path, settings):
    path = make_zip(
        tmp_path / "photos.zip",
        [("folder/Nested/P.CR3", b"raw"), ("notes.txt", b"text"), ("inner.zip", b"zip")],
    )
    selected, skipped, expanded = inspect_archive(path, settings)
    assert len(selected) == 1 and skipped == ["notes.txt", "inner.zip"] and expanded == 10
    target = tmp_path / "generated.cr3"
    assert extract_selected(path, selected[0], target, settings) == 3
    assert target.read_bytes() == b"raw"
    assert not (tmp_path / "folder").exists()


@pytest.mark.parametrize(
    "name",
    [
        "../bad.cr3",
        "a/../../bad.cr3",
        "/bad.cr3",
        "C:/bad.cr3",
        "\\\\host\\bad.cr3",
        "a\\..\\bad.cr3",
        "a:stream.cr3",
        "CON.cr3",
        "foo/LPT1.txt",
        "folder./a.cr3",
        "folder /a.cr3",
        "a//bad.cr3",
        "a/./bad.cr3",
        "a/COM¹.cr3",
        "CON .cr3",
        "CONOUT$.txt",
    ],
)
def test_unsafe_paths_fail_entire_archive(tmp_path, settings, name):
    path = make_zip(tmp_path / "bad.zip", [("safe.CR3", b"r"), (name, b"x")])
    with pytest.raises(ValueError):
        inspect_archive(path, settings)


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK])
def test_links_and_special_files(tmp_path, settings, mode):
    entry = zipfile.ZipInfo("link.cr3")
    entry.create_system = 3
    entry.external_attr = (mode | 0o777) << 16
    path = make_zip(tmp_path / "bad.zip", [(entry, b"target")])
    with pytest.raises(ValueError, match="special"):
        inspect_archive(path, settings)


def test_encrypted_and_nul_entries(tmp_path, settings):
    path = make_zip(tmp_path / "bad.zip", [("abc.cr3", b"x")])
    content = bytearray(path.read_bytes())
    central = content.index(b"PK\x01\x02")
    content[central + 8] |= 1
    path.write_bytes(content)
    with pytest.raises(ValueError, match="Encrypted"):
        inspect_archive(path, settings)
    content[central + 8] &= 0xFE
    content[central + 46 + 1] = 0
    path.write_bytes(content)
    with pytest.raises(ValueError, match="Unsafe"):
        inspect_archive(path, settings)


def test_bomb_limits(tmp_path, settings):
    path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("huge.CR3", b"0" * 100000)
    with pytest.raises(ValueError, match="ratio"):
        inspect_archive(path, settings)


def test_crc_failure_cleans_staging(tmp_path, settings):
    path = make_zip(tmp_path / "bad.zip", [("a.CR3", b"raw bytes")])
    selected, _, _ = inspect_archive(path, settings)
    content = bytearray(path.read_bytes())
    name_len, extra_len = struct.unpack_from("<HH", content, 26)
    content[30 + name_len + extra_len] ^= 0xFF
    path.write_bytes(content)
    with pytest.raises(ValueError, match="CRC"):
        extract_selected(path, selected[0], tmp_path / "generated.cr3", settings)
    assert not list(tmp_path.glob("*.part"))
    assert not (tmp_path / "generated.cr3").exists()


def test_unicode_case_and_folder_collisions():
    names = OutputNames()
    assert names.archive_root("files.zip") == "files__2"
    assert names.archive_root("FILES.zip") == "FILES__3"
    assert names.jpeg("files/É.CR3") == "files/É.jpg"
    assert names.jpeg("FILES/e\u0301.cr3") == "FILES/é__2.jpg"
    assert names.jpeg("files/É.jpg/a.cr3") == "files/É.jpg__2/a.jpg"


def test_atomic_success_package(tmp_path):
    photo = tmp_path / "id.jpg"
    photo.write_bytes(b"committed image fixture")
    target = tmp_path / "results.zip"
    package_outputs(target, [{"path": photo, "output_name": "archive/folder/a.jpg"}])
    with zipfile.ZipFile(target) as result:
        assert result.namelist() == ["archive/folder/a.jpg"] and result.testzip() is None
    with pytest.raises(ValueError):
        package_outputs(tmp_path / "failed.zip", [{"path": photo, "output_name": "../bad.jpg"}])
    assert not (tmp_path / "failed.zip").exists() and not list(tmp_path.glob("*.part"))


def test_central_directory_count_lies_and_byte_limits(tmp_path, settings):
    path = make_zip(tmp_path / "bad.zip", [("a.cr3", b"x"), ("b.cr3", b"y")])
    original = path.read_bytes()
    content = bytearray(original)
    end = content.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", content, end + 8, 1, 1)
    path.write_bytes(content)
    with pytest.raises(ValueError, match="count"):
        inspect_archive(path, settings)
    path.write_bytes(original)
    settings.zip_directory_max_bytes = 16
    with pytest.raises(ValueError, match="directory"):
        inspect_archive(path, settings)


def test_lzma_dictionary_guard_and_normal_extraction(tmp_path, settings):
    path = tmp_path / "lzma.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_LZMA) as archive:
        archive.writestr("safe.cr3", b"a small raw fixture")
    selected, _, _ = inspect_archive(path, settings)
    target = tmp_path / "generated.cr3"
    extract_selected(path, selected[0], target, settings)
    assert target.read_bytes() == b"a small raw fixture"
    content = bytearray(path.read_bytes())
    name_size, extra_size = struct.unpack_from("<HH", content, 26)
    struct.pack_into("<I", content, 30 + name_size + extra_size + 5, 2**30)
    path.write_bytes(content)
    with pytest.raises(ValueError, match="dictionary"):
        inspect_archive(path, settings)
