"""Registro de pacotes instalados, por scope.

Persistência em TOML:
- root scope:    ~/.config/pskt/installed.toml
- project scope: ./.claude/.pskt-installed.toml

Schema (chave do dict é o `qualified_name` do pacote: <kind>s/<name>):

    [packages."agents/my-agent"]
    name = "my-agent"
    kind = "agent"
    version = "1.0.0"
    installed_at = "2026-05-10T17:30:00Z"
    source_commit = "abc123"          # opcional
    installed_paths = [               # paths relativos ao .claude/ do scope
      "agents/my-agent.md",
      "agent-memory/my-agent/context.md",
    ]

A chave qualificada permite ter `agents/foo` e `skills/foo` instalados
simultaneamente sem colidir.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from perskent.paths import installed_project_file, installed_root_file

ROOT = "root"
PROJECT = "project"
SCOPES = (ROOT, PROJECT)


@dataclass
class InstalledPackage:
    name: str
    kind: str          # "agent" | "skill" | "command"
    version: str
    scope: str         # "root" | "project"
    installed_at: str
    source_commit: str | None
    installed_paths: list[str]

    @property
    def qualified_name(self) -> str:
        return f"{self.kind}s/{self.name}"


def _registry_path(scope: str, project_root: Path | None = None) -> Path:
    if scope == ROOT:
        return installed_root_file()
    if scope == PROJECT:
        return installed_project_file(project_root)
    raise ValueError(f"scope inválido: {scope!r}. Use 'root' ou 'project'.")


def load(scope: str, project_root: Path | None = None) -> dict[str, InstalledPackage]:
    """Lê installed.toml do scope. Retorna dict {qualified_name: InstalledPackage}.
    Se o arquivo não existe, retorna dict vazio."""
    path = _registry_path(scope, project_root)
    if not path.exists():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)

    packages: dict[str, InstalledPackage] = {}
    for qualified, entry in (data.get("packages") or {}).items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")) or qualified.split("/", 1)[-1]
        kind = str(entry.get("kind", "")) or "unknown"
        packages[qualified] = InstalledPackage(
            name=name,
            kind=kind,
            version=str(entry.get("version", "")),
            scope=scope,
            installed_at=str(entry.get("installed_at", "")),
            source_commit=entry.get("source_commit"),
            installed_paths=list(entry.get("installed_paths", [])),
        )
    return packages


def save(packages: dict[str, InstalledPackage], scope: str, project_root: Path | None = None) -> None:
    path = _registry_path(scope, project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {"packages": {}}
    for qualified, pkg in packages.items():
        entry: dict = {
            "name": pkg.name,
            "kind": pkg.kind,
            "version": pkg.version,
            "installed_at": pkg.installed_at,
            "installed_paths": pkg.installed_paths,
        }
        if pkg.source_commit:
            entry["source_commit"] = pkg.source_commit
        out["packages"][qualified] = entry
    with path.open("wb") as f:
        tomli_w.dump(out, f)


def all_installed(project_root: Path | None = None) -> list[InstalledPackage]:
    """Lista pacotes instalados em ambos os scopes."""
    result = list(load(ROOT).values())
    result.extend(load(PROJECT, project_root).values())
    return result


def find_by_name(name: str, project_root: Path | None = None) -> list[InstalledPackage]:
    """Retorna instalações desse nome (pode estar em kinds e/ou scopes diferentes)."""
    return [p for p in all_installed(project_root) if p.name == name]
