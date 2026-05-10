"""Parser do manifest.toml de um pacote.

Schema:
    [package]
    name = "..."        (obrigatório)
    version = "..."     (obrigatório)
    description = "..." (opcional)
    author = "..."      (opcional)

    [update]                 (opcional)
    preserve = [             (opcional)
      "agent-memory/foo/MEMORY.md",   # arquivo exato
      "agent-memory/foo/notes/",      # pasta inteira (terminada em / = recursivo)
    ]

Paths em `preserve` são RELATIVOS ao .claude/ do scope onde o pacote será
instalado (ou seja: mesmo formato dos paths que o pacote produz). Em update,
arquivos que batem com algum pattern e já existem no destino não são tocados.
Em install (primeira vez), são tratados como qualquer outro arquivo (criados
como template).
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

    update_section = data.get("update", {}) or {}
    if not isinstance(update_section, dict):
        raise ManifestError(f"manifest.toml em {path}: [update] deve ser uma tabela")
    raw_preserve = update_section.get("preserve", []) or []
    if not isinstance(raw_preserve, list):
        raise ManifestError(
            f"manifest.toml em {path}: update.preserve deve ser uma lista de strings"
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
    """Path relativo bate com algum pattern de preserve?

    Formatos suportados:
    - Arquivo exato: 'agent-memory/foo/MEMORY.md' — bate só nesse path
    - Pasta recursiva: 'agent-memory/foo/' — bate em qualquer descendente
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
