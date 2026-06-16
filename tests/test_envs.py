"""envs — destination path mapping per code-agent."""
from __future__ import annotations

from perskent import envs


def test_codex_skills_land_in_codex_dir():
    # Modern Codex reads skills from ~/.codex/skills (the env base), NOT ~/.agents.
    assert envs.dest_relative(envs.ENV_CODEX, "root", "skill") == ".codex"
    assert envs.dest_relative(envs.ENV_CODEX, "project", "skill") == ".codex"


def test_zed_still_uses_agents_convention():
    # Zed keeps the cross-tool ~/.agents/skills convention Codex moved away from.
    assert envs.dest_relative(envs.ENV_ZED, "root", "skill") == ".agents"


def test_codex_supports_only_skills_verbatim():
    # Skills copy 1:1 (SKILL.md is shared). Agents/commands would need a TOML /
    # format conversion perskent does not do, so they stay out.
    assert envs.supports_kind(envs.ENV_CODEX, "skill")
    assert not envs.supports_kind(envs.ENV_CODEX, "agent")
    assert not envs.supports_kind(envs.ENV_CODEX, "command")
