"""pskt show <name> — detalhes de um pacote do registry."""
from __future__ import annotations

import typer

from perskent import config
from perskent import installed as installed_mod
from perskent import registry_scan, ui
from perskent.paths import workspace_dir


def run(
    name: str = typer.Argument(
        ...,
        help="Nome do pacote (ou <kind>s/<name> pra desambiguar, ex.: agents/my-agent)",
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
        ui.warn(f"'{name}' é ambíguo — existe em múltiplos kinds:")
        for m in matches:
            ui.console.print(
                f"  [muted]→[/muted] {m.qualified_name}  [muted]v{m.manifest.version}[/muted]"
            )
        ui.info("Use o nome qualificado, ex.: `pskt show agents/<nome>`.")
        raise typer.Exit(1)

    pkg = matches[0]
    mf = pkg.manifest

    ui.console.print(
        f"[bold info]{pkg.qualified_name}[/bold info] [muted]v{mf.version}[/muted]"
    )
    if mf.description:
        ui.console.print(mf.description)
    if mf.author:
        ui.console.print(f"[muted]autor:[/muted] {mf.author}")
    ui.console.print(f"[muted]fonte:[/muted] {pkg.path}")
    ui.console.print()

    files = pkg.files_to_install()
    if files:
        ui.console.print(
            f"[bold]{len(files)} arquivo(s) a instalar[/bold] "
            f"[muted](relativos ao .claude/ do scope escolhido):[/muted]"
        )
        for f in files:
            ui.console.print(f"  [muted]→[/muted] {f}")
    else:
        ui.warn("Pacote vazio (só tem manifest.toml).")
    ui.console.print()

    installations = installed_mod.find_by_name(pkg.name)
    same_kind = [i for i in installations if i.kind == pkg.kind]
    if same_kind:
        ui.console.print("[bold]Instalado em:[/bold]")
        for inst in same_kind:
            same_version = inst.version == mf.version
            tag = (
                "[ok](igual ao registry)[/ok]"
                if same_version
                else f"[warn](registry: v{mf.version})[/warn]"
            )
            ui.console.print(f"  {inst.scope}: v{inst.version} {tag}")
    else:
        ui.console.print("[muted]Não instalado.[/muted]")
