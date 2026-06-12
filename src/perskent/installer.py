"""Filesystem operations for install/remove/update.

Design (decided in Phase 3):
- **Conflict = destination file that already exists.** Container folders
  existing is OK.
- **Atomic copy:** conflicts are detected before any copying happens; if
  any conflict, abort before touching anything.
- **Cleanup after remove:** after removing files, walk parent directories
  upward and remove any that became empty, up to `dest_root` (exclusive).
- **Preserve on update:** files whose path matches `manifest.preserve`
  and already exist in the destination are left alone.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from perskent import fsutil
from perskent.registry_scan import Package


class InstallError(RuntimeError):
    pass


@dataclass
class Conflict:
    relative: Path
    absolute: Path

    def __str__(self) -> str:
        return str(self.absolute)


def detect_conflicts(
    pkg: Package,
    dest_root: Path,
    *,
    skip: set[Path] | None = None,
) -> list[Conflict]:
    """List conflicts before installing.

    Conflict = destination FILE from the package already exists (any content).
    Container folders existing is not a conflict.

    `skip` (relative paths): paths that do NOT count as conflicts even if
    they already exist (e.g. `--force` reinstall replacing paths previously
    owned by the same package).
    """
    skip_set = skip or set()
    conflicts: list[Conflict] = []
    for relative in pkg.files_to_install():
        if relative in skip_set:
            continue
        target = dest_root / relative
        if target.exists() and target.is_file():
            conflicts.append(Conflict(relative=relative, absolute=target))
    return conflicts


def copy_files(
    pkg: Package,
    dest_root: Path,
    *,
    skip: set[Path] | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Copy package files to `dest_root`. Returns relative paths that were copied.

    `skip`: paths to NOT copy (preserve on update).
    `overwrite`: if True, overwrite existing files; if False, fail on existing.
    """
    skip_set = skip or set()
    installed: list[Path] = []
    for relative in pkg.files_to_install():
        if relative in skip_set:
            continue
        src = pkg.path / relative
        target = dest_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise InstallError(f"existing path blocking copy: {target}")
        fsutil.safe_copy(src, target)
        installed.append(relative)
    return installed


def remove_paths(
    relative_paths: list[str | Path],
    dest_root: Path,
) -> None:
    """Remove the listed files (paths relative to dest_root) and clean up
    empty parent directories upstream, up to `dest_root` (exclusive).

    Idempotent: missing paths are ignored.
    """
    parents: set[Path] = set()
    for rel in relative_paths:
        target = dest_root / rel
        if target.is_file() or target.is_symlink():
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        parents.add(target.parent)

    while parents:
        next_round: set[Path] = set()
        for parent in parents:
            if parent == dest_root:
                continue
            try:
                parent.relative_to(dest_root)
            except ValueError:
                continue  # parent outside dest_root, ignore
            if not parent.exists():
                continue
            try:
                next(parent.iterdir())
            except StopIteration:
                try:
                    parent.rmdir()
                    next_round.add(parent.parent)
                except OSError:
                    pass
        parents = next_round
