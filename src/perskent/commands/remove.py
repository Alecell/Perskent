"""pskt remove [name] [scope] [--agent <name>|all].

If `scope` is omitted, prompts for `root` | `project`.
If `name` is omitted, prompts from the packages installed in that scope.
A package may be installed for several code-agents in one scope; `--agent`
picks one (or `all`), otherwise the command prompts when there's more than one.
"""
from __future__ import annotations

from pathlib import Path

import typer

from perskent import agentsel, config, installer, ui
from perskent import installed as installed_mod
from perskent.installed import InstalledPackage
from perskent.paths import dest_project_dir, dest_root_dir


def _dest_root_for(env: str, scope: str, kind: str) -> Path:
    if scope == installed_mod.ROOT:
        return dest_root_dir(env, kind)
    return dest_project_dir(env, kind)


def _prompt_installed_package(scope: str, state: dict) -> str:
    if not state:
        ui.die(f"No packages installed in {scope}.")
    qualifieds = sorted({r.qualified_name for r in state.values()})
    return ui.ask_select(f"Which package to remove from {scope}?", choices=qualifieds)


def _resolve_records(
    name: str, scope: str, state: dict[str, InstalledPackage], agent_opt: str | None
) -> list[InstalledPackage]:
    if "/" in name:
        records = [r for r in state.values() if r.qualified_name == name]
    else:
        records = [r for r in state.values() if r.name == name]

    if not records:
        ui.die(f"'{name}' is not installed in {scope}.")

    quals = {r.qualified_name for r in records}
    if len(quals) > 1:
        ui.warn(f"'{name}' is ambiguous in {scope}:")
        for q in sorted(quals):
            ui.console.print(f"  [muted]→[/muted] {q}")
        ui.die(f"Use the qualified name, e.g. `pskt remove agents/<name> {scope}`.")

    if agent_opt is not None:
        if agent_opt == agentsel.ALL:
            return records
        chosen = [r for r in records if r.env == agent_opt]
        if not chosen:
            ui.die(f"'{name}' is not installed for code-agent '{agent_opt}' in {scope}.")
        return chosen

    if len(records) == 1:
        return records

    choice_map = {f"{r.env}  v{r.version}": r for r in sorted(records, key=lambda r: r.env)}
    choice = ui.ask_select(
        f"'{records[0].qualified_name}' is installed for several code-agents — remove from which?",
        choices=[*choice_map.keys(), agentsel.ALL],
    )
    if choice == agentsel.ALL:
        return records
    return [choice_map[choice]]


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
        help="Code-agent to remove from (or 'all'); omit to prompt when there are several.",
    ),
) -> None:
    cfg = config.load_or_die()

    if scope is None:
        scope = ui.ask_select("Scope?", choices=list(installed_mod.SCOPES))
    if scope not in installed_mod.SCOPES:
        ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")

    state = installed_mod.load(scope)

    if name is None:
        name = _prompt_installed_package(scope, state)

    records = _resolve_records(name, scope, state, agent)
    configured = cfg.agents_for(scope)

    removed_total = 0
    for record in records:
        if record.env not in configured:
            ui.warn(
                f"[{record.env}] not in the {scope} scope's configured code-agents "
                f"({', '.join(configured)}). Removing from its install location anyway."
            )
        dest_root = _dest_root_for(record.env, scope, record.kind)
        ui.info(f"[{record.env}] removing {record.qualified_name} v{record.version} from {dest_root}...")
        installer.remove_paths(record.installed_paths, dest_root)
        del state[record.storage_key]
        removed_total += len(record.installed_paths)

    installed_mod.save(state, scope)
    ui.ok(f"Removed: {removed_total} file(s) across {len(records)} code-agent(s).")
