"""pskt update [name] [scope].

If `scope` is omitted, prompts for `root` | `project`.
If `name` is omitted, prompts from the packages installed in that scope.
"""
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


def _prompt_installed_package(scope: str, state: dict) -> str:
    if not state:
        ui.die(f"No packages installed in {scope}.")
    choice_map = {
        f"{q}  v{r.version}": q
        for q, r in sorted(state.items())
    }
    choice = ui.ask_select(
        f"Which package to update in {scope}?",
        choices=list(choice_map.keys()),
    )
    return choice_map[choice]


def _resolve_install_record(name: str, scope: str):
    """Returns the InstalledPackage in the given scope. Errors clearly on 0 or >1 matches."""
    state = installed_mod.load(scope)

    if "/" in name:
        record = state.get(name)
        if record is None:
            ui.die(f"'{name}' is not installed in {scope}.")
        return record

    candidates = [(q, r) for q, r in state.items() if r.name == name]
    if not candidates:
        ui.die(f"'{name}' is not installed in {scope}.")
    if len(candidates) > 1:
        ui.warn(f"'{name}' is ambiguous in {scope}:")
        for q, r in candidates:
            ui.console.print(f"  [muted]→[/muted] {q} v{r.version}")
        ui.die("Use the qualified name, e.g. `pskt update agents/<name> <scope>`.")
    return candidates[0][1]


def run(
    name: str = typer.Argument(
        None,
        help="Package name (or <kind>s/<name>); omit for an interactive prompt.",
    ),
    scope: str = typer.Argument(
        None,
        help="root | project (omit for an interactive prompt)",
    ),
) -> None:
    if not config.exists():
        ui.die("perskent is not initialized. Run `pskt init` first.")

    if scope is None:
        scope = ui.ask_select("Scope?", choices=list(installed_mod.SCOPES))
    if scope not in installed_mod.SCOPES:
        ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")

    if name is None:
        state = installed_mod.load(scope)
        name = _prompt_installed_package(scope, state)

    record = _resolve_install_record(name, scope)
    dest_root = _dest_root_for(scope)

    matches = registry_scan.find(workspace_dir(), record.qualified_name)
    if not matches:
        ui.die(
            f"Package '{record.qualified_name}' is no longer in the registry. "
            "Run `pskt sync` to refresh, or `pskt remove` if it was deleted."
        )
    pkg = matches[0]
    new_version = pkg.manifest.version

    if new_version == record.version:
        ui.warn(
            f"'{pkg.qualified_name}' is already at v{new_version} (matches registry)."
        )
        if not ui.ask_confirm("Reinstall anyway?", default=False):
            ui.info("Cancelled.")
            return

    ui.info(
        f"Updating {pkg.qualified_name}: v{record.version} → v{new_version}..."
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
        ui.die(f"Copy failed: {e}")

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

    parts = [f"{len(copied)} overwritten"]
    if skip_in_copy:
        parts.append(f"{len(skip_in_copy)} preserved")
    if orphans_to_remove:
        parts.append(f"{len(orphans_to_remove)} orphan(s) removed")
    if orphans_preserved:
        parts.append(f"{len(orphans_preserved)} orphan(s) preserved")
    ui.ok("Updated: " + ", ".join(parts) + ".")
