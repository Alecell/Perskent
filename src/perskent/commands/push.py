"""pskt push <name> — bump + commit + push of a package.

Flow:
1. Resolves the package (with kind disambiguation). If `name` is omitted,
   prompts interactively from the list of workspace packages.
2. If the folder has no `manifest.toml`, generates one interactively
   (description, author, initial version 0.1.0). Otherwise, shows git
   changes for the package and prompts for a bump (patch/minor/major/no bump).
3. Updates `version` in the manifest in place via regex (preserves comments).
4. git add `<kind>s/<name>/` + git commit + git push (askpass HTTPS).
"""
from __future__ import annotations

import re
from pathlib import Path

import typer

from perskent import auth, config, git_ops, registry_scan, ui
from perskent import manifest as manifest_mod
from perskent.paths import workspace_dir
from perskent.registry_scan import KIND_FOLDERS, KIND_SINGULAR


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


def run(
    name: str = typer.Argument(
        None,
        help="Package name (or <kind>s/<name>); omit for an interactive prompt.",
    ),
    message: str = typer.Option(
        None,
        "--message",
        "-m",
        help="Commit message (default: '<kind>s/<name> v<version>')",
    ),
) -> None:
    if not config.exists():
        ui.die("perskent is not initialized. Run `pskt init` first.")
    cfg = config.load()
    assert cfg is not None

    if name is None:
        name = _prompt_workspace_package()

    pkg_dir, kind, pkg_name = _resolve_package_dir(name)
    rel_path = pkg_dir.relative_to(workspace_dir())
    manifest_path = pkg_dir / "manifest.toml"

    try:
        changes = git_ops.status_porcelain(workspace_dir(), str(rel_path))
    except git_ops.GitError as e:
        ui.die(f"Failed to read workspace status: {e}")

    has_manifest = manifest_path.exists()

    if has_manifest and not changes:
        ui.warn(
            f"No changes detected in {kind}s/{pkg_name}. Nothing to do."
        )
        return

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
