"""Varre o workspace local (~/.pskt/) atrás de pacotes.

Estrutura esperada do workspace:
    ~/.pskt/
    ├── agents/
    │   └── <pacote>/manifest.toml + estrutura mirror do .claude/
    ├── skills/
    │   └── <pacote>/manifest.toml + ...
    └── commands/
        └── <pacote>/manifest.toml + ...

A pasta-mãe (`agents`, `skills`, `commands`) determina o **kind** do pacote.
Pastas top-level fora desse conjunto e arquivos top-level (README, .gitignore)
são ignorados — permite que o autor enriqueça o repo com docs sem o CLI tropeçar.

Conteúdo de cada pacote (exceto `manifest.toml`) é instalado por mirror 1:1
relativo ao `.claude/` do scope escolhido — definido em `installer` na Fase 3.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from perskent import manifest as manifest_mod
from perskent.manifest import Manifest

# Pastas que o Claude Code reconhece em `.claude/` — bate com a estrutura do registry.
KIND_FOLDERS: tuple[str, ...] = ("agents", "skills", "commands")
KIND_SINGULAR: dict[str, str] = {"agents": "agent", "skills": "skill", "commands": "command"}


@dataclass
class Package:
    """Pacote disponível no registry remoto (clonado em ~/.pskt/)."""

    manifest: Manifest
    path: Path  # absoluto, ex.: ~/.pskt/agents/my-agent/
    kind: str   # "agent" | "skill" | "command"

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def qualified_name(self) -> str:
        """Nome qualificado pelo kind, ex.: 'agents/my-agent'.
        Usar quando precisar desambiguar entre pacotes de kinds diferentes com mesmo nome."""
        return f"{self.kind}s/{self.name}"

    def files_to_install(self) -> list[Path]:
        """Lista arquivos do pacote (paths relativos a self.path), exceto manifest.toml.

        Esses paths são ao mesmo tempo o destino RELATIVO ao .claude/ — regra de
        instalação por mirror recursivo definida pelo projeto.
        """
        result: list[Path] = []
        for entry in self.path.rglob("*"):
            if entry.is_file() and entry.name != "manifest.toml":
                result.append(entry.relative_to(self.path))
        return sorted(result)


def scan(workspace: Path) -> list[Package]:
    """Lista pacotes válidos no workspace, ordenados por (kind, name)."""
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
                continue  # manifest quebrado: ignora silenciosamente
            packages.append(Package(manifest=mf, path=entry, kind=kind))

    packages.sort(key=lambda p: (p.kind, p.name))
    return packages


def find(workspace: Path, query: str) -> list[Package]:
    """Busca pacote por `<name>` (sem qualificação) ou `<kind>s/<name>` (qualificado).

    Retorna lista — caller decide entre nenhum (0), match único (1), ou ambíguo (2+).
    Bare name pode retornar múltiplos se o mesmo nome existir em kinds diferentes.
    """
    pkgs = scan(workspace)

    if "/" in query:
        kind_folder, _, name = query.partition("/")
        if kind_folder not in KIND_FOLDERS:
            return []
        kind = KIND_SINGULAR[kind_folder]
        return [p for p in pkgs if p.kind == kind and p.name == name]

    return [p for p in pkgs if p.name == query]
