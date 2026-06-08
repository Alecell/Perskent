"""Shared fixtures: isolate HOME / XDG / cwd so commands touch only tmp dirs."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from perskent import config


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A clean sandbox: $HOME and $XDG_CONFIG_HOME under tmp, cwd in a project,
    and a saved config (root: claude+codex, project: claude+cursor)."""
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.chdir(proj)

    config.save(config.Config(
        registry_url="git@example.com:me/registry.git",
        auth_method="ssh",
        code_agents_root=["claude", "codex"],
        code_agents_project=["claude", "cursor"],
    ))
    return SimpleNamespace(home=home, proj=proj, workspace=home / ".pskt")


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
