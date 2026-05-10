"""pskt show <name> — details of a registry package."""
from __future__ import annotations

import typer

from perskent import config
from perskent import installed as installed_mod
from perskent import registry_scan, ui
from perskent.paths import workspace_dir


def run(
    name: str = typer.Argument(
        ...,
        help="Package name (or <kind>s/<name> to disambiguate, e.g. agents/my-agent)",
    ),
) -> None:
    if not config.exists():
        ui.die("perskent is not initialized. Run `pskt init` first.")

    matches = registry_scan.find(workspace_dir(), name)
    if not matches:
        ui.die(
            f"Package '{name}' does not exist in the registry. "
            "Run `pskt find remote` to list available packages."
        )
    if len(matches) > 1:
        ui.warn(f"'{name}' is ambiguous — exists in multiple kinds:")
        for m in matches:
            ui.console.print(
                f"  [muted]→[/muted] {m.qualified_name}  [muted]v{m.manifest.version}[/muted]"
            )
        ui.info("Use the qualified name, e.g. `pskt show agents/<name>`.")
        raise typer.Exit(1)

    pkg = matches[0]
    mf = pkg.manifest

    ui.console.print(
        f"[bold info]{pkg.qualified_name}[/bold info] [muted]v{mf.version}[/muted]"
    )
    if mf.description:
        ui.console.print(mf.description)
    if mf.author:
        ui.console.print(f"[muted]author:[/muted] {mf.author}")
    ui.console.print(f"[muted]source:[/muted] {pkg.path}")
    ui.console.print()

    files = pkg.files_to_install()
    if files:
        ui.console.print(
            f"[bold]{len(files)} file(s) to install[/bold] "
            f"[muted](relative to the chosen scope's .claude/):[/muted]"
        )
        for f in files:
            ui.console.print(f"  [muted]→[/muted] {f}")
    else:
        ui.warn("Empty package (only manifest.toml).")
    ui.console.print()

    installations = installed_mod.find_by_name(pkg.name)
    same_kind = [i for i in installations if i.kind == pkg.kind]
    if same_kind:
        ui.console.print("[bold]Installed in:[/bold]")
        for inst in same_kind:
            same_version = inst.version == mf.version
            tag = (
                "[ok](matches registry)[/ok]"
                if same_version
                else f"[warn](registry: v{mf.version})[/warn]"
            )
            ui.console.print(f"  {inst.scope}: v{inst.version} {tag}")
    else:
        ui.console.print("[muted]Not installed.[/muted]")
