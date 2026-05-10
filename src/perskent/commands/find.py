"""pskt find — listar pacotes (subcomandos: remote, local)."""
from __future__ import annotations

import typer
from rich.table import Table

from perskent import config
from perskent import installed as installed_mod
from perskent import registry_scan, ui
from perskent.paths import claude_project_dir, claude_root_dir, workspace_dir

find_app = typer.Typer(
    name="find",
    help="Listar pacotes (remote: registry, local: instalados).",
    no_args_is_help=True,
)


@find_app.command(
    "remote",
    help="Lista pacotes disponíveis no registry remoto (~/.pskt/).",
)
def remote() -> None:
    if not config.exists():
        ui.die("perskent não inicializado. Rode `pskt init` primeiro.")

    packages = registry_scan.scan(workspace_dir())
    if not packages:
        ui.warn(f"Registry vazio em {workspace_dir()}.")
        ui.info(
            "Estrutura esperada: ~/.pskt/<agents|skills|commands>/<nome>/manifest.toml"
        )
        return

    table = Table(
        title=f"Registry ({len(packages)} pacote(s))",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Tipo", no_wrap=True)
    table.add_column("Nome", no_wrap=True)
    table.add_column("Versão", no_wrap=True)
    table.add_column("Descrição", overflow="fold")
    for pkg in packages:
        table.add_row(
            pkg.kind,
            pkg.name,
            pkg.manifest.version,
            pkg.manifest.display_description,
        )
    ui.console.print(table)


@find_app.command(
    "local",
    help="Lista pacotes instalados em ~/.claude/ (root) e ./.claude/ (project).",
)
def local() -> None:
    root_pkgs = installed_mod.load(installed_mod.ROOT)
    project_pkgs = installed_mod.load(installed_mod.PROJECT)

    total = len(root_pkgs) + len(project_pkgs)
    if total == 0:
        ui.info("Nenhum pacote instalado.")
        ui.info("Use `pskt find remote` pra ver o que está disponível.")
        return

    table = Table(
        title=f"Pacotes instalados ({total})",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Tipo", no_wrap=True)
    table.add_column("Nome", no_wrap=True)
    table.add_column("Versão", no_wrap=True)
    table.add_column("Scope", no_wrap=True)
    table.add_column("Local", overflow="fold")
    for pkg in sorted(root_pkgs.values(), key=lambda p: (p.kind, p.name)):
        table.add_row(
            pkg.kind, pkg.name, pkg.version, "[info]root[/info]", str(claude_root_dir())
        )
    for pkg in sorted(project_pkgs.values(), key=lambda p: (p.kind, p.name)):
        table.add_row(
            pkg.kind, pkg.name, pkg.version, "[warn]project[/warn]", str(claude_project_dir())
        )
    ui.console.print(table)
