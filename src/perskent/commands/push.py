"""pskt push [name] [scope] — publish a package to the remote registry.

Two modes, picked by the arguments:

1. Workspace mode (`pskt push`, `pskt push <name>`): publish a package that
   was edited directly in the workspace (~/.pskt/). Default behaviour.

2. Scope mode (`pskt push root|project`, `pskt push <name> <scope>`): publish a
   package that was edited in place inside the code-agent's directory (e.g. a
   skill you refined while using it). The chosen installation's files are first
   mirrored back into the workspace, then the normal publish flow runs.
   Files matching the manifest's `[update].preserve` (user runtime data such as
   memory) are NOT copied back — only the package template is published.

Publish flow (shared by both modes):
1. Resolve the package (with kind disambiguation). If `name` is omitted,
   prompts interactively.
2. If the folder has no `manifest.toml`, generates one interactively
   (description, author, initial version 0.1.0). Otherwise, shows git
   changes for the package and prompts for a bump (patch/minor/major/no bump).
3. Updates `version` in the manifest in place via regex (preserves comments).
4. git add `<kind>s/<name>/` + git commit + git push (askpass HTTPS).
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path

import typer

from perskent import artifacts, auth, config, envs, git_ops, registry_scan, ui
from perskent import installed as installed_mod
from perskent import manifest as manifest_mod
from perskent.installed import InstalledPackage
from perskent.paths import workspace_dir
from perskent.registry_scan import KIND_FOLDERS, KIND_SINGULAR

# Reverse of registry_scan.KIND_SINGULAR: "skill" -> "skills".
_KIND_FOLDER: dict[str, str] = {v: k for k, v in KIND_SINGULAR.items()}


def _resolve_package_dir(query: str) -> tuple[Path, str, str]:
    """Resolve `<name>` or `<kind>s/<name>` into (path, kind_singular, name).

    Accepts an existing folder without a manifest (so one can be created on the fly).
    """
    ws = workspace_dir()

    if "/" in query:
        kind_folder, _, name = query.partition("/")
        if kind_folder not in KIND_FOLDERS:
            ui.die(
                f"Invalid kind: {kind_folder!r}. Use {' | '.join(KIND_FOLDERS)}."
            )
        pkg_dir = ws / kind_folder / name
        if not pkg_dir.is_dir():
            ui.die(
                f"Folder '{pkg_dir}' does not exist. Create the package first:\n"
                f"  mkdir -p {pkg_dir}"
            )
        return pkg_dir, KIND_SINGULAR[kind_folder], name

    matches: list[tuple[Path, str]] = []
    for kind_folder in KIND_FOLDERS:
        candidate = ws / kind_folder / query
        if candidate.is_dir():
            matches.append((candidate, KIND_SINGULAR[kind_folder]))

    if not matches:
        ui.die(
            f"Package '{query}' does not exist in the workspace. "
            "Create ~/.pskt/<agents|skills|commands>/<name>/ first."
        )
    if len(matches) > 1:
        ui.warn(f"'{query}' is ambiguous — exists in multiple kinds:")
        for path, kind in matches:
            ui.console.print(f"  [muted]→[/muted] {kind}s/{query}")
        ui.die("Use the qualified name, e.g. `pskt push agents/<name>`.")

    pkg_dir, kind = matches[0]
    return pkg_dir, kind, query


def _bump(version: str, level: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"non-semver version: {version!r}")
    try:
        major, minor, patch = (int(p) for p in parts)
    except ValueError as e:
        raise ValueError(f"non-semver version: {version!r}") from e
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "major":
        return f"{major + 1}.0.0"
    raise ValueError(f"unknown level: {level!r}")


def _replace_version_inplace(manifest_path: Path, new_version: str) -> None:
    """Replace `version = "..."` via regex, preserving comments/formatting."""
    content = manifest_path.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'^(version\s*=\s*)"[^"]*"',
        rf'\1"{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise RuntimeError(
            f"could not locate `version = \"...\"` in {manifest_path}"
        )
    manifest_path.write_text(new_content, encoding="utf-8")


def _generate_manifest(pkg_dir: Path, name: str, kind: str) -> None:
    """Create manifest.toml interactively for a new package."""
    ui.info(f"Package {kind}s/{name} has no manifest.toml — let's create one.")
    default_author = git_ops.git_config_value("user.name", repo=workspace_dir()) or ""

    version = ui.ask_text("Initial version", default="0.1.0").strip() or "0.1.0"
    description = ui.ask_text("Description (one line)").strip()
    author = ui.ask_text("Author", default=default_author).strip()

    lines = ["[package]", f'name = "{name}"', f'version = "{version}"']
    if description:
        safe_desc = description.replace('"', '\\"')
        lines.append(f'description = "{safe_desc}"')
    if author:
        safe_author = author.replace('"', '\\"')
        lines.append(f'author = "{safe_author}"')

    content = "\n".join(lines) + "\n"
    manifest_path = pkg_dir / "manifest.toml"
    manifest_path.write_text(content, encoding="utf-8")
    ui.ok(f"manifest.toml created: {manifest_path}")


def _prompt_workspace_package() -> str:
    packages = registry_scan.scan(workspace_dir())
    if not packages:
        ui.die(
            f"No packages with a manifest in {workspace_dir()}. "
            "Create ~/.pskt/<agents|skills|commands>/<name>/ first "
            "(then pass the name explicitly to bootstrap a manifest)."
        )
    labels = [p.qualified_name for p in packages]
    return ui.ask_select("Which package to push?", choices=labels)


def _publish_workspace_pkg(
    cfg: config.Config,
    pkg_dir: Path,
    kind: str,
    pkg_name: str,
    message: str | None,
) -> str | None:
    """Bump + commit + push a workspace package. Returns the published version,
    or None if there was nothing to do (no changes / cancelled)."""
    rel_path = pkg_dir.relative_to(workspace_dir())
    manifest_path = pkg_dir / "manifest.toml"

    try:
        changes = git_ops.status_porcelain(workspace_dir(), str(rel_path))
    except git_ops.GitError as e:
        ui.die(f"Failed to read workspace status: {e}")

    has_manifest = manifest_path.exists()

    if has_manifest and not changes:
        ui.warn(f"No changes detected in {kind}s/{pkg_name}. Nothing to do.")
        return None

    if not has_manifest:
        _generate_manifest(pkg_dir, pkg_name, kind)
    else:
        try:
            current_mf = manifest_mod.load(manifest_path)
        except manifest_mod.ManifestError as e:
            ui.die(f"current manifest is invalid: {e}")

        ui.console.print(f"[bold]Changes in {kind}s/{pkg_name}:[/bold]")
        for line in changes:
            ui.console.print(f"  [muted]{line}[/muted]")
        ui.console.print()

        try:
            choices_map = {
                "patch": _bump(current_mf.version, "patch"),
                "minor": _bump(current_mf.version, "minor"),
                "major": _bump(current_mf.version, "major"),
            }
        except ValueError as e:
            ui.die(f"manifest.toml has an invalid version: {e}")

        labels = [
            f"patch  ({current_mf.version} → {choices_map['patch']})",
            f"minor  ({current_mf.version} → {choices_map['minor']})",
            f"major  ({current_mf.version} → {choices_map['major']})",
            f"no bump (keep {current_mf.version})",
        ]
        choice = ui.ask_select("Bump version", choices=labels)

        if choice.startswith("patch"):
            new_version = choices_map["patch"]
        elif choice.startswith("minor"):
            new_version = choices_map["minor"]
        elif choice.startswith("major"):
            new_version = choices_map["major"]
        else:
            new_version = current_mf.version

        if new_version != current_mf.version:
            try:
                _replace_version_inplace(manifest_path, new_version)
            except RuntimeError as e:
                ui.die(str(e))
            ui.ok(f"version: {current_mf.version} → {new_version}")

    try:
        final_mf = manifest_mod.load(manifest_path)
    except manifest_mod.ManifestError as e:
        ui.die(f"final manifest is invalid: {e}")
    default_message = f"{kind}s/{pkg_name} v{final_mf.version}"
    final_message = message or ui.ask_text("Commit message", default=default_message)
    if not final_message.strip():
        final_message = default_message

    ui.info(f"git add {rel_path}/")
    try:
        git_ops.add(workspace_dir(), str(rel_path))
    except git_ops.GitError as e:
        ui.die(f"git add failed: {e}")

    ui.info("git commit...")
    try:
        git_ops.commit(workspace_dir(), final_message)
    except git_ops.GitError as e:
        ui.die(
            f"git commit failed: {e}\n"
            "If this is due to missing `user.name`/`user.email`, configure them with:\n"
            "  git config --global user.name \"Your Name\"\n"
            "  git config --global user.email \"you@example.com\""
        )

    ui.info("git push origin HEAD:main...")
    token = auth.get_token() if cfg.auth_method == "https" else None
    try:
        git_ops.push(workspace_dir(), cfg.registry_url, token=token)
    except git_ops.GitError as e:
        ui.die(
            f"git push failed: {e}\n"
            "The commit was created locally. Resolve the issue and run "
            "`pskt push` again (it will detect no changes and only push the "
            "pending commit — or run `git push` directly in ~/.pskt/)."
        )

    ui.ok(f"Pushed {kind}s/{pkg_name} v{final_mf.version}")
    return final_mf.version


# ─── Scope mode (publish edits made in place in an installation) ─────────────


def _load_preserve(ws_pkg_dir: Path) -> list[str]:
    """`[update].preserve` patterns from the workspace manifest, or []."""
    manifest_path = ws_pkg_dir / "manifest.toml"
    if not manifest_path.exists():
        return []
    try:
        return manifest_mod.load(manifest_path).preserve
    except manifest_mod.ManifestError:
        return []


def _publishable_files(source: Path, env_base: Path, preserve: list[str]) -> list[Path]:
    """Install files to mirror back, minus the `preserve` (user-data) ones."""
    files = artifacts.files_relative_to_env_base(source, env_base)
    return [f for f in files if not manifest_mod.matches_preserve(f, preserve)]


def _has_local_edits(
    source: Path, env_base: Path, ws_pkg_dir: Path, preserve: list[str]
) -> bool:
    """Does the installation's publishable content differ from the workspace?

    Covers added/modified files (install vs workspace) and deletions
    (publishable file present in the workspace but gone from the install).
    `preserve`-matched files and manifest.toml are ignored.
    """
    publishable = _publishable_files(source, env_base, preserve)
    pub_set = {str(rel) for rel in publishable}

    for rel in publishable:
        dst = ws_pkg_dir / rel
        if not dst.exists() or (env_base / rel).read_bytes() != dst.read_bytes():
            return True

    if ws_pkg_dir.is_dir():
        for f in ws_pkg_dir.rglob("*"):
            if not f.is_file() or f.name == "manifest.toml":
                continue
            rel = f.relative_to(ws_pkg_dir)
            if manifest_mod.matches_preserve(rel, preserve):
                continue
            if str(rel) not in pub_set:
                return True
    return False


def _sync_to_workspace(
    env_base: Path, ws_pkg_dir: Path, publishable: list[Path], preserve: list[str]
) -> None:
    """Mirror the installation's publishable files into the workspace package,
    making the workspace match the install (additions, edits, and deletions).
    manifest.toml and preserve-matched files are left untouched."""
    pub_set = {str(rel) for rel in publishable}

    if ws_pkg_dir.is_dir():
        for f in ws_pkg_dir.rglob("*"):
            if not f.is_file() or f.name == "manifest.toml":
                continue
            rel = f.relative_to(ws_pkg_dir)
            if manifest_mod.matches_preserve(rel, preserve):
                continue
            if str(rel) not in pub_set:
                f.unlink()

    ws_pkg_dir.mkdir(parents=True, exist_ok=True)
    for rel in publishable:
        src = env_base / rel
        tgt = ws_pkg_dir / rel
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, tgt)


def _build_scope_entries(scope: str) -> tuple[dict, list[dict]]:
    """Resolve every installed package in `scope` to its on-disk source and
    workspace mirror. Returns (state, entries); entries skip records whose
    install files have vanished or whose kind the env no longer supports."""
    state = installed_mod.load(scope)
    ws = workspace_dir()
    entries: list[dict] = []
    for skey, rec in sorted(state.items()):
        if not envs.supports_kind(rec.env, rec.kind):
            continue
        kind_folder = _KIND_FOLDER.get(rec.kind)
        if kind_folder is None:
            continue
        env_base = artifacts.env_base_for(rec.env, scope, rec.kind)
        source = artifacts.find_source(env_base, kind_folder, rec.name)
        if source is None:
            continue
        ws_pkg_dir = ws / kind_folder / rec.name
        preserve = _load_preserve(ws_pkg_dir)
        entries.append(
            {
                "storage_key": skey,
                "qualified": rec.qualified_name,
                "record": rec,
                "env_base": env_base,
                "source": source,
                "ws_pkg_dir": ws_pkg_dir,
                "preserve": preserve,
                "edited": _has_local_edits(source, env_base, ws_pkg_dir, preserve),
            }
        )
    return state, entries


def _resolve_scope_entry(name: str, scope: str, entries: list[dict]) -> dict:
    if "/" in name:
        matches = [e for e in entries if e["qualified"] == name]
    else:
        matches = [e for e in entries if e["record"].name == name]

    if not matches:
        ui.die(f"'{name}' is not installed in {scope} (or its files are missing).")

    quals = {e["qualified"] for e in matches}
    if len(quals) > 1:
        ui.warn(f"'{name}' is ambiguous in {scope}:")
        for q in sorted(quals):
            ui.console.print(f"  [muted]→[/muted] {q}")
        ui.die(f"Use the qualified name, e.g. `pskt push skills/<name> {scope}`.")

    if len(matches) == 1:
        return matches[0]

    # Same package installed for several code-agents — publish from which one.
    choice_map = {
        f"{e['record'].env}  v{e['record'].version}": e
        for e in sorted(matches, key=lambda e: e["record"].env)
    }
    choice = ui.ask_select(
        f"'{matches[0]['qualified']}' is installed for several code-agents — publish from which?",
        choices=list(choice_map.keys()),
    )
    return choice_map[choice]


def _run_scoped(
    cfg: config.Config, name: str | None, scope: str, message: str | None
) -> None:
    state, entries = _build_scope_entries(scope)
    if not entries:
        ui.die(
            f"No installed packages in {scope} to publish from. "
            f"Install something there first, or use `pskt push <name>` for a workspace package."
        )

    if name is not None:
        entry = _resolve_scope_entry(name, scope, entries)
    else:
        editable = [e for e in entries if e["edited"]]
        if not editable:
            ui.die(
                f"No {scope} installation has local edits to publish. "
                "Edit a package in its install dir first."
            )
        choice_map = {f"{e['qualified']}  v{e['record'].version}": e for e in editable}
        choice = ui.ask_select(
            f"Which {scope} installation to publish?",
            choices=list(choice_map.keys()),
        )
        entry = choice_map[choice]

    rec = entry["record"]
    ws_pkg_dir = entry["ws_pkg_dir"]
    env_base = entry["env_base"]
    preserve = entry["preserve"]
    publishable = _publishable_files(entry["source"], env_base, preserve)

    ui.info(
        f"Syncing {entry['qualified']} from the {scope} installation "
        f"({env_base}) into the workspace..."
    )
    _sync_to_workspace(env_base, ws_pkg_dir, publishable, preserve)

    if not (ws_pkg_dir / "manifest.toml").exists():
        _generate_manifest(ws_pkg_dir, rec.name, rec.kind)

    version = _publish_workspace_pkg(cfg, ws_pkg_dir, rec.kind, rec.name, message)
    if version is None:
        return

    # The installation now matches the freshly published version — record it so
    # `status` doesn't flag it as outdated against the registry it just updated.
    head = git_ops.head_commit(workspace_dir())
    now_iso = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    files = artifacts.files_relative_to_env_base(entry["source"], env_base)
    state[entry["storage_key"]] = InstalledPackage(
        name=rec.name,
        kind=rec.kind,
        version=version,
        scope=scope,
        env=rec.env,
        installed_at=now_iso,
        source_commit=head,
        installed_paths=[str(p) for p in files],
    )
    installed_mod.save(state, scope)
    ui.ok(f"Install record for {entry['qualified']} ({scope}) updated to v{version}.")


def run(
    name: str = typer.Argument(
        None,
        help="Package name (or <kind>s/<name>); 'root'/'project' alone selects scope mode.",
    ),
    scope: str = typer.Argument(
        None,
        help="root | project — publish edits made in place in that scope's installation.",
    ),
    message: str = typer.Option(
        None,
        "--message",
        "-m",
        help="Commit message (default: '<kind>s/<name> v<version>')",
    ),
) -> None:
    cfg = config.load_or_die()

    # `pskt push project` / `pskt push root`: the lone positional is a scope.
    if scope is None and name in installed_mod.SCOPES:
        scope, name = name, None

    if scope is not None:
        if scope not in installed_mod.SCOPES:
            ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")
        _run_scoped(cfg, name, scope, message)
        return

    # Workspace mode: publish a package edited directly in ~/.pskt/.
    if name is None:
        name = _prompt_workspace_package()
    pkg_dir, kind, pkg_name = _resolve_package_dir(name)
    _publish_workspace_pkg(cfg, pkg_dir, kind, pkg_name, message)
