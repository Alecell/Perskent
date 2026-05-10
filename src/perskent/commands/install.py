"""pskt install <name> [scope] [--force]."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import typer

from perskent import config, git_ops, installer, ui
from perskent import installed as installed_mod
from perskent import registry_scan
from perskent.installed import InstalledPackage
from perskent.paths import claude_project_dir, claude_root_dir, workspace_dir


def _dest_root_for(scope: str) -> Path:
    if scope == installed_mod.ROOT:
        return claude_root_dir()
    return claude_project_dir()


def run(
    name: str = typer.Argument(
        ...,
        help="Nome do pacote (ou <kind>s/<name> pra desambiguar)",
    ),
    scope: str = typer.Argument(
        None,
        help="root | project (omitir = pergunta interativamente)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Sobrescreve arquivos existentes em conflito (atenção: pode apagar trabalho do user)",
    ),
) -> None:
    if not config.exists():
        ui.die("perskent não inicializado. Rode `pskt init` primeiro.")

    matches = registry_scan.find(workspace_dir(), name)
    if not matches:
        ui.die(
            f"Pacote '{name}' não existe no registry. "
            "Rode `pskt find remote` pra listar disponíveis."
        )
    if len(matches) > 1:
        ui.warn(f"'{name}' é ambíguo:")
        for m in matches:
            ui.console.print(f"  [muted]→[/muted] {m.qualified_name} v{m.manifest.version}")
        ui.info("Use o nome qualificado, ex.: `pskt install agents/<nome>`.")
        raise typer.Exit(1)
    pkg = matches[0]

    if scope is None:
        scope = ui.ask_select(
            f"Instalar '{pkg.qualified_name}' onde?",
            choices=[installed_mod.ROOT, installed_mod.PROJECT],
        )
    if scope not in installed_mod.SCOPES:
        ui.die(f"Scope inválido: {scope!r}. Use 'root' ou 'project'.")

    dest_root = _dest_root_for(scope)

    state = installed_mod.load(scope)
    existing = state.get(pkg.qualified_name)
    if existing is not None and not force:
        ui.die(
            f"'{pkg.qualified_name}' já está instalado em {scope} (v{existing.version}). "
            f"Use `pskt update {pkg.qualified_name}` ou `--force` pra reinstalar do zero."
        )

    skip_for_force: set[Path] = set()
    if force and existing is not None:
        skip_for_force = {Path(p) for p in existing.installed_paths}

    conflicts = installer.detect_conflicts(pkg, dest_root, skip=skip_for_force)
    if conflicts and not force:
        ui.error(
            f"Install abortado: {len(conflicts)} arquivo(s) destino já existem em {dest_root}:"
        )
        for c in conflicts:
            ui.console.print(f"  [err]✗[/err] {c.absolute}")
        ui.info("Use --force pra sobrescrever, ou remova manualmente.")
        raise typer.Exit(1)

    ui.info(
        f"Instalando {pkg.qualified_name} v{pkg.manifest.version} em {dest_root}..."
    )
    try:
        copied = installer.copy_files(pkg, dest_root, overwrite=force)
    except installer.InstallError as e:
        ui.die(f"Falha durante cópia: {e}")

    head = git_ops.head_commit(workspace_dir())
    now_iso = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    record = InstalledPackage(
        name=pkg.name,
        kind=pkg.kind,
        version=pkg.manifest.version,
        scope=scope,
        installed_at=now_iso,
        source_commit=head,
        installed_paths=[str(p) for p in copied],
    )
    state[pkg.qualified_name] = record
    installed_mod.save(state, scope)

    ui.ok(f"Instalado: {len(copied)} arquivo(s) em {dest_root}.")
