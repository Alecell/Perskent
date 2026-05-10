"""pskt update <name>."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import typer

from perskent import config, git_ops, installer, ui
from perskent import installed as installed_mod
from perskent import manifest as manifest_mod
from perskent import registry_scan
from perskent.installed import InstalledPackage
from perskent.paths import claude_project_dir, claude_root_dir, workspace_dir


def _dest_root_for(scope: str) -> Path:
    if scope == installed_mod.ROOT:
        return claude_root_dir()
    return claude_project_dir()


def _resolve_install_record(name: str):
    """Retorna (scope, record) do pacote instalado. Erra com mensagem amigável se 0 ou >1."""
    if "/" in name:
        for scope_candidate in installed_mod.SCOPES:
            state = installed_mod.load(scope_candidate)
            if name in state:
                return scope_candidate, state[name]
        ui.die(f"'{name}' não está instalado em nenhum scope.")

    installations = installed_mod.find_by_name(name)
    if not installations:
        ui.die(f"'{name}' não está instalado em nenhum scope.")
    if len(installations) > 1:
        ui.warn(f"'{name}' é ambíguo:")
        for inst in installations:
            ui.console.print(
                f"  [muted]→[/muted] {inst.qualified_name} ({inst.scope}) v{inst.version}"
            )
        ui.die("Use o nome qualificado, ex.: `pskt update agents/<nome>`.")
    inst = installations[0]
    return inst.scope, inst


def run(
    name: str = typer.Argument(
        ...,
        help="Nome do pacote (ou <kind>s/<name> pra desambiguar)",
    ),
) -> None:
    if not config.exists():
        ui.die("perskent não inicializado. Rode `pskt init` primeiro.")

    scope, record = _resolve_install_record(name)
    dest_root = _dest_root_for(scope)

    matches = registry_scan.find(workspace_dir(), record.qualified_name)
    if not matches:
        ui.die(
            f"Pacote '{record.qualified_name}' não está mais no registry. "
            "Rode `pskt sync` pra atualizar, ou `pskt remove` se foi removido."
        )
    pkg = matches[0]
    new_version = pkg.manifest.version

    if new_version == record.version:
        ui.warn(
            f"'{pkg.qualified_name}' já está em v{new_version} (mesma versão do registry)."
        )
        if not ui.ask_confirm("Reinstalar mesmo assim?", default=False):
            ui.info("Cancelado.")
            return

    ui.info(
        f"Atualizando {pkg.qualified_name}: v{record.version} → v{new_version}..."
    )

    new_files = pkg.files_to_install()
    preserve = pkg.manifest.preserve

    skip_in_copy: set[Path] = set()
    for f in new_files:
        if manifest_mod.matches_preserve(f, preserve) and (dest_root / f).exists():
            skip_in_copy.add(f)

    try:
        copied = installer.copy_files(pkg, dest_root, skip=skip_in_copy, overwrite=True)
    except installer.InstallError as e:
        ui.die(f"Falha durante cópia: {e}")

    new_paths_set = {str(f) for f in new_files}
    orphans_to_remove: list[str] = []
    orphans_preserved: list[str] = []
    for p in record.installed_paths:
        if p in new_paths_set:
            continue
        if manifest_mod.matches_preserve(p, preserve) and (dest_root / p).exists():
            orphans_preserved.append(p)
        else:
            orphans_to_remove.append(p)

    if orphans_to_remove:
        installer.remove_paths(orphans_to_remove, dest_root)

    head = git_ops.head_commit(workspace_dir())
    now_iso = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    final_paths = [str(f) for f in new_files] + orphans_preserved

    new_record = InstalledPackage(
        name=pkg.name,
        kind=pkg.kind,
        version=new_version,
        scope=scope,
        installed_at=now_iso,
        source_commit=head,
        installed_paths=final_paths,
    )
    state = installed_mod.load(scope)
    state[pkg.qualified_name] = new_record
    installed_mod.save(state, scope)

    parts = [f"{len(copied)} sobrescrito(s)"]
    if skip_in_copy:
        parts.append(f"{len(skip_in_copy)} preservado(s)")
    if orphans_to_remove:
        parts.append(f"{len(orphans_to_remove)} órfão(s) removido(s)")
    if orphans_preserved:
        parts.append(f"{len(orphans_preserved)} órfão(s) preservado(s)")
    ui.ok("Atualizado: " + ", ".join(parts) + ".")
