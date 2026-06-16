"""compat — Codex skill frontmatter injection, reversibly."""
from __future__ import annotations

from perskent import compat, envs

NO_FM = b"> **Role:** Product Owner do Reapho\n\n## SYSTEM ROLE\n\nVoce e o Jeff.\n"
AUTHOR_FM = b"---\nname: prd-maker\ndescription: Make PRDs.\n---\n\n# PRD Maker\n"


def test_injects_frontmatter_into_codex_when_missing():
    out = compat.project(envs.ENV_CODEX, "skills/jeff-patton/SKILL.md", NO_FM)
    assert out.startswith(b"---\n")
    assert b"name: " in out
    assert b"description: " in out
    assert compat.AUTO_MARKER.encode() in out
    # name is derived from the skill folder; description from the body.
    assert b'"jeff-patton"' in out
    assert b"Product Owner do Reapho" in out
    # original body is preserved after the injected block.
    assert out.rstrip().endswith(b"Voce e o Jeff.")


def test_author_frontmatter_left_untouched_into_codex():
    out = compat.project(envs.ENV_CODEX, "skills/prd-maker/SKILL.md", AUTHOR_FM)
    assert out == AUTHOR_FM


def test_non_codex_target_gets_verbatim_when_no_injection():
    out = compat.project(envs.ENV_CLAUDE, "skills/jeff-patton/SKILL.md", NO_FM)
    assert out == NO_FM


def test_round_trip_codex_then_back_is_clean():
    # claude(raw) -> codex(injected) -> claude(must be raw again, not polluted).
    injected = compat.project(envs.ENV_CODEX, "skills/jeff-patton/SKILL.md", NO_FM)
    back = compat.project(envs.ENV_CLAUDE, "skills/jeff-patton/SKILL.md", injected)
    assert back == NO_FM


def test_injection_is_idempotent():
    once = compat.project(envs.ENV_CODEX, "skills/jeff-patton/SKILL.md", NO_FM)
    twice = compat.project(envs.ENV_CODEX, "skills/jeff-patton/SKILL.md", once)
    assert twice == once


def test_canonical_strips_only_our_block():
    injected = compat.project(envs.ENV_CODEX, "skills/jeff-patton/SKILL.md", NO_FM)
    assert compat.canonical("skills/jeff-patton/SKILL.md", injected) == NO_FM
    # author frontmatter is canonical content, not stripped.
    assert compat.canonical("skills/prd-maker/SKILL.md", AUTHOR_FM) == AUTHOR_FM


def test_non_skill_files_never_touched():
    data = b"# template\nno frontmatter here\n"
    assert compat.project(envs.ENV_CODEX, "skills/x/templates/t.md", data) == data
