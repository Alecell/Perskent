"""pskt remove [name] [scope].

If `scope` is omitted, prompts for `root` | `project`.
If `name` is omitted, prompts from the packages installed in that scope.
"""
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


def _prompt_installed_package(scope: str, state: dict, verb: str) -> str:
    if not state:
        ui.die(f"No packages installed in {scope}.")
    choice_map = {
        f"{q}  v{r.version}": q
        for q, r in sorted(state.items())
    }
    choice = ui.ask_select(
        f"Which package to {verb} from {scope}?",
        choices=list(choice_map.keys()),
    )
    return choice_map[choice]


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

    state = installed_mod.load(scope)

    if name is None:
        target_qualified = _prompt_installed_package(scope, state, "remove")
        record = state[target_qualified]
    elif "/" in name:
        target_qualified = name
        record = state.get(target_qualified)
        if record is None:
            ui.die(f"'{name}' is not installed in {scope}.")
    else:
        candidates = [(q, r) for q, r in state.items() if r.name == name]
        if not candidates:
            ui.die(f"'{name}' is not installed in {scope}.")
        if len(candidates) > 1:
            ui.warn(f"'{name}' is ambiguous in {scope}:")
            for q, r in candidates:
                ui.console.print(f"  [muted]→[/muted] {q} v{r.version}")
            ui.die("Use the qualified name, e.g. `pskt remove agents/<name> <scope>`.")
        target_qualified, record = candidates[0]

    dest_root = _dest_root_for(scope)

    ui.info(f"Removing {target_qualified} v{record.version} from {dest_root}...")
    installer.remove_paths(record.installed_paths, dest_root)

    del state[target_qualified]
    installed_mod.save(state, scope)

    ui.ok(f"Removed: {len(record.installed_paths)} file(s).")
