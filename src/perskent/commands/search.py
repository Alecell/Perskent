"""pskt search <term> — search by name or description."""
from __future__ import annotations

import typer
from rich.table import Table

from perskent import config, registry_scan, ui
from perskent.paths import workspace_dir


def run(
    term: str = typer.Argument(..., help="Search term (case-insensitive)"),
) -> None:
    if not config.exists():
        ui.die("perskent is not initialized. Run `pskt init` first.")

    needle = term.strip().lower()
    if not needle:
        ui.die("Search term cannot be empty.")

    packages = registry_scan.scan(workspace_dir())
    matches = []
    for pkg in packages:
        haystack = (pkg.name + " " + (pkg.manifest.description or "")).lower()
        if needle in haystack:
            matches.append(pkg)

    if not matches:
        ui.warn(f"No packages found for '{term}'.")
        return

    table = Table(
        title=f"Results for '{term}' ({len(matches)})",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Kind", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Version", no_wrap=True)
    table.add_column("Description", overflow="fold")
    for pkg in matches:
        table.add_row(
            pkg.kind,
            pkg.name,
            pkg.manifest.version,
            pkg.manifest.display_description,
        )
    ui.console.print(table)
