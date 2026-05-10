"""pskt search <termo> — busca em nome/descrição."""
from __future__ import annotations

import typer
from rich.table import Table

from perskent import config, registry_scan, ui
from perskent.paths import workspace_dir


def run(
    term: str = typer.Argument(..., help="Termo de busca (case-insensitive)"),
) -> None:
    if not config.exists():
        ui.die("perskent não inicializado. Rode `pskt init` primeiro.")

    needle = term.strip().lower()
    if not needle:
        ui.die("Termo de busca não pode ser vazio.")

    packages = registry_scan.scan(workspace_dir())
    matches = []
    for pkg in packages:
        haystack = (pkg.name + " " + (pkg.manifest.description or "")).lower()
        if needle in haystack:
            matches.append(pkg)

    if not matches:
        ui.warn(f"Nenhum pacote encontrado pra '{term}'.")
        return

    table = Table(
        title=f"Resultados pra '{term}' ({len(matches)})",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Tipo", no_wrap=True)
    table.add_column("Nome", no_wrap=True)
    table.add_column("Versão", no_wrap=True)
    table.add_column("Descrição", overflow="fold")
    for pkg in matches:
        table.add_row(
            pkg.kind,
            pkg.name,
            pkg.manifest.version,
            pkg.manifest.display_description,
        )
    ui.console.print(table)
