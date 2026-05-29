"""Shared helpers for locating an artifact inside a code-agent's install dir.

Both `add` (import a brand-new artifact into the workspace) and `push <scope>`
(re-publish an installation that was edited in place) need to find where an
artifact's files live under the env-base and enumerate them. This module owns
that env/scope-aware lookup so the two commands stay in sync.
"""
from __future__ import annotations

from pathlib import Path

from perskent import installed as installed_mod
from perskent.paths import dest_project_dir, dest_root_dir


def env_base_for(env: str, scope: str, kind: str) -> Path:
    """Dir under which the `<kind_folder>/<name>` artifact lives in the user's
    environment (mirror of install.py's `_dest_root_for`)."""
    if scope == installed_mod.ROOT:
        return dest_root_dir(env, kind)
    return dest_project_dir(env, kind)


def find_source(env_base: Path, kind_folder: str, art_name: str) -> Path | None:
    """Locate the artifact under the env-base. Returns a directory or a
    single-file path (`.md` convention), or None if neither exists."""
    dir_path = env_base / kind_folder / art_name
    if dir_path.is_dir():
        return dir_path
    file_path = env_base / kind_folder / f"{art_name}.md"
    if file_path.is_file():
        return file_path
    return None


def files_relative_to_env_base(source: Path, env_base: Path) -> list[Path]:
    """Files to copy, as paths relative to the env-base (matches the
    `installed_paths` format used by install/update/remove)."""
    if source.is_file():
        return [source.relative_to(env_base)]
    return sorted(
        f.relative_to(env_base) for f in source.rglob("*") if f.is_file()
    )
