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


def test_codex_supports_skill_and_agent_not_command():
    # Skills copy 1:1; agents convert md->TOML. Codex commands are deprecated
    # prompts (use skills), so command stays out.
    assert envs.supports_kind(envs.ENV_CODEX, "skill")
    assert envs.supports_kind(envs.ENV_CODEX, "agent")
    assert not envs.supports_kind(envs.ENV_CODEX, "command")


def test_cursor_drops_command_keeps_agent_skill():
    # Cursor commands are `.mdc` rules (a different concept) — not modeled.
    assert envs.supports_kind(envs.ENV_CURSOR, "agent")
    assert envs.supports_kind(envs.ENV_CURSOR, "skill")
    assert not envs.supports_kind(envs.ENV_CURSOR, "command")
