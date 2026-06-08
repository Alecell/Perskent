"""pskt add [name] [scope].

Reverse direction of `install`: take an artifact that already lives under
the code-agent's directory (e.g. `~/.claude/agents/foo/`) and bring it
into the registry workspace at `~/.pskt/<kind>s/<name>/`. A manifest is
generated interactively (same flow as `pskt push` on a brand-new package),
and the artifact is registered as installed in the chosen scope so future
`update`/`remove`/`status` operations target the right place.

`name` may be qualified (`agents/foo`) or bare (`foo`). On ambiguity (the
bare name matches artifacts in multiple kinds), the qualified form is
required.
"""
from __future__ import annotations

import datetime as dt
import shutil

import typer

from perskent import agentsel, artifacts, config, envs, git_ops, ui
from perskent import installed as installed_mod
from perskent import manifest as manifest_mod
from perskent.commands.push import _generate_manifest
from perskent.installed import InstalledPackage
from perskent.paths import workspace_dir
from perskent.registry_scan import KIND_FOLDERS, KIND_SINGULAR


def _resolve_qualified(env: str, scope: str, name: str) -> tuple[str, str]:
    """Returns (kind_folder, art_name). Validates that the source exists.

    - Qualified input (`agents/foo`): kind is fixed; source must exist.
    - Bare input (`foo`): scans every kind supported by the env. 0 → die,
      1 → ok, >1 → die asking for qualification.
    """
    if "/" in name:
        kind_folder, _, art_name = name.partition("/")
        if kind_folder not in KIND_FOLDERS:
            ui.die(
                f"Invalid kind: {kind_folder!r}. Use {' | '.join(KIND_FOLDERS)}."
            )
        kind = KIND_SINGULAR[kind_folder]
        if not envs.supports_kind(env, kind):
            ui.die(f"Code-agent '{env}' does not support packages of kind '{kind}'.")
        env_base = artifacts.env_base_for(env, scope, kind)
        if artifacts.find_source(env_base, kind_folder, art_name) is None:
            ui.die(
                f"Artifact '{kind_folder}/{art_name}' not found under {env_base}/{kind_folder}/."
            )
        return kind_folder, art_name

    matches: list[str] = []
    for kind_folder in KIND_FOLDERS:
        kind = KIND_SINGULAR[kind_folder]
        if not envs.supports_kind(env, kind):
            continue
        env_base = artifacts.env_base_for(env, scope, kind)
        if artifacts.find_source(env_base, kind_folder, name) is not None:
            matches.append(kind_folder)
    if not matches:
        ui.die(
            f"Artifact '{name}' not found under any kind folder for code-agent "
            f"'{env}' in scope '{scope}'."
        )
    if len(matches) > 1:
        ui.warn(f"'{name}' is ambiguous in {scope}:")
        for kf in matches:
            ui.console.print(f"  [muted]→[/muted] {kf}/{name}")
        ui.die("Use the qualified name, e.g. `pskt add agents/<name> <scope>`.")
    return matches[0], name


def _prompt_addable(env: str, scope: str, installed_qualified: set[str]) -> str:
    """List artifacts under the env-base that aren't yet registered in this
    scope and aren't already mirrored in the workspace. Returns the qualified
    name picked by the user."""
    workspace = workspace_dir()
    candidates: list[str] = []
    for kind_folder in KIND_FOLDERS:
        kind = KIND_SINGULAR[kind_folder]
        if not envs.supports_kind(env, kind):
            continue
        env_base = artifacts.env_base_for(env, scope, kind)
        kind_dir = env_base / kind_folder
        if not kind_dir.is_dir():
            continue
        for entry in sorted(kind_dir.iterdir()):
            if entry.name.startswith(".") or entry.name == ".pskt-installed.toml":
                continue
            if entry.is_dir():
                art_name = entry.name
            elif entry.is_file() and entry.suffix == ".md":
                art_name = entry.stem
            else:
                continue
            qualified = f"{kind_folder}/{art_name}"
            if qualified in installed_qualified:
                continue
            if (workspace / kind_folder / art_name).exists():
                continue
            candidates.append(qualified)
    if not candidates:
        ui.die(
            f"No addable artifacts in {scope} scope for code-agent '{env}'. "
            "Every artifact in the env-base is already registered or already in the workspace."
        )
    return ui.ask_select("Which artifact to add?", choices=candidates)


def run(
    name: str = typer.Argument(
        None,
        help="Artifact name (or <kind>s/<name>); omit for an interactive prompt.",
    ),
    scope: str = typer.Argument(
        None,
        help="root | project (omit for an interactive prompt)",
    ),
    agent: str = typer.Option(
        None,
        "--agent",
        "-a",
        help="Code-agent to import the artifact from; omit to prompt when the scope has several.",
    ),
) -> None:
    cfg = config.load_or_die()

    if scope is None:
        scope = ui.ask_select("Scope?", choices=list(installed_mod.SCOPES))
    if scope not in installed_mod.SCOPES:
        ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")

    env = agentsel.select_targets(cfg, scope, agent, verb="import from", allow_all=False)[0]
    state = installed_mod.load(scope)

    # Names already registered for this env (so we don't offer to re-add them).
    installed_qualified = {r.qualified_name for r in state.values() if r.env == env}

    if name is None:
        name = _prompt_addable(env, scope, installed_qualified)

    kind_folder, art_name = _resolve_qualified(env, scope, name)
    kind = KIND_SINGULAR[kind_folder]
    qualified = f"{kind_folder}/{art_name}"

    env_base = artifacts.env_base_for(env, scope, kind)
    source = artifacts.find_source(env_base, kind_folder, art_name)
    if source is None:
        ui.die(f"Source not found under {env_base}/{kind_folder}/.")

    files = artifacts.files_relative_to_env_base(source, env_base)
    if not files:
        ui.die(f"Source is empty: {source}")

    workspace = workspace_dir()
    dest = workspace / kind_folder / art_name
    if dest.exists():
        ui.die(
            f"'{qualified}' already exists in the workspace at {dest}. "
            "Use `pskt push` if you want to publish local changes."
        )
    key = installed_mod.storage_key(env, qualified)
    if key in state:
        ui.die(
            f"'{qualified}' is already registered as installed for '{env}' in {scope}. "
            "Use `pskt push` to publish, or `pskt remove` first if you want to re-add."
        )

    ui.info(f"Copying {len(files)} file(s) from {source} → {dest}/")
    dest.mkdir(parents=True, exist_ok=True)
    try:
        for relative in files:
            src = env_base / relative
            tgt = dest / relative
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tgt)
    except OSError as e:
        shutil.rmtree(dest, ignore_errors=True)
        ui.die(f"Copy failed: {e}")
    ui.ok(f"Copied {len(files)} file(s) into {dest}.")

    manifest_path = dest / "manifest.toml"
    if not manifest_path.exists():
        _generate_manifest(dest, art_name, kind)
    try:
        manifest = manifest_mod.load(manifest_path)
    except manifest_mod.ManifestError as e:
        ui.die(f"final manifest is invalid: {e}")

    head = git_ops.head_commit(workspace)
    now_iso = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = InstalledPackage(
        name=art_name,
        kind=kind,
        version=manifest.version,
        scope=scope,
        env=env,
        installed_at=now_iso,
        source_commit=head,
        installed_paths=[str(p) for p in files],
    )
    state[key] = record
    installed_mod.save(state, scope)

    ui.ok(
        f"Added {qualified} v{manifest.version} from {scope}. "
        f"Run `pskt push {qualified}` to publish."
    )
