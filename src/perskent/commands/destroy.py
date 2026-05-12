"""pskt destroy <name> — permanently remove a package from the registry.

Removes the package folder from the local workspace (~/.pskt/) and pushes
the deletion to the remote. The package's git history is preserved (you
can still inspect it via `git log` in ~/.pskt/), it's just gone from HEAD.

Does NOT touch installed copies in ~/.claude/ or ./.claude/. Use
`pskt remove <name> <scope>` separately if you want to clean those up.
"""
from __future__ import annotations

from pathlib import Path

import typer

from perskent import auth, config, git_ops, ui
from perskent import manifest as manifest_mod
from perskent.paths import workspace_dir
from perskent.registry_scan import KIND_FOLDERS, KIND_SINGULAR


def _resolve_package_dir(query: str) -> tuple[Path, str, str]:
    """Resolve `<name>` or `<kind>s/<name>` into (path, kind_singular, name).

    Requires an existing folder (no on-the-fly creation here — destroy is
    only for things that already exist).
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
            ui.die(f"Package '{query}' does not exist in the workspace.")
        return pkg_dir, KIND_SINGULAR[kind_folder], name

    matches: list[tuple[Path, str]] = []
    for kind_folder in KIND_FOLDERS:
        candidate = ws / kind_folder / query
        if candidate.is_dir():
            matches.append((candidate, KIND_SINGULAR[kind_folder]))

    if not matches:
        ui.die(f"Package '{query}' does not exist in the workspace.")
    if len(matches) > 1:
        ui.warn(f"'{query}' is ambiguous — exists in multiple kinds:")
        for path, kind in matches:
            ui.console.print(f"  [muted]→[/muted] {kind}s/{query}")
        ui.die("Use the qualified name, e.g. `pskt destroy agents/<name>`.")

    pkg_dir, kind = matches[0]
    return pkg_dir, kind, query


def run(
    name: str = typer.Argument(
        ...,
        help="Package name (or <kind>s/<name> to disambiguate)",
    ),
    message: str = typer.Option(
        None,
        "--message",
        "-m",
        help="Commit message (default: 'destroy <kind>s/<name>')",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt (for scripts / automation)",
    ),
) -> None:
    cfg = config.load_or_die()

    pkg_dir, kind, pkg_name = _resolve_package_dir(name)
    rel_path = pkg_dir.relative_to(workspace_dir())
    qualified = f"{kind}s/{pkg_name}"

    # Try to read the manifest just to show the current version in the preview.
    # If the manifest is missing or invalid, we proceed anyway — we're deleting.
    version_str = ""
    manifest_path = pkg_dir / "manifest.toml"
    if manifest_path.exists():
        try:
            mf = manifest_mod.load(manifest_path)
            version_str = f" v{mf.version}"
        except manifest_mod.ManifestError:
            pass

    ui.warn(f"This will permanently delete '{qualified}{version_str}' from the registry:")
    ui.console.print(f"  [muted]→[/muted] local workspace ({pkg_dir})")
    ui.console.print(f"  [muted]→[/muted] remote registry ({cfg.registry_url})")
    ui.console.print()
    ui.console.print(
        "[muted]Installed copies in the code-agent's directory are not affected. "
        "Use `pskt remove` separately if you want to clean those up.[/muted]"
    )
    ui.console.print()

    if not yes:
        if not ui.ask_confirm(f"Delete '{qualified}' from the registry?", default=False):
            ui.info("Cancelled.")
            return

    final_message = message or f"destroy {qualified}"

    ui.info(f"git rm -rf {rel_path}/")
    try:
        git_ops.rm_recursive(workspace_dir(), str(rel_path))
    except git_ops.GitError as e:
        ui.die(f"git rm failed: {e}")

    ui.info("git commit...")
    try:
        git_ops.commit(workspace_dir(), final_message)
    except git_ops.GitError as e:
        ui.die(
            f"git commit failed: {e}\n"
            "The package was removed from disk but the deletion is not "
            "committed yet. Run `git commit` and `git push` manually in "
            "~/.pskt/ to finish, or `git restore` to undo."
        )

    ui.info("git push origin HEAD:main...")
    token = auth.get_token() if cfg.auth_method == "https" else None
    try:
        git_ops.push(workspace_dir(), cfg.registry_url, token=token)
    except git_ops.GitError as e:
        ui.die(
            f"git push failed: {e}\n"
            "The deletion was committed locally. Resolve the issue and "
            "run `git push` in ~/.pskt/ to finish."
        )

    ui.ok(f"Destroyed {qualified}{version_str}")
