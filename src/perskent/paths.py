"""Path resolver used across the CLI.

Conventions:
- Config (config.toml, root scope's installed.toml): platformdirs user_config_dir.
- Workspace (clone of the remote registry): ~/.pskt/ (fixed, per project decision).
- Installations consumed by the chosen code-agent:
  - root scope:    ~/<env-base>/    (e.g. ~/.claude/, ~/.config/opencode/, ~/.qwen/, ~/.codex/, ~/.cursor/)
  - project scope: ./<env-base>/    (relative to cwd, or to a given project_root)
- Per-scope installed.toml records what each `pskt install` placed on disk.

The env-base path depends on the code-agent chosen for the scope. See `envs`.
"""
from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir

from perskent import envs

APP_NAME = "pskt"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def config_file() -> Path:
    return config_dir() / "config.toml"


def installed_root_file() -> Path:
    return config_dir() / "installed.toml"


def workspace_dir() -> Path:
    return Path.home() / ".pskt"


def env_base_root_dir(env: str) -> Path:
    """Canonical base dir of `env` in the root scope (e.g. ~/.claude/)."""
    return Path.home() / envs.base_relative(env, "root")


def env_base_project_dir(env: str, project_root: Path | None = None) -> Path:
    """Canonical base dir of `env` in the project scope (e.g. ./.claude/)."""
    return (project_root or Path.cwd()) / envs.base_relative(env, "project")


def dest_root_dir(env: str, kind: str) -> Path:
    """Where files of `kind` are mirrored in the root scope (env-aware)."""
    return Path.home() / envs.dest_relative(env, "root", kind)


def dest_project_dir(env: str, kind: str, project_root: Path | None = None) -> Path:
    """Where files of `kind` are mirrored in the project scope (env-aware)."""
    return (project_root or Path.cwd()) / envs.dest_relative(env, "project", kind)


def installed_project_file(env: str, project_root: Path | None = None) -> Path:
    """The project-scope installed.toml lives inside the env's canonical base dir."""
    return env_base_project_dir(env, project_root) / ".pskt-installed.toml"
