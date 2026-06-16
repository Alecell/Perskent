"""Converter layer: frontmatter utils, per-converter behavior, round-trips."""
from __future__ import annotations

import tomllib

import pytest

from perskent import converters, envs
from perskent.converters import base


# --------------------------------------------------------------------------
# base: frontmatter parse/build
# --------------------------------------------------------------------------

def test_frontmatter_roundtrip_and_idempotent():
    raw = b'---\nname: "foo"\ndescription: "A thing"\nmodel: "sonnet"\n---\n\nBody line.\n'
    fm, body = base.parse_frontmatter(raw)
    assert fm == {"name": "foo", "description": "A thing", "model": "sonnet"}
    assert body == b"Body line.\n"
    rebuilt = base.build_frontmatter(fm, body)
    # normalize is idempotent
    assert base.normalize_md(rebuilt, base.AGENT_KEY_ORDER) == base.normalize_md(raw, base.AGENT_KEY_ORDER)
    assert base.normalize_md(base.normalize_md(raw, base.AGENT_KEY_ORDER), base.AGENT_KEY_ORDER) \
        == base.normalize_md(raw, base.AGENT_KEY_ORDER)


def test_frontmatter_no_blank_line_body_preserved():
    raw = b"---\nname: foo\n---\nimmediate body\n"
    fm, body = base.parse_frontmatter(raw)
    assert body == b"immediate body\n"


def test_parse_inline_list_and_nested_map():
    raw = b'---\ntools: [Read, Glob]\nmetadata:\n  k: "v"\n---\nx'
    fm, _ = base.parse_frontmatter(raw)
    assert fm["tools"] == ["Read", "Glob"]
    assert fm["metadata"] == {"k": "v"}


# --------------------------------------------------------------------------
# skill: injection for every non-canonical target
# --------------------------------------------------------------------------

NO_FM = b"> **Role:** PO do Reapho\n\n## ROLE\nbody\n"


@pytest.mark.parametrize("env", ["codex", "opencode", "qwen", "cursor", "zed", "cline"])
def test_skill_injects_for_non_claude_targets(env):
    art = converters.build_artifact("skill", "foo", {"skills/foo/SKILL.md": NO_FM})
    out = converters.from_canonical(env, art).files["skills/foo/SKILL.md"]
    assert out.startswith(b"---\n")
    assert b"name: " in out and b"description: " in out
    assert base.AUTO_MARKER.encode() in out


def test_skill_claude_target_stays_pristine():
    art = converters.build_artifact("skill", "foo", {"skills/foo/SKILL.md": NO_FM})
    out = converters.from_canonical("claude", art).files["skills/foo/SKILL.md"]
    assert out == NO_FM


def test_skill_roundtrip_clean():
    art = converters.build_artifact("skill", "foo", {"skills/foo/SKILL.md": NO_FM})
    injected = converters.from_canonical("codex", art).files["skills/foo/SKILL.md"]
    back = converters.canonical_files("codex", "skill", "foo", {"skills/foo/SKILL.md": injected})
    assert back["skills/foo/SKILL.md"] == NO_FM


# --------------------------------------------------------------------------
# codex agent: md+files <-> single TOML
# --------------------------------------------------------------------------

def _canon_agent(name="foo", with_model=True, body=b"Stay focused.\nTrace paths.\n"):
    fm = {"name": name, "description": "An explorer agent."}
    if with_model:
        fm["model"] = "sonnet"
    return base.build_frontmatter(base.ordered_fm(fm, base.AGENT_KEY_ORDER), body)


def test_codex_agent_from_canonical_emits_toml():
    canon = _canon_agent()
    art = converters.build_artifact("agent", "foo", {"agents/foo.md": canon})
    res = converters.from_canonical("codex", art)
    assert set(res.files) == {"agents/foo.toml"}
    data = tomllib.loads(res.files["agents/foo.toml"].decode())
    assert data["name"] == "foo"
    assert data["description"] == "An explorer agent."
    assert data["model"] == "sonnet"
    assert data["developer_instructions"] == "Stay focused.\nTrace paths.\n"


def test_codex_agent_roundtrip_no_supporting_files_is_byte_stable():
    canon = _canon_agent()
    fwd = converters.from_canonical("codex", converters.build_artifact("agent", "foo", {"agents/foo.md": canon}))
    back = converters.to_canonical("codex", converters.build_artifact("agent", "foo", fwd.files))
    assert back.files["agents/foo.md"] == canon


