"""Resolvedor de paths usados pelo CLI.

Convenções:
- Config (config.toml, installed.toml do scope root): platformdirs user_config_dir.
- Workspace (clone do registry remoto): ~/.pskt/ (fixo, conforme decisão do projeto).
- Instalações consumidas pelo Claude Code:
  - root scope:    ~/.claude/
  - project scope: ./.claude/ (relativo ao cwd, ou a um project_root informado).
- installed.toml por scope: registra o que cada `pskt install` colocou em disco.
"""
from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "pskt"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def config_file() -> Path:
    return config_dir() / "config.toml"


def installed_root_file() -> Path:
    return config_dir() / "installed.toml"


def workspace_dir() -> Path:
    return Path.home() / ".pskt"


def claude_root_dir() -> Path:
    return Path.home() / ".claude"


def claude_project_dir(project_root: Path | None = None) -> Path:
    return (project_root or Path.cwd()) / ".claude"


def installed_project_file(project_root: Path | None = None) -> Path:
    return claude_project_dir(project_root) / ".pskt-installed.toml"
