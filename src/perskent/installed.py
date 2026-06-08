"""Record of installed packages, per scope.

Persisted as TOML:
- root scope:    ~/.config/pskt/installed.toml
- project scope: ./.pskt-installed.toml  (project root, cross-agent)

Schema (the dict key is the package's `storage_key`: <env>/<kind>s/<name>):

    [packages."claude/agents/my-agent"]
    name = "my-agent"
    kind = "agent"
    version = "1.0.0"
    env = "claude"                    # code-agent this copy was installed for
    installed_at = "2026-05-10T17:30:00Z"
    source_commit = "abc123"          # optional
    installed_paths = [               # paths relative to the package's dest dir
      "agents/my-agent.md",
      "agent-memory/my-agent/context.md",
    ]

`env` is the code-agent the copy was installed for. Including it in the key
lets the SAME package be installed for several code-agents in one scope
(e.g. `claude/skills/foo` and `codex/skills/foo`), which is what enables
`pskt install ... --agent all` and `pskt mirror`.

Migration (pre-1.0 → 1.0):
- The key used to be `<kind>s/<name>` (no env). Such records are re-keyed to
  `<env>/<kind>s/<name>`, with `env` taken from the entry (defaulting to
  "claude", the only code-agent before multi-agent support).
- The project-scope file used to live inside the active env's base dir
  (`./<env-base>/.pskt-installed.toml`). When the neutral file is absent,
  `load` reads every known env's legacy location and merges them forward.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from perskent import envs
from perskent.paths import (
    installed_project_file,
    installed_project_file_legacy,
    installed_root_file,
)

ROOT = "root"
PROJECT = "project"
SCOPES = (ROOT, PROJECT)


@dataclass
class InstalledPackage:
    name: str
    kind: str          # "agent" | "skill" | "command"
    version: str
    scope: str         # "root" | "project"
    env: str           # code-agent this copy was installed for (one of envs.ENVS)
    installed_at: str
    source_commit: str | None
    installed_paths: list[str]

    @property
    def qualified_name(self) -> str:
        """Kind-qualified, env-agnostic name, e.g. 'agents/foo'. Matches the
        registry package's qualified_name (the registry has no env dimension)."""
        return f"{self.kind}s/{self.name}"

    @property
    def storage_key(self) -> str:
        """Unique key within a scope: '<env>/<kind>s/<name>'."""
        return f"{self.env}/{self.kind}s/{self.name}"


def storage_key(env: str, qualified_name: str) -> str:
    """Build the per-scope storage key from an env and a kind-qualified name."""
    return f"{env}/{qualified_name}"


def _parse_file(path: Path, scope: str) -> dict[str, InstalledPackage]:
    """Parse one installed.toml into {storage_key: InstalledPackage}.

    Re-keys both legacy (`<kind>s/<name>`) and current (`<env>/<kind>s/<name>`)
    entries to the canonical storage_key derived from the record's fields.
    """
    if not path.exists():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)

    packages: dict[str, InstalledPackage] = {}
    for key, entry in (data.get("packages") or {}).items():
        if not isinstance(entry, dict):
            continue
        # Legacy records (pre multi-code-agent) didn't store env. Back then the
        # only supported code-agent was Claude Code.
        env = str(entry.get("env", "")) or "claude"
        name = str(entry.get("name", "")) or key.rsplit("/", 1)[-1]
        kind = str(entry.get("kind", "")) or "unknown"
        pkg = InstalledPackage(
            name=name,
            kind=kind,
            version=str(entry.get("version", "")),
            scope=scope,
            env=env,
            installed_at=str(entry.get("installed_at", "")),
            source_commit=entry.get("source_commit"),
            installed_paths=list(entry.get("installed_paths", [])),
        )
        packages[pkg.storage_key] = pkg
    return packages


def load(scope: str, project_root: Path | None = None) -> dict[str, InstalledPackage]:
    """Read the scope's installed records. Returns {storage_key: InstalledPackage}.

    Returns an empty dict if nothing is recorded. For the project scope, falls
    back to the pre-1.0 per-env locations and merges them forward when the
    neutral file does not exist yet (lazy migration; persisted on next save)."""
    if scope == ROOT:
        return _parse_file(installed_root_file(), scope)

    if scope == PROJECT:
        neutral = installed_project_file(project_root)
        if neutral.exists():
            return _parse_file(neutral, scope)
        merged: dict[str, InstalledPackage] = {}
        for env in envs.ENVS:
            legacy = installed_project_file_legacy(env, project_root)
            if legacy == neutral:
                continue
            merged.update(_parse_file(legacy, scope))
        return merged

    raise ValueError(f"invalid scope: {scope!r}. Use 'root' or 'project'.")


def save(packages: dict[str, InstalledPackage], scope: str, project_root: Path | None = None) -> None:
    if scope == ROOT:
        path = installed_root_file()
    elif scope == PROJECT:
        path = installed_project_file(project_root)
    else:
        raise ValueError(f"invalid scope: {scope!r}. Use 'root' or 'project'.")

    path.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {"packages": {}}
    for pkg in packages.values():
        entry: dict = {
            "name": pkg.name,
            "kind": pkg.kind,
            "version": pkg.version,
            "env": pkg.env,
            "installed_at": pkg.installed_at,
            "installed_paths": pkg.installed_paths,
        }
        if pkg.source_commit:
            entry["source_commit"] = pkg.source_commit
        out["packages"][pkg.storage_key] = entry
    with path.open("wb") as f:
        tomli_w.dump(out, f)


def all_installed(project_root: Path | None = None) -> list[InstalledPackage]:
    """List packages installed in both scopes."""
    result = list(load(ROOT).values())
    result.extend(load(PROJECT, project_root).values())
    return result


def find_by_name(name: str, project_root: Path | None = None) -> list[InstalledPackage]:
    """Return all installations of a name (across kinds, envs and scopes)."""
    return [p for p in all_installed(project_root) if p.name == name]