def test_codex_agent_drops_supporting_files_with_warning():
    canon = _canon_agent()
    files = {"agents/foo.md": canon, "templates/foo/t.md": b"tpl", "extra.md": b"x"}
    res = converters.from_canonical("codex", converters.build_artifact("agent", "foo", files))
    assert set(res.files) == {"agents/foo.toml"}
    assert res.dropped and any("supporting file" in w for w in res.warnings)


def test_codex_agent_warns_on_tools():
    canon = base.build_frontmatter(
        {"name": "foo", "description": "d", "tools": ["Read", "Glob"]}, b"body\n"
    )
    res = converters.from_canonical("codex", converters.build_artifact("agent", "foo", {"agents/foo.md": canon}))
    assert any("tools" in w for w in res.warnings)


def test_codex_agent_preserves_codex_fields_via_x_keys():
    # codex-only fields survive a codex -> claude -> codex round-trip.
    toml = b'name = "foo"\ndescription = "d"\nmodel_reasoning_effort = "high"\nsandbox_mode = "read-only"\ndeveloper_instructions = "body\\n"\n'
    canon = converters.to_canonical("codex", converters.build_artifact("agent", "foo", {"agents/foo.toml": toml})).files["agents/foo.md"]
    assert b"x-codex-reasoning" in canon and b"x-codex-sandbox" in canon
    back = converters.from_canonical("codex", converters.build_artifact("agent", "foo", {"agents/foo.md": canon}))
    data = tomllib.loads(back.files["agents/foo.toml"].decode())
    assert data["model_reasoning_effort"] == "high"
    assert data["sandbox_mode"] == "read-only"


# --------------------------------------------------------------------------
# gemini command: md <-> single TOML
# --------------------------------------------------------------------------

def test_gemini_command_from_canonical_emits_toml():
    canon = base.build_frontmatter({"description": "Refactor."}, b"Refactor the code.\n")
    res = converters.from_canonical("gemini", converters.build_artifact("command", "ref", {"commands/ref.md": canon}))
    assert set(res.files) == {"commands/ref.toml"}
    data = tomllib.loads(res.files["commands/ref.toml"].decode())
    assert data["description"] == "Refactor."
    assert data["prompt"] == "Refactor the code.\n"


def test_gemini_command_roundtrip_byte_stable():
    canon = base.build_frontmatter({"description": "Refactor."}, b"Refactor the code.\n")
    fwd = converters.from_canonical("gemini", converters.build_artifact("command", "ref", {"commands/ref.md": canon}))
    back = converters.to_canonical("gemini", converters.build_artifact("command", "ref", fwd.files))
    assert back.files["commands/ref.md"] == canon


# --------------------------------------------------------------------------
# opencode agent: mode defaulted + warns; canonical drops mode
# --------------------------------------------------------------------------

def test_opencode_agent_defaults_mode_with_warning():
    canon = _canon_agent()
    res = converters.from_canonical("opencode", converters.build_artifact("agent", "foo", {"agents/foo.md": canon}))
    fm, _ = base.parse_frontmatter(res.files["agents/foo.md"])
    assert fm["mode"] == "subagent"
    assert any("mode" in w for w in res.warnings)


def test_opencode_agent_to_canonical_drops_mode():
    md = base.build_frontmatter({"name": "foo", "description": "d", "mode": "primary"}, b"body\n")
    canon = converters.to_canonical("opencode", converters.build_artifact("agent", "foo", {"agents/foo.md": md})).files["agents/foo.md"]
    fm, _ = base.parse_frontmatter(canon)
    assert "mode" not in fm


# --------------------------------------------------------------------------
# gate <-> registry consistency
# --------------------------------------------------------------------------

def test_supported_kinds_match_registered_converters():
    for env, kinds in envs.SUPPORTED_KINDS.items():
        for kind in kinds:
            assert not converters.is_skip(env, kind), f"{env}/{kind} in SUPPORTED_KINDS but no converter"
    for (env, kind) in converters.registered_pairs():
        assert envs.supports_kind(env, kind), f"{env}/{kind} registered but not in SUPPORTED_KINDS"


def test_dest_layout_codex_agent_is_single_toml():
    layout = converters.dest_layout("codex", "agent", "foo")
    assert layout.primary == "agents/foo.toml"
    assert layout.is_single_file


def test_dest_layout_skill_is_dir():
    layout = converters.dest_layout("cursor", "skill", "foo")
    assert layout.primary == "skills/foo/SKILL.md"
    assert not layout.is_single_file
