"""pskt update [name] [scope] [--agent <name>|all].

If `scope` is omitted, prompts for `root` | `project`.
If `name` is omitted, prompts from the packages installed in that scope.
A package may be installed for several code-agents in one scope; `--agent`
picks one (or `all`), otherwise the command prompts when there's more than one.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import typer

from perskent import agentsel, config, envs, git_ops, installer, ui
from perskent import installed as installed_mod
from perskent import manifest as manifest_mod
from perskent import registry_scan
from perskent.installed import InstalledPackage
from perskent.paths import dest_project_dir, dest_root_dir, workspace_dir


def _dest_root_for(env: str, scope: str, kind: str) -> Path:
    if scope == installed_mod.ROOT:
        return dest_root_dir(env, kind)
    return dest_project_dir(env, kind)


def _prompt_installed_package(scope: str, state: dict) -> str:
    if not state:
        ui.die(f"No packages installed in {scope}.")
    # Collapse the per-env records down to the kind-qualified names on offer.
    qualifieds = sorted({r.qualified_name for r in state.values()})
    return ui.ask_select(f"Which package to update in {scope}?", choices=qualifieds)


def _resolve_records(
    name: str, scope: str, state: dict[str, InstalledPackage], agent_opt: str | None
) -> list[InstalledPackage]:
    """Records (one per code-agent) matching `name` in `scope`, filtered by agent."""
    if "/" in name:
        records = [r for r in state.values() if r.qualified_name == name]
    else:
        records = [r for r in state.values() if r.name == name]

    if not records:
        ui.die(f"'{name}' is not installed in {scope}.")

    # Disambiguate kinds (bare name matching agents/foo and skills/foo).
    quals = {r.qualified_name for r in records}
    if len(quals) > 1:
        ui.warn(f"'{name}' is ambiguous in {scope}:")
        for q in sorted(quals):
            ui.console.print(f"  [muted]→[/muted] {q}")
        ui.die(f"Use the qualified name, e.g. `pskt update agents/<name> {scope}`.")

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
        f"'{records[0].qualified_name}' is installed for several code-agents — update which?",
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
        help="Code-agent to update (or 'all'); omit to prompt when there are several.",
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

    updated_any = False
    for record in records:
        if _update_record(cfg, record, scope, state):
            updated_any = True
    if updated_any:
        installed_mod.save(state, scope)


def _update_record(
    cfg: config.Config,
    record: InstalledPackage,
    scope: str,
    state: dict[str, InstalledPackage],
) -> bool:
    """Update one installed copy. Mutates `state`. Returns True if it changed."""
    if record.env not in cfg.agents_for(scope):
        ui.warn(
            f"[{record.env}] not in the {scope} scope's configured code-agents "
            f"({', '.join(cfg.agents_for(scope))}). Updating in place anyway."
        )

    if not envs.supports_kind(record.env, record.kind):
        ui.die(
            f"Code-agent '{record.env}' no longer supports packages of kind "
            f"'{record.kind}'. Run `pskt remove {record.qualified_name} {scope} "
            f"--agent {record.env}` to clean up."
        )

    dest_root = _dest_root_for(record.env, scope, record.kind)

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
            f"[{record.env}] '{pkg.qualified_name}' is already at v{new_version}."
        )
        if not ui.ask_confirm("Reinstall anyway?", default=False):
            return False

    ui.info(
        f"[{record.env}] updating {pkg.qualified_name}: v{record.version} → v{new_version}..."
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
        ui.die(f"[{record.env}] copy failed: {e}")

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

    state[record.storage_key] = InstalledPackage(
        name=pkg.name,
        kind=pkg.kind,
        version=new_version,
        scope=scope,
        env=record.env,
        installed_at=now_iso,
        source_commit=head,
        installed_paths=final_paths,
    )

    parts = [f"{len(copied)} overwritten"]
    if skip_in_copy:
        parts.append(f"{len(skip_in_copy)} preserved")
    if orphans_to_remove:
        parts.append(f"{len(orphans_to_remove)} orphan(s) removed")
    if orphans_preserved:
        parts.append(f"{len(orphans_preserved)} orphan(s) preserved")
    ui.ok(f"[{record.env}] updated: " + ", ".join(parts) + ".")
    return True
