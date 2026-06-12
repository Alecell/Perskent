"""Filesystem helpers shared across commands.

The one rule here: copying a file must never fail because of *metadata*.
`shutil.copy2` (and `copystat`) try to replicate mode, mtime, flags and
xattrs via `os.utime` / `os.chmod` / `os.setxattr`. Several real-world
filesystems reject those calls even when the byte copy itself is fine:

- WSL2 DrvFs / 9p mounts (`/mnt/c`, `/mnt/n`, ...) — `os.utime` → EPERM
- SMB / NFS / FAT / exFAT — utime ns or xattrs → ENOTSUP / EINVAL / EACCES

So we split the copy into a mandatory part (content) and a best-effort part
(metadata). Content must succeed; metadata is attempted and any `OSError`
is swallowed. This mirrors `copy2` on capable filesystems and degrades
cleanly everywhere else.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def safe_copy(src: Path, target: Path) -> None:
    """Copy `src` to `target`: content mandatory, metadata best-effort.

    Raises the underlying `OSError` only if the *content* copy fails
    (missing source, unwritable dir, no space). A metadata-only failure
    (utime/chmod/xattr rejected by the destination filesystem) is ignored.
    """
    shutil.copyfile(src, target)
    try:
        shutil.copystat(src, target)
    except OSError:
        # Destination FS refuses metadata (WSL mount, network share, FAT).
        # The bytes are already there — that's all install needs.
        pass
