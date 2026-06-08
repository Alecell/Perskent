"""Opt-in declaration of what `pskt mirror` replicates across code-agents.

Mirroring is **opt-in**: only artifacts listed here participate. Identified by
their kind-qualified name (`<kind>s/<name>`, e.g. `skills/foo`), the same form
the registry and `installed.toml` use.

Locations:
- root scope:    ~/.config/pskt/mirror.toml
- project scope: ./.pskt-mirror.toml  (project root, cross-agent)

Schema:

    [mirror]
    include = [
      "skills/foo",
      "commands/deploy",
      "agents/reviewer",
    ]
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from perskent.installed import PROJECT, ROOT
from perskent.paths import config_dir

_PROJECT_FILE = ".pskt-mirror.toml"

_EXAMPLE = """\
# perskent mirror config — opt-in list of artifacts to replicate across the
# code-agents configured for this scope (`pskt code-agent`).
# Identify each by its kind-qualified name: skills/<name>, agents/<name>,
# commands/<name>.
[mirror]
include = [
  # "skills/my-skill",
  # "commands/deploy",
]
"""


def config_path(scope: str, project_root: Path | None = None) -> Path:
    if scope == ROOT:
        return config_dir() / "mirror.toml"
    if scope == PROJECT:
        return (project_root or Path.cwd()) / _PROJECT_FILE
    raise ValueError(f"invalid scope: {scope!r}. Use 'root' or 'project'.")


def include_list(scope: str, project_root: Path | None = None) -> list[str]:
    """The opt-in qualified names for `scope`. Empty if the file is absent."""
    path = config_path(scope, project_root)
    if not path.exists():
        return []
    with path.open("rb") as f:
        data = tomllib.load(f)
    raw = (data.get("mirror") or {}).get("include") or []
    result: list[str] = []
    for item in raw:
        item = str(item).strip()
        if item and item not in result:
            result.append(item)
    return result


def write_example(scope: str, project_root: Path | None = None) -> Path:
    """Create a commented example config if none exists. Returns the path."""
    path = config_path(scope, project_root)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_EXAMPLE, encoding="utf-8")
    return path
