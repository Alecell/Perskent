"""pskt find — list packages (subcommands: remote, local)."""
from __future__ import annotations

import typer
from rich.table import Table

from perskent import config
from perskent import installed as installed_mod
from perskent import registry_scan, ui
from perskent.paths import dest_project_dir, dest_root_dir, workspace_dir

find_app = typer.Typer(
    name="find",
    help="List packages (remote: registry, local: installed).",
    no_args_is_help=True,
)


@find_app.command(
    "remote",
    help="List packages available in the remote registry (~/.pskt/).",
)
def remote() -> None:
    if not config.exists():
        ui.die("perskent is not initialized. Run `pskt init` first.")

    packages = registry_scan.scan(workspace_dir())
    if not packages:
        ui.warn(f"Registry is empty at {workspace_dir()}.")
        ui.info(
            "Expected layout: ~/.pskt/<agents|skills|commands>/<name>/manifest.toml"
        )
        return

    table = Table(
        title=f"Registry ({len(packages)} package(s))",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Kind", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Version", no_wrap=True)
    table.add_column("Description", overflow="fold")
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
    help="List packages installed in the code-agent's directory for each scope.",
)
def local() -> None:
    cfg = config.load_or_die()

    root_pkgs = installed_mod.load(installed_mod.ROOT)
    project_pkgs = installed_mod.load(installed_mod.PROJECT)

    total = len(root_pkgs) + len(project_pkgs)
    if total == 0:
        ui.info("No packages installed.")
        ui.info("Run `pskt find remote` to see what's available.")
        return

    table = Table(
        title=f"Installed packages ({total})",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Kind", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Version", no_wrap=True)
    table.add_column("Scope", no_wrap=True)
    table.add_column("Path", overflow="fold")
    def _env_label(record_env: str, configured: list[str]) -> str:
        if record_env in configured:
            return f"[muted]({record_env})[/muted]"
        return f"[muted]({record_env})[/muted] [warn](not in config)[/warn]"

    for pkg in sorted(root_pkgs.values(), key=lambda p: (p.env, p.kind, p.name)):
        table.add_row(
            pkg.kind, pkg.name, pkg.version,
            f"[info]root[/info] {_env_label(pkg.env, cfg.code_agents_root)}",
            str(dest_root_dir(pkg.env, pkg.kind)),
        )
    for pkg in sorted(project_pkgs.values(), key=lambda p: (p.env, p.kind, p.name)):
        table.add_row(
            pkg.kind, pkg.name, pkg.version,
            f"[warn]project[/warn] {_env_label(pkg.env, cfg.code_agents_project)}",
            str(dest_project_dir(pkg.env, pkg.kind)),
        )
    ui.console.print(table)
