from __future__ import annotations

import h5py
import pytest

import moberg_h5
from conftest import write_root_attrs, write_v1_archive


def _write(path, version):
    with h5py.File(path, "w") as file:
        write_root_attrs(file, version=version)
        write_v1_archive(file)
    return path


@pytest.mark.parametrize("version", ["1.0", "1.7", b"1.0"])
def test_accepts_any_minor_of_major_1(tmp_path, version):
    path = _write(tmp_path / "ok.h5", version)
    with moberg_h5.open(path) as rec:
        assert rec.format_version == (version.decode() if isinstance(version, bytes) else version)
        assert rec.signals()


@pytest.mark.parametrize("version", ["2.0", "0.9", "10.1"])
def test_rejects_unknown_major(tmp_path, version):
    path = _write(tmp_path / "new.h5", version)
    with pytest.raises(moberg_h5.UnsupportedFormatVersion, match=f"uses HDF5 format {version}") as raised:
        moberg_h5.open(path)
    assert raised.value.version == version
    assert "Install a newer moberg-h5" in str(raised.value)


@pytest.mark.parametrize("version", ["1", "v1.0", "1.0.0", ""])
def test_rejects_malformed_version(tmp_path, version):
    path = _write(tmp_path / "bad.h5", version)
    with pytest.raises(moberg_h5.UnsupportedFormatVersion, match="MAJOR.MINOR"):
        moberg_h5.open(path)


def test_rejected_file_is_closed(tmp_path):
    path = _write(tmp_path / "new.h5", "2.0")
    with pytest.raises(moberg_h5.UnsupportedFormatVersion):
        moberg_h5.open(path)
    with h5py.File(path, "a") as file:
        file.attrs["format_version"] = "1.0"
