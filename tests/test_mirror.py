"""pskt mirror — symmetric union, conflict (newest), directional, dry-run."""
from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from perskent.cli import app

runner = CliRunner()


def _skill(proj: Path, env: str, content: str, mtime: float | None = None) -> Path:
    f = proj / f".{env}" / "skills" / "foo" / "SKILL.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    if mtime is not None:
        os.utime(f, (mtime, mtime))
    return f


def test_symmetric_union_copies_to_missing_agent(isolated):
    # Only claude has the skill; cursor should receive it.
    _skill(isolated.proj, "claude", "hello")
    res = runner.invoke(app, ["mirror", "--scope", "project", "--only", "skills/foo"])
    assert res.exit_code == 0, res.output
    cursor_file = isolated.proj / ".cursor" / "skills" / "foo" / "SKILL.md"
    assert cursor_file.read_text() == "hello"


def test_conflict_newest_wins(isolated):
    _skill(isolated.proj, "claude", "NEW", mtime=2_000_000_000)
    _skill(isolated.proj, "cursor", "OLD", mtime=1_000_000_000)
    res = runner.invoke(app, ["mirror", "--scope", "project", "--only", "skills/foo"])
    assert res.exit_code == 0, res.output
    cursor_file = isolated.proj / ".cursor" / "skills" / "foo" / "SKILL.md"
    assert cursor_file.read_text() == "NEW"
    assert "conflict" in res.output.lower()


def test_strategy_abort_writes_nothing(isolated):
    _skill(isolated.proj, "claude", "NEW", mtime=2_000_000_000)
    _skill(isolated.proj, "cursor", "OLD", mtime=1_000_000_000)
    res = runner.invoke(
        app, ["mirror", "--scope", "project", "--only", "skills/foo", "--strategy", "abort"]
    )
    assert res.exit_code == 1
    # cursor untouched
    assert (isolated.proj / ".cursor" / "skills" / "foo" / "SKILL.md").read_text() == "OLD"


def test_directional_from_source_always_wins(isolated):
    _skill(isolated.proj, "claude", "NEWER", mtime=2_000_000_000)
    _skill(isolated.proj, "cursor", "OLDER", mtime=1_000_000_000)
    # Even though claude is newer, --from cursor makes cursor authoritative.
    res = runner.invoke(
        app, ["mirror", "--scope", "project", "--only", "skills/foo", "--from", "cursor", "--to", "claude"]
    )
    assert res.exit_code == 0, res.output
    assert (isolated.proj / ".claude" / "skills" / "foo" / "SKILL.md").read_text() == "OLDER"


def test_dry_run_touches_nothing(isolated):
    _skill(isolated.proj, "claude", "hello")
    res = runner.invoke(app, ["mirror", "--scope", "project", "--only", "skills/foo", "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "would copy" in res.output.lower()
    assert not (isolated.proj / ".cursor" / "skills" / "foo").exists()


def _enable_codex_project():
    from perskent import config
    cfg = config.load()
    cfg.code_agents_project = ["claude", "codex"]
    config.save(cfg)


def test_mirror_claude_to_codex_lands_in_codex_skills(isolated):
    # End-to-end: a skill refined in .claude must land where modern Codex reads
    # skills (.codex/skills/), not the legacy .agents/ location.
    _enable_codex_project()
    _skill(isolated.proj, "claude", "---\nname: foo\ndescription: x\n---\nbody")
    res = runner.invoke(
        app, ["mirror", "--scope", "project", "--only", "skills/foo", "--from", "claude", "--to", "codex"]
    )
    assert res.exit_code == 0, res.output
    dest = isolated.proj / ".codex" / "skills" / "foo" / "SKILL.md"
    assert dest.read_text() == "---\nname: foo\ndescription: x\n---\nbody"  # author FM verbatim
    assert not (isolated.proj / ".agents" / "skills" / "foo").exists()


def test_mirror_into_codex_injects_frontmatter_when_missing(isolated):
    # A frontmatter-less skill (e.g. a persona loaded by path) must become
    # Codex-discoverable automatically — pskt injects name/description.
    _enable_codex_project()
    _skill(isolated.proj, "claude", "> **Role:** Product Owner\n\n## ROLE\nbody\n")
    res = runner.invoke(
        app, ["mirror", "--scope", "project", "--only", "skills/foo", "--from", "claude", "--to", "codex"]
    )
    assert res.exit_code == 0, res.output
    dest = (isolated.proj / ".codex" / "skills" / "foo" / "SKILL.md").read_text()
    assert dest.startswith("---\n")
    assert "name: " in dest and "description: " in dest
    assert "Product Owner" in dest
    # source .claude copy stays pristine (no injection upstream).
    assert (isolated.proj / ".claude" / "skills" / "foo" / "SKILL.md").read_text().startswith(">")


def test_mirror_into_codex_is_idempotent(isolated):
    # Second run must be a no-op: injected frontmatter must not look "different".
    _enable_codex_project()
    _skill(isolated.proj, "claude", "> **Role:** PO\n\nbody\n")
    args = ["mirror", "--scope", "project", "--only", "skills/foo", "--from", "claude", "--to", "codex"]
    assert runner.invoke(app, args).exit_code == 0
    res2 = runner.invoke(app, args)
    assert res2.exit_code == 0, res2.output
    assert "nothing to mirror" in res2.output.lower()


def test_refuses_single_agent_scope(isolated):
    # Root scope is claude+codex but codex doesn't support... actually 2 agents.
    # Force a single-agent scope to assert the guard.
    from perskent import config
    cfg = config.load()
    cfg.code_agents_project = ["claude"]
    config.save(cfg)
    _skill(isolated.proj, "claude", "hello")
    res = runner.invoke(app, ["mirror", "--scope", "project", "--only", "skills/foo"])
    assert res.exit_code == 1
    assert "code-agent configured" in res.output.lower()
