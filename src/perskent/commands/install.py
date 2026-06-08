"""pskt install [name] [scope] [--force].

If `name` is omitted, prompts interactively from the list of registry packages.
If `scope` is omitted, prompts for `root` | `project`.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import typer

from perskent import agentsel, config, envs, git_ops, installer, ui
from perskent import installed as installed_mod
from perskent import registry_scan
from perskent.installed import InstalledPackage
from perskent.paths import dest_project_dir, dest_root_dir, workspace_dir


def _dest_root_for(env: str, scope: str, kind: str) -> Path:
    if scope == installed_mod.ROOT:
        return dest_root_dir(env, kind)
    return dest_project_dir(env, kind)


def _prompt_registry_package() -> str:
    packages = registry_scan.scan(workspace_dir())
    if not packages:
        ui.die(
            f"Registry is empty at {workspace_dir()}. "
            "Run `pskt sync` or `pskt find remote` first."
        )
    labels = [p.qualified_name for p in packages]
    return ui.ask_select("Which package to install?", choices=labels)


def run(
    name: str = typer.Argument(
        None,
        help="Package name (or <kind>s/<name>); omit for an interactive prompt.",
    ),
    scope: str = typer.Argument(
        None,
        help="root | project (omit for an interactive prompt)",
    ),
    agent: str = typer.Option(
        None,
        "--agent",
        "-a",
        help="Code-agent to install into (or 'all'); omit to prompt if the scope has several.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite conflicting existing files (warning: may erase user work)",
    ),
) -> None:
    cfg = config.load_or_die()

    if name is None:
        name = _prompt_registry_package()

    matches = registry_scan.find(workspace_dir(), name)
    if not matches:
        ui.die(
            f"Package '{name}' does not exist in the registry. "
            "Run `pskt find remote` to list available packages."
        )
    if len(matches) > 1:
        ui.warn(f"'{name}' is ambiguous:")
        for m in matches:
            ui.console.print(f"  [muted]→[/muted] {m.qualified_name} v{m.manifest.version}")
        ui.info("Use the qualified name, e.g. `pskt install agents/<name>`.")
        raise typer.Exit(1)
    pkg = matches[0]

    if scope is None:
        scope = ui.ask_select(
            f"Install '{pkg.qualified_name}' where?",
            choices=[installed_mod.ROOT, installed_mod.PROJECT],
        )
    if scope not in installed_mod.SCOPES:
        ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")

    targets = agentsel.select_targets(cfg, scope, agent, verb="install into")

    # Filter to agents that accept this kind as files; warn+skip the rest.
    eligible = [e for e in targets if envs.supports_kind(e, pkg.kind)]
    for e in targets:
        if e not in eligible:
            ui.warn(
                f"Code-agent '{e}' does not accept packages of kind '{pkg.kind}' "
                f"as standalone files — skipped."
            )
    if not eligible:
        ui.die(
            f"None of the targeted code-agents accept kind '{pkg.kind}' as files."
        )

    state = installed_mod.load(scope)
    installed_envs: list[str] = []
    for env in eligible:
        if not _install_one(pkg, scope, env, state, force):
            continue
        installed_envs.append(env)

    if installed_envs:
        installed_mod.save(state, scope)
        ui.ok(
            f"Installed {pkg.qualified_name} v{pkg.manifest.version} "
            f"in {scope} for: {', '.join(installed_envs)}."
        )


def _install_one(
    pkg: registry_scan.Package,
    scope: str,
    env: str,
    state: dict[str, InstalledPackage],
    force: bool,
) -> bool:
    """Install `pkg` for one code-agent. Mutates `state`. Returns True on success,
    False if it was skipped (already installed / conflict) without --force."""
    key = installed_mod.storage_key(env, pkg.qualified_name)
    dest_root = _dest_root_for(env, scope, pkg.kind)
    existing = state.get(key)
    if existing is not None and not force:
        ui.warn(
            f"[{env}] '{pkg.qualified_name}' is already installed (v{existing.version}). "
            f"Use `pskt update {pkg.qualified_name} {scope} --agent {env}` or `--force`."
        )
        return False

    skip_for_force: set[Path] = set()
    if force and existing is not None:
        skip_for_force = {Path(p) for p in existing.installed_paths}

    conflicts = installer.detect_conflicts(pkg, dest_root, skip=skip_for_force)
    if conflicts and not force:
        ui.error(
            f"[{env}] aborted: {len(conflicts)} destination file(s) already exist at {dest_root}:"
        )
        for c in conflicts:
            ui.console.print(f"  [err]✗[/err] {c.absolute}")
        ui.info("Use --force to overwrite, or remove them manually.")
        return False

    ui.info(f"[{env}] installing into {dest_root}...")
    try:
        copied = installer.copy_files(pkg, dest_root, overwrite=force)
    except installer.InstallError as e:
        ui.die(f"[{env}] copy failed: {e}")

    head = git_ops.head_commit(workspace_dir())
    now_iso = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    state[key] = InstalledPackage(
        name=pkg.name,
        kind=pkg.kind,
        version=pkg.manifest.version,
        scope=scope,
        env=env,
        installed_at=now_iso,
        source_commit=head,
        installed_paths=[str(p) for p in copied],
    )
    return True
