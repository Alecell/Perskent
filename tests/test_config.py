"""Config schema: [env] as a per-scope list, with backward-compatible coercion."""
from __future__ import annotations

import pytest

from perskent import config


def test_string_env_is_coerced_to_list():
    cfg = config.Config.from_dict({
        "registry": {"url": "u", "auth_method": "ssh"},
        "env": {"root": "claude", "project": "codex"},
    })
    assert cfg.code_agents_root == ["claude"]
    assert cfg.code_agents_project == ["codex"]


def test_list_env_preserved_and_deduped():
    cfg = config.Config.from_dict({
        "registry": {"url": "u"},
        "env": {"root": ["claude", "codex", "claude"], "project": ["cursor"]},
    })
    assert cfg.code_agents_root == ["claude", "codex"]
    assert cfg.code_agents_project == ["cursor"]


def test_invalid_agent_rejected():
    with pytest.raises(ValueError):
        config.Config.from_dict({
            "registry": {"url": "u"},
            "env": {"root": ["nope"], "project": ["claude"]},
        })


def test_empty_list_rejected():
    with pytest.raises(ValueError):
        config.Config.from_dict({
            "registry": {"url": "u"},
            "env": {"root": [], "project": ["claude"]},
        })


def test_missing_env_section_raises_schema_error():
    with pytest.raises(config.ConfigSchemaError):
        config.Config.from_dict({"registry": {"url": "u"}})


def test_roundtrip_and_agents_for():
    cfg = config.Config(
        registry_url="u", auth_method="ssh",
        code_agents_root=["claude", "codex"], code_agents_project=["cursor"],
    )
    data = cfg.to_dict()
    assert data["env"]["root"] == ["claude", "codex"]
    again = config.Config.from_dict(data)
    assert again.agents_for("root") == ["claude", "codex"]
    assert again.agents_for("project") == ["cursor"]
