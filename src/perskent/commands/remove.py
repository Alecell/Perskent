"""pskt remove <name> <scope>."""
from __future__ import annotations

from pathlib import Path

import typer

from perskent import config, installer, ui
from perskent import installed as installed_mod
from perskent.paths import claude_project_dir, claude_root_dir


def _dest_root_for(scope: str) -> Path:
    if scope == installed_mod.ROOT:
        return claude_root_dir()
    return claude_project_dir()


def run(
    name: str = typer.Argument(
        ...,
        help="Nome do pacote (ou <kind>s/<name> pra desambiguar)",
    ),
    scope: str = typer.Argument(..., help="root | project"),
) -> None:
    if not config.exists():
        ui.die("perskent não inicializado. Rode `pskt init` primeiro.")
    if scope not in installed_mod.SCOPES:
        ui.die(f"Scope inválido: {scope!r}. Use 'root' ou 'project'.")

    state = installed_mod.load(scope)

    if "/" in name:
        target_qualified = name
        record = state.get(target_qualified)
        if record is None:
            ui.die(f"'{name}' não está instalado em {scope}.")
    else:
        candidates = [(q, r) for q, r in state.items() if r.name == name]
        if not candidates:
            ui.die(f"'{name}' não está instalado em {scope}.")
        if len(candidates) > 1:
            ui.warn(f"'{name}' é ambíguo em {scope}:")
            for q, r in candidates:
                ui.console.print(f"  [muted]→[/muted] {q} v{r.version}")
            ui.die("Use o nome qualificado, ex.: `pskt remove agents/<nome> <scope>`.")
        target_qualified, record = candidates[0]

    dest_root = _dest_root_for(scope)

    ui.info(f"Removendo {target_qualified} v{record.version} de {dest_root}...")
    installer.remove_paths(record.installed_paths, dest_root)

    del state[target_qualified]
    installed_mod.save(state, scope)

    ui.ok(f"Removido: {len(record.installed_paths)} arquivo(s).")
