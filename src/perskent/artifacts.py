"""Shared helpers for locating an artifact inside a code-agent's install dir.

Both `add` (import a brand-new artifact into the workspace) and `push <scope>`
(re-publish an installation that was edited in place) need to find where an
artifact's files live under the env-base and enumerate them. This module owns
that env/scope-aware lookup so the two commands stay in sync.
"""
from __future__ import annotations

from pathlib import Path

from perskent import converters
from perskent import installed as installed_mod
from perskent.paths import dest_project_dir, dest_root_dir


def env_base_for(env: str, scope: str, kind: str) -> Path:
    """Dir under which the `<kind_folder>/<name>` artifact lives in the user's
    environment (mirror of install.py's `_dest_root_for`)."""
    if scope == installed_mod.ROOT:
        return dest_root_dir(env, kind)
    return dest_project_dir(env, kind)


def find_source(env_base: Path, env: str, kind: str, art_name: str) -> Path | None:
    """Locate the artifact under the env-base, honoring the env's layout
    (single .toml file, single .md, or a directory). Returns the path or None."""
    layout = converters.dest_layout(env, kind, art_name)
    kind_folder = f"{kind}s"
    candidates = list(layout.glob_roots) + [
        f"{kind_folder}/{art_name}",
        f"{kind_folder}/{art_name}.md",
    ]
    for cand in candidates:
        p = env_base / cand
        if p.exists():
            return p
    return None


def files_relative_to_env_base(source: Path, env_base: Path) -> list[Path]:
    """Files to copy, as paths relative to the env-base (matches the
    `installed_paths` format used by install/update/remove)."""
    if source.is_file():
        return [source.relative_to(env_base)]
    return sorted(
        f.relative_to(env_base) for f in source.rglob("*") if f.is_file()
    )
