"""Parser for a package's manifest.toml.

Schema:
    [package]
    name = "..."        (required)
    version = "..."     (required)
    description = "..." (optional)
    author = "..."      (optional)

    [update]                 (optional)
    preserve = [             (optional)
      "agent-memory/foo/MEMORY.md",   # exact file
      "agent-memory/foo/notes/",      # whole folder (trailing / = recursive)
    ]

Paths in `preserve` are RELATIVE to the .claude/ of the scope where the
package will be installed (i.e. same format as the paths the package
produces). On update, files matching any pattern that already exist in
the destination are left untouched. On first install they are treated
like any other file (created as templates).
"""
from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


class ManifestError(ValueError):
    pass


@dataclass
class Manifest:
    name: str
    version: str
    description: str | None = None
    author: str | None = None
    preserve: list[str] = field(default_factory=list)

    @property
    def display_description(self) -> str:
        return self.description or "[muted](no description)[/muted]"


def load(path: Path) -> Manifest:
    if not path.exists():
        raise ManifestError(f"manifest.toml not found at {path}")
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(f"invalid manifest.toml at {path}: {e}") from e

    pkg = data.get("package")
    if not isinstance(pkg, dict):
        raise ManifestError(f"manifest.toml at {path}: missing [package] section")

    name = pkg.get("name")
    version = pkg.get("version")
    if not isinstance(name, str) or not name.strip():
        raise ManifestError(f"manifest.toml at {path}: package.name missing or invalid")
    if not isinstance(version, str) or not version.strip():
        raise ManifestError(f"manifest.toml at {path}: package.version missing or invalid")

    desc = pkg.get("description")
    author = pkg.get("author")

    update_section = data.get("update", {}) or {}
    if not isinstance(update_section, dict):
        raise ManifestError(f"manifest.toml at {path}: [update] must be a table")
    raw_preserve = update_section.get("preserve", []) or []
    if not isinstance(raw_preserve, list):
        raise ManifestError(
            f"manifest.toml at {path}: update.preserve must be a list of strings"
        )
    preserve: list[str] = []
    for item in raw_preserve:
        if not isinstance(item, str) or not item.strip():
            continue
        preserve.append(item.strip())

    return Manifest(
        name=name.strip(),
        version=version.strip(),
        description=desc.strip() if isinstance(desc, str) and desc.strip() else None,
        author=author.strip() if isinstance(author, str) and author.strip() else None,
        preserve=preserve,
    )


def matches_preserve(relative: str | Path, patterns: Iterable[str]) -> bool:
    """Does the relative path match any preserve pattern?

    Supported formats:
    - Exact file: 'agent-memory/foo/MEMORY.md' — matches only that path
    - Recursive folder: 'agent-memory/foo/' — matches any descendant
    """
    spath = str(relative).replace("\\", "/").lstrip("./")
    for pat in patterns:
        pat_norm = pat.strip().replace("\\", "/").lstrip("./")
        if not pat_norm:
            continue
        if pat_norm.endswith("/"):
            prefix = pat_norm.rstrip("/")
            if spath == prefix or spath.startswith(prefix + "/"):
                return True
        else:
            if spath == pat_norm:
                return True
    return False
