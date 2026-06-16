"""Backward-compatible per-file shim over the converter layer.

Historically `compat` injected/stripped skill frontmatter directly. That logic
now lives in `converters/` (artifact-level, all kinds). These two functions are
kept as thin per-file shims so older call sites (and `test_compat.py`) keep
working: they operate only on `SKILL.md` and delegate to the skill converter.
"""
from __future__ import annotations

from pathlib import Path

from perskent import converters
from perskent.converters.base import AUTO_MARKER  # re-exported

__all__ = ["AUTO_MARKER", "project", "canonical"]


def _skill_artifact(rel: str, data: bytes) -> converters.Artifact:
    return converters.build_artifact("skill", Path(rel).parent.name, {rel: data})


def project(env: str, rel: str, data: bytes) -> bytes:
    """What `env` should hold for `rel` (skills gain frontmatter on the way in)."""
    if Path(rel).name != "SKILL.md":
        return data
    art = _skill_artifact(rel, data)
    return converters.from_canonical(env, art).files.get(rel, data)


def canonical(rel: str, data: bytes) -> bytes:
    """Content with any pskt-injected frontmatter removed (for comparisons)."""
    if Path(rel).name != "SKILL.md":
        return data
    art = _skill_artifact(rel, data)
    return converters.to_canonical("claude", art).files.get(rel, data)
