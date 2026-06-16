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

from dataclasses import dataclass
from pathlib import Path

from perskent import converters
from perskent.registry_scan import Package


class InstallError(RuntimeError):
    pass


@dataclass
class Conflict:
    relative: Path
    absolute: Path

    def __str__(self) -> str:
        return str(self.absolute)


def plan_install(pkg: Package, env: str) -> converters.ConvertResult:
    """Project a registry package (canonical Claude-markdown layout) into the
    file-set `env` should physically hold, applying any format conversion."""
    canonical = {str(rel): (pkg.path / rel).read_bytes() for rel in pkg.files_to_install()}
    art = converters.build_artifact(pkg.kind, pkg.name, canonical)
    return converters.from_canonical(env, art)


def detect_conflicts(
    pkg: Package,
    dest_root: Path,
    *,
    env: str,
    skip: set[Path] | None = None,
) -> list[Conflict]:
    """List conflicts before installing, on the env's target file-set.

    Conflict = destination FILE already exists. `skip` (relative target paths)
    do not count (e.g. `--force` reinstall of paths the package already owns).
    """
    skip_set = skip or set()
    conflicts: list[Conflict] = []
    for relative in plan_install(pkg, env).files:
        rel = Path(relative)
        if rel in skip_set:
            continue
        target = dest_root / rel
        if target.exists() and target.is_file():
            conflicts.append(Conflict(relative=rel, absolute=target))
    return conflicts


def copy_files(
    pkg: Package,
    dest_root: Path,
    *,
    env: str,
    skip: set[Path] | None = None,
    overwrite: bool = False,
) -> tuple[list[Path], list[str]]:
    """Write the env's converted file-set to `dest_root`.

    Returns (relative paths written, conversion warnings).
    `skip`: target paths to NOT write (preserve on update).
    `overwrite`: if True, overwrite existing files; if False, fail on existing.
    """
    skip_set = skip or set()
    result = plan_install(pkg, env)
    installed: list[Path] = []
    for relative, data in result.files.items():
        rel = Path(relative)
        if rel in skip_set:
            continue
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise InstallError(f"existing path blocking copy: {target}")
        target.write_bytes(data)
        installed.append(rel)
    return installed, result.warnings


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
