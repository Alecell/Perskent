"""Read/write of config.toml (registry URL, auth method, code-agent per scope).

The token does NOT live here — it goes to the OS keyring via `auth.py`.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass

import tomli_w

from perskent import envs
from perskent.paths import config_dir, config_file


class ConfigSchemaError(ValueError):
    """Raised when config.toml is from an older schema and needs reinit."""


@dataclass
class Config:
    registry_url: str
    auth_method: str           # "ssh" | "https"
    code_agent_root: str       # one of envs.ENVS
    code_agent_project: str    # one of envs.ENVS

    def to_dict(self) -> dict:
        return {
            "registry": {
                "url": self.registry_url,
                "auth_method": self.auth_method,
            },
            "env": {
                "root": self.code_agent_root,
                "project": self.code_agent_project,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        registry = data.get("registry") or {}
        if "url" not in registry:
            raise ValueError("invalid config.toml: missing [registry].url")

        env_section = data.get("env")
        if not env_section or "root" not in env_section or "project" not in env_section:
            raise ConfigSchemaError(
                "config.toml is from an older perskent version (missing \\[env] section). "
                "Run `pskt init --force` to reconfigure."
            )

        root_env = env_section["root"]
        project_env = env_section["project"]
        if not envs.is_valid(root_env):
            raise ValueError(
                f"invalid [env].root: {root_env!r}. Must be one of {envs.ENVS}."
            )
        if not envs.is_valid(project_env):
            raise ValueError(
                f"invalid [env].project: {project_env!r}. Must be one of {envs.ENVS}."
            )

        return cls(
            registry_url=registry["url"],
            auth_method=registry.get("auth_method") or "ssh",
            code_agent_root=root_env,
            code_agent_project=project_env,
        )


def exists() -> bool:
    return config_file().exists()


def load() -> Config | None:
    path = config_file()
    if not path.exists():
        return None
    with path.open("rb") as f:
        data = tomllib.load(f)
    return Config.from_dict(data)


def load_or_die() -> Config:
    """Load the config or exit cleanly with a user-facing message.

    Replaces the `if not config.exists(): die; cfg = config.load(); assert cfg`
    pattern at call sites, and catches `ConfigSchemaError` (raised when the
    saved config is from an older perskent version) so the user sees a clean
    "run pskt init --force" message instead of a traceback.
    """
    from perskent import ui  # late import to avoid a cycle at module load
    if not exists():
        ui.die("perskent is not initialized. Run `pskt init` first.")
    try:
        cfg = load()
    except ConfigSchemaError as e:
        ui.die(str(e))
    assert cfg is not None
    return cfg


def save(cfg: Config) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    with config_file().open("wb") as f:
        tomli_w.dump(cfg.to_dict(), f)


def delete() -> None:
    path = config_file()
    if path.exists():
        path.unlink()
