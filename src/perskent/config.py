"""Read/write of config.toml (registry URL and auth method).

The token does NOT live here — it goes to the OS keyring via `auth.py`.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass

import tomli_w

from perskent.paths import config_dir, config_file


@dataclass
class Config:
    registry_url: str
    auth_method: str  # "ssh" | "https"

    def to_dict(self) -> dict:
        return {
            "registry": {
                "url": self.registry_url,
                "auth_method": self.auth_method,
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        registry = data.get("registry") or {}
        if "url" not in registry:
            raise ValueError("invalid config.toml: missing [registry].url")
        return cls(
            registry_url=registry["url"],
            auth_method=registry.get("auth_method") or "ssh",
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


def save(cfg: Config) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    with config_file().open("wb") as f:
        tomli_w.dump(cfg.to_dict(), f)


def delete() -> None:
    path = config_file()
    if path.exists():
        path.unlink()
