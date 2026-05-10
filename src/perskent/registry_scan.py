"""Scans the local workspace (~/.pskt/) for packages.

Expected workspace layout:
    ~/.pskt/
    ├── agents/
    │   └── <package>/manifest.toml + mirror structure of .claude/
    ├── skills/
    │   └── <package>/manifest.toml + ...
    └── commands/
        └── <package>/manifest.toml + ...

The parent folder (`agents`, `skills`, `commands`) determines the package
**kind**. Other top-level folders and top-level files (README, .gitignore)
are ignored — so the author can enrich the repo with docs without tripping
up the CLI.

Each package's contents (except `manifest.toml`) are installed via a 1:1
mirror relative to the chosen scope's `.claude/` — implemented in `installer`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from perskent import manifest as manifest_mod
from perskent.manifest import Manifest

# Folders Claude Code recognizes under `.claude/` — matches the registry layout.
KIND_FOLDERS: tuple[str, ...] = ("agents", "skills", "commands")
KIND_SINGULAR: dict[str, str] = {"agents": "agent", "skills": "skill", "commands": "command"}


@dataclass
class Package:
    """A package available in the remote registry (cloned into ~/.pskt/)."""

    manifest: Manifest
    path: Path  # absolute, e.g. ~/.pskt/agents/my-agent/
    kind: str   # "agent" | "skill" | "command"

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def qualified_name(self) -> str:
        """Name qualified by kind, e.g. 'agents/my-agent'.
        Used to disambiguate between packages of different kinds sharing a name."""
        return f"{self.kind}s/{self.name}"

    def files_to_install(self) -> list[Path]:
        """List package files (paths relative to self.path), excluding manifest.toml.

        These paths are also the install destinations RELATIVE to .claude/ —
        the recursive-mirror rule defined for the project.
        """
        result: list[Path] = []
        for entry in self.path.rglob("*"):
            if entry.is_file() and entry.name != "manifest.toml":
                result.append(entry.relative_to(self.path))
        return sorted(result)


def scan(workspace: Path) -> list[Package]:
    """List valid packages in the workspace, sorted by (kind, name)."""
    if not workspace.exists():
        return []

    packages: list[Package] = []
    for kind_folder in KIND_FOLDERS:
        kind_dir = workspace / kind_folder
        if not kind_dir.exists() or not kind_dir.is_dir():
            continue
        kind = KIND_SINGULAR[kind_folder]
        for entry in sorted(kind_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            manifest_path = entry / "manifest.toml"
            if not manifest_path.exists():
                continue
            try:
                mf = manifest_mod.load(manifest_path)
            except manifest_mod.ManifestError:
                continue  # broken manifest: silently ignore
            packages.append(Package(manifest=mf, path=entry, kind=kind))

    packages.sort(key=lambda p: (p.kind, p.name))
    return packages


def find(workspace: Path, query: str) -> list[Package]:
    """Search by `<name>` (unqualified) or `<kind>s/<name>` (qualified).

    Returns a list — caller decides between no match (0), unique (1), or
    ambiguous (2+). A bare name may return multiple results if the same
    name exists in different kinds.
    """
    pkgs = scan(workspace)

    if "/" in query:
        kind_folder, _, name = query.partition("/")
        if kind_folder not in KIND_FOLDERS:
            return []
        kind = KIND_SINGULAR[kind_folder]
        return [p for p in pkgs if p.kind == kind and p.name == name]

    return [p for p in pkgs if p.name == query]
