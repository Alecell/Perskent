"""safe_copy: content is mandatory, metadata is best-effort.

Regression for the WSL/DrvFs (and SMB/NFS/FAT) case where os.utime/chmod/
setxattr reject metadata with EPERM/ENOTSUP and shutil.copy2 aborted the
install with only the first file half-written.
"""
from __future__ import annotations

import shutil

import pytest

from perskent import fsutil


def test_safe_copy_copies_content(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("hello", encoding="utf-8")
    dst = tmp_path / "out" / "dst.md"
    dst.parent.mkdir()

    fsutil.safe_copy(src, dst)

    assert dst.read_text(encoding="utf-8") == "hello"


def test_safe_copy_survives_metadata_failure(tmp_path, monkeypatch):
    """copystat raising EPERM (as on a Windows mount) must not abort the copy."""
    src = tmp_path / "src.md"
    src.write_text("payload", encoding="utf-8")
    dst = tmp_path / "dst.md"

    def boom(*_a, **_k):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(shutil, "copystat", boom)

    fsutil.safe_copy(src, dst)  # must not raise

    assert dst.read_text(encoding="utf-8") == "payload"


def test_safe_copy_propagates_content_failure(tmp_path):
    """A genuine content failure (missing source) still raises."""
    missing = tmp_path / "nope.md"
    dst = tmp_path / "dst.md"

    with pytest.raises(OSError):
        fsutil.safe_copy(missing, dst)
