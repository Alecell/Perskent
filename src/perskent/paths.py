"""Path resolver used across the CLI.

Conventions:
- Config (config.toml, root scope's installed.toml): platformdirs user_config_dir.
- Workspace (clone of the remote registry): ~/.pskt/ (fixed, per project decision).
- Installations consumed by Claude Code:
  - root scope:    ~/.claude/
  - project scope: ./.claude/ (relative to cwd, or to a given project_root).
- Per-scope installed.toml: records what each `pskt install` placed on disk.
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
