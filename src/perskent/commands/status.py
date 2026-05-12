"""pskt status — consolidated view of workspace, registry, and installations.

Shows in one screen:
- Remote registry URL and reachability state from the local clone.
- Workspace clean/dirty state and unpushed commits.
- Package count, broken down by kind.
- Installations across both scopes, flagging outdated and orphaned ones.
"""
from __future__ import annotations

from perskent import config, git_ops, ui
from perskent import installed as installed_mod
from perskent import registry_scan
from perskent.paths import workspace_dir


def run() -> None:
    cfg = config.load_or_die()

    ws = workspace_dir()
    if not ws.exists() or not git_ops.is_git_repo(ws):
        ui.die(f"Workspace missing at {ws}. Run `pskt init --force` to reconfigure.")

    # ─── Registry / Workspace ────────────────────────────────────────────
    ui.console.print(f"[bold]Registry[/bold]  [muted]{cfg.registry_url}[/muted]")

    head = git_ops.head_commit(ws)
    if head:
        ui.console.print(f"  HEAD:           [muted]{head[:7]}[/muted]")
    else:
        ui.console.print("  HEAD:           [muted](no commits yet)[/muted]")

    try:
        changes = git_ops.status_porcelain(ws)
        if changes:
            ui.console.print(
                f"  Local changes:  [warn]{len(changes)} file(s) modified or untracked[/warn]"
            )
        else:
            ui.console.print("  Local changes:  [ok]clean[/ok]")
    except git_ops.GitError:
        ui.console.print("  Local changes:  [err]error reading status[/err]")

    ahead = git_ops.unpushed_commits(ws)
    if ahead > 0:
        ui.console.print(
            f"  Unpushed:       [warn]{ahead} commit(s) ahead of origin/main[/warn]"
        )
    else:
        ui.console.print("  Unpushed:       [ok]in sync with remote[/ok]")

    ui.console.print()

    # ─── Registry packages ───────────────────────────────────────────────
    pkgs = registry_scan.scan(ws)
    if pkgs:
        by_kind: dict[str, int] = {}
        for p in pkgs:
            by_kind[p.kind] = by_kind.get(p.kind, 0) + 1
        breakdown = ", ".join(
            f"{count} {kind}{'s' if count != 1 else ''}"
            for kind, count in sorted(by_kind.items())
        )
        ui.console.print(
            f"[bold]Registry packages[/bold]  {len(pkgs)} [muted]({breakdown})[/muted]"
        )
    else:
        ui.console.print("[bold]Registry packages[/bold]  [muted](none)[/muted]")

    ui.console.print()

    # ─── Installations ───────────────────────────────────────────────────
    root_pkgs = installed_mod.load(installed_mod.ROOT)
    project_pkgs = installed_mod.load(installed_mod.PROJECT)
    total_installed = len(root_pkgs) + len(project_pkgs)

    if total_installed == 0:
        ui.console.print("[bold]Installations[/bold]  [muted](none)[/muted]")
        return

    ui.console.print(
        f"[bold]Installations[/bold]  {total_installed} "
        f"[muted](root: {len(root_pkgs)}, project: {len(project_pkgs)})[/muted]"
    )

    reg_by_qualified = {p.qualified_name: p for p in pkgs}
    outdated: list[tuple[str, str, str, str]] = []
    orphaned: list[tuple[str, str, str]] = []

    for inst in [*root_pkgs.values(), *project_pkgs.values()]:
        reg_pkg = reg_by_qualified.get(inst.qualified_name)
        if reg_pkg is None:
            orphaned.append((inst.qualified_name, inst.scope, inst.version))
        elif reg_pkg.manifest.version != inst.version:
            outdated.append(
                (inst.qualified_name, inst.scope, inst.version, reg_pkg.manifest.version)
            )

    if outdated:
        ui.console.print(f"  [warn]Outdated ({len(outdated)}):[/warn]")
        for qual, scope, inst_v, reg_v in outdated:
            ui.console.print(
                f"    {qual} [muted]({scope})[/muted]  "
                f"[warn]v{inst_v}[/warn] → [ok]v{reg_v}[/ok]  "
                f"[muted](run `pskt update {qual} {scope}`)[/muted]"
            )

    if orphaned:
        ui.console.print(
            f"  [warn]Orphaned ({len(orphaned)}):[/warn] "
            f"[muted](installed but no longer in the registry)[/muted]"
        )
        for qual, scope, inst_v in orphaned:
            ui.console.print(
                f"    {qual} [muted]({scope})[/muted] v{inst_v}  "
                f"[muted](run `pskt remove {qual} {scope}` to clean up)[/muted]"
            )

    if not outdated and not orphaned:
        ui.console.print("  [ok]All up to date[/ok]")
