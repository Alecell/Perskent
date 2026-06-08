"""pskt install --agent all → installs into every configured agent of the scope."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from perskent import installed as installed_mod
from perskent.cli import app

runner = CliRunner()


def _registry_skill(workspace: Path, name: str, version: str = "1.0.0") -> None:
    """Create a registry package: manifest + a 1:1 install mirror (skills/<name>/)."""
    pkg = workspace / "skills" / name
    (pkg).mkdir(parents=True, exist_ok=True)
    (pkg / "manifest.toml").write_text(
        f'[package]\nname = "{name}"\nversion = "{version}"\n', encoding="utf-8"
    )
    mirror = pkg / "skills" / name / "SKILL.md"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text("body", encoding="utf-8")


def test_install_all_lands_in_every_agent(isolated):
    _registry_skill(isolated.workspace, "foo")
    res = runner.invoke(app, ["install", "skills/foo", "project", "--agent", "all"])
    assert res.exit_code == 0, res.output

    assert (isolated.proj / ".claude" / "skills" / "foo" / "SKILL.md").exists()
    assert (isolated.proj / ".cursor" / "skills" / "foo" / "SKILL.md").exists()

    state = installed_mod.load("project", project_root=isolated.proj)
    assert set(state) == {"claude/skills/foo", "cursor/skills/foo"}


def test_install_single_agent(isolated):
    _registry_skill(isolated.workspace, "bar")
    res = runner.invoke(app, ["install", "skills/bar", "project", "--agent", "cursor"])
    assert res.exit_code == 0, res.output
    assert (isolated.proj / ".cursor" / "skills" / "bar" / "SKILL.md").exists()
    assert not (isolated.proj / ".claude" / "skills" / "bar").exists()
    state = installed_mod.load("project", project_root=isolated.proj)
    assert set(state) == {"cursor/skills/bar"}


def test_install_unconfigured_agent_is_rejected(isolated):
    _registry_skill(isolated.workspace, "baz")
    res = runner.invoke(app, ["install", "skills/baz", "project", "--agent", "qwen"])
    assert res.exit_code == 1
    assert "not configured" in res.output.lower()
