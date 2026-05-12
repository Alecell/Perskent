"""pskt remove [name] [scope].

If `scope` is omitted, prompts for `root` | `project`.
If `name` is omitted, prompts from the packages installed in that scope.
"""
from __future__ import annotations

from pathlib import Path

import typer

from perskent import config, installer, ui
from perskent import installed as installed_mod
from perskent.paths import dest_project_dir, dest_root_dir


def _dest_root_for(env: str, scope: str, kind: str) -> Path:
    if scope == installed_mod.ROOT:
        return dest_root_dir(env, kind)
    return dest_project_dir(env, kind)


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
    cfg = config.load_or_die()

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

    current_env = cfg.code_agent_root if scope == installed_mod.ROOT else cfg.code_agent_project
    if record.env != current_env:
        ui.warn(
            f"Package was installed for code-agent '{record.env}', but {scope} scope is "
            f"now configured for '{current_env}'. Removing from the original location."
        )
    dest_root = _dest_root_for(record.env, scope, record.kind)

    ui.info(f"Removing {target_qualified} v{record.version} from {dest_root}...")
    installer.remove_paths(record.installed_paths, dest_root)

    del state[target_qualified]
    installed_mod.save(state, scope)

    ui.ok(f"Removed: {len(record.installed_paths)} file(s).")
