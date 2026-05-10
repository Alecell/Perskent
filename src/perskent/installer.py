"""Operações de filesystem pra install/remove/update.

Filosofia (decidida no design da Fase 3):
- **Conflito = arquivo destino que já existe.** Pasta-container existir é OK.
- **Cópia atômica:** detecta conflitos antes de copiar; se há, aborta antes de
  mexer em qualquer coisa.
- **Cleanup pós-remove:** depois de remover arquivos, sobe nas pastas-mãe e
  remove qualquer uma que ficou vazia, até o `dest_root` (exclusive).
- **Preserve em update:** arquivos cujo path bate com `manifest.preserve`
  e já existem no destino não são tocados.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from perskent.registry_scan import Package


class InstallError(RuntimeError):
    pass


@dataclass
class Conflict:
    relative: Path
    absolute: Path

    def __str__(self) -> str:
        return str(self.absolute)


def detect_conflicts(
    pkg: Package,
    dest_root: Path,
    *,
    skip: set[Path] | None = None,
) -> list[Conflict]:
    """Lista conflitos antes de instalar.

    Conflito = ARQUIVO destino do pacote já existe (com qualquer conteúdo).
    Pastas-container existirem não é conflito.

    `skip` (paths relativos): paths que NÃO contam como conflito mesmo se já
    existirem (ex.: re-install com `--force` substituindo paths previamente
    do próprio pacote).
    """
    skip_set = skip or set()
    conflicts: list[Conflict] = []
    for relative in pkg.files_to_install():
        if relative in skip_set:
            continue
        target = dest_root / relative
        if target.exists() and target.is_file():
            conflicts.append(Conflict(relative=relative, absolute=target))
    return conflicts


def copy_files(
    pkg: Package,
    dest_root: Path,
    *,
    skip: set[Path] | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Copia arquivos do pacote pro `dest_root`. Retorna paths relativos copiados.

    `skip`: paths a NÃO copiar (preserve em update).
    `overwrite`: se True, sobrescreve existentes; se False, falha se existir.
    """
    skip_set = skip or set()
    installed: list[Path] = []
    for relative in pkg.files_to_install():
        if relative in skip_set:
            continue
        src = pkg.path / relative
        target = dest_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise InstallError(f"path existente bloqueando cópia: {target}")
        shutil.copy2(src, target)
        installed.append(relative)
    return installed


def remove_paths(
    relative_paths: list[str | Path],
    dest_root: Path,
) -> None:
    """Remove os arquivos listados (paths relativos a dest_root) e limpa
    pastas vazias upstream até `dest_root` (exclusive).

    Idempotente: paths que não existem são ignorados.
    """
    parents: set[Path] = set()
    for rel in relative_paths:
        target = dest_root / rel
        if target.is_file() or target.is_symlink():
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        parents.add(target.parent)

    while parents:
        next_round: set[Path] = set()
        for parent in parents:
            if parent == dest_root:
                continue
            try:
                parent.relative_to(dest_root)
            except ValueError:
                continue  # parent fora do dest_root, ignora
            if not parent.exists():
                continue
            try:
                next(parent.iterdir())
            except StopIteration:
                try:
                    parent.rmdir()
                    next_round.add(parent.parent)
                except OSError:
                    pass
        parents = next_round
