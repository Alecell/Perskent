"""Parser do manifest.toml de um pacote.

Schema mínimo:
    [package]
    name = "..."        (obrigatório)
    version = "..."     (obrigatório)
    description = "..." (opcional)
    author = "..."      (opcional)
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    pass


@dataclass
class Manifest:
    name: str
    version: str
    description: str | None = None
    author: str | None = None

    @property
    def display_description(self) -> str:
        return self.description or "[muted](sem descrição)[/muted]"


def load(path: Path) -> Manifest:
    if not path.exists():
        raise ManifestError(f"manifest.toml não encontrado em {path}")
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(f"manifest.toml inválido em {path}: {e}") from e

    pkg = data.get("package")
    if not isinstance(pkg, dict):
        raise ManifestError(f"manifest.toml em {path}: faltando seção [package]")

    name = pkg.get("name")
    version = pkg.get("version")
    if not isinstance(name, str) or not name.strip():
        raise ManifestError(f"manifest.toml em {path}: package.name ausente ou inválido")
    if not isinstance(version, str) or not version.strip():
        raise ManifestError(f"manifest.toml em {path}: package.version ausente ou inválido")

    desc = pkg.get("description")
    author = pkg.get("author")
    return Manifest(
        name=name.strip(),
        version=version.strip(),
        description=desc.strip() if isinstance(desc, str) and desc.strip() else None,
        author=author.strip() if isinstance(author, str) and author.strip() else None,
    )
