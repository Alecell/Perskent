"""pskt sync — git pull on the local workspace."""
from __future__ import annotations

from perskent import auth, config, git_ops, ui
from perskent.paths import workspace_dir


def run() -> None:
    cfg = config.load_or_die()

    ws = workspace_dir()
    if not ws.exists() or not git_ops.is_git_repo(ws):
        ui.die(f"Workspace missing at {ws}. Run `pskt init --force` to reconfigure.")

    token = auth.get_token() if cfg.auth_method == "https" else None

    ui.info(f"Syncing registry at {ws}...")
    before = git_ops.head_commit(ws)

    try:
        git_ops.pull(ws, cfg.registry_url, token=token)
    except git_ops.GitError as e:
        # Common case: repo just created on GitHub, still with no commits → pull fails
        # without an upstream. Not a fatal error, just "nothing to pull yet".
        if before is None:
            ui.warn(
                "Remote registry is empty (no commits yet). "
                "Create packages at ~/.pskt/<agents|skills|commands>/<name>/ "
                "and push them with `pskt push <name>`."
            )
            return
        ui.die(f"Pull failed:\n  {e}")

    after = git_ops.head_commit(ws)

    if before is None and after is None:
        ui.warn("Remote registry is empty.")
        return
    if before is None:
        ui.ok(f"Registry synced for the first time (HEAD: {after[:7]}).")
        return
    if before == after:
        ui.ok("Already up to date.")
        return

    try:
        count = git_ops.commits_between(ws, before, after)
        ui.ok(f"Synced: {count} new commit(s).")
    except git_ops.GitError:
        ui.ok("Synced.")
