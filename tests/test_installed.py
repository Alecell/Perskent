"""installed.toml: env-keyed storage + legacy migration."""
from __future__ import annotations

from perskent import installed as installed_mod
from perskent.installed import InstalledPackage


def _rec(name="foo", kind="skill", env="claude", version="1.0.0"):
    return InstalledPackage(
        name=name, kind=kind, version=version, scope="root", env=env,
        installed_at="2026-01-01T00:00:00Z", source_commit=None,
        installed_paths=[f"{kind}s/{name}/SKILL.md"],
    )


def test_storage_key_and_qualified_name():
    r = _rec(env="codex")
    assert r.qualified_name == "skills/foo"
    assert r.storage_key == "codex/skills/foo"
    assert installed_mod.storage_key("codex", "skills/foo") == "codex/skills/foo"


def test_parse_legacy_key_is_rekeyed(tmp_path):
    # Pre-1.0 record: key without env, no env field → defaults to claude.
    f = tmp_path / "installed.toml"
    f.write_text(
        '[packages."skills/foo"]\n'
        'name = "foo"\nkind = "skill"\nversion = "0.1.0"\n'
        'installed_at = "x"\ninstalled_paths = ["skills/foo/SKILL.md"]\n',
        encoding="utf-8",
    )
    parsed = installed_mod._parse_file(f, "root")
    assert set(parsed) == {"claude/skills/foo"}
    assert parsed["claude/skills/foo"].env == "claude"


def test_parse_new_key_with_env(tmp_path):
    f = tmp_path / "installed.toml"
    f.write_text(
        '[packages."codex/skills/bar"]\n'
        'name = "bar"\nkind = "skill"\nversion = "2.0.0"\nenv = "codex"\n'
        'installed_at = "x"\ninstalled_paths = ["skills/bar/SKILL.md"]\n',
        encoding="utf-8",
    )
    parsed = installed_mod._parse_file(f, "root")
    assert parsed["codex/skills/bar"].env == "codex"
    assert parsed["codex/skills/bar"].version == "2.0.0"


def test_save_load_roundtrip_two_envs(isolated):
    state = {r.storage_key: r for r in (_rec(env="claude"), _rec(env="codex"))}
    installed_mod.save(state, "root")
    loaded = installed_mod.load("root")
    assert set(loaded) == {"claude/skills/foo", "codex/skills/foo"}


def test_project_legacy_location_is_migrated(isolated):
    # Old per-env project file lived inside .claude/.
    legacy = isolated.proj / ".claude" / ".pskt-installed.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        '[packages."skills/foo"]\n'
        'name = "foo"\nkind = "skill"\nversion = "0.1.0"\nenv = "claude"\n'
        'installed_at = "x"\ninstalled_paths = ["skills/foo/SKILL.md"]\n',
        encoding="utf-8",
    )
    # Neutral file absent → load merges the legacy per-env file forward.
    loaded = installed_mod.load("project", project_root=isolated.proj)
    assert "claude/skills/foo" in loaded
