"""pskt init — configure the remote registry and clone the local workspace."""
from __future__ import annotations

import shutil

import typer

from perskent import auth, config, envs, git_ops, ui
from perskent.paths import config_file, workspace_dir


def _ask_code_agent(scope_label: str, detected: list[str]) -> str:
    """Prompt for which code-agent to use in a given scope.

    If exactly one is detected on PATH, it's offered first; if multiple are
    detected, the list shows them ordered with non-detected at the bottom.
    If none are detected, falls back to the full canonical list.
    """
    if detected:
        rest = [e for e in envs.ENVS if e not in detected]
        choices = detected + rest
    else:
        choices = list(envs.ENVS)
    label = "detected" if detected else "none detected on PATH"
    return ui.ask_select(
        f"Which code-agent for {scope_label} scope? ({label})",
        choices=choices,
    )


def run(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Reconfigure even if already initialized (deletes local clone and token).",
    ),
) -> None:
    if config.exists() and not force:
        ui.warn("perskent is already initialized.")
        if not ui.ask_confirm(
            "Reconfigure from scratch? This deletes the local clone at ~/.pskt/ and removes the token.",
            default=False,
        ):
            ui.info("Cancelled, nothing was changed.")
            raise typer.Exit()
        force = True

    if force:
        ws = workspace_dir()
        if ws.exists():
            ui.info(f"Removing existing clone at {ws}...")
            shutil.rmtree(ws, ignore_errors=True)
        if auth.has_token():
            auth.delete_token()
        if config.exists():
            config.delete()

    ui.info("Configuring the remote registry.")
    url = ui.ask_text("Repository URL (HTTPS or SSH)")
    if not url:
        ui.die("URL cannot be empty.")

    try:
        method = git_ops.detect_auth_method(url)
    except git_ops.GitError as e:
        ui.die(str(e))

    token: str | None = None
    if method == "https":
        ui.info(
            "HTTPS URL detected — you'll be asked for an access token (GitHub PAT, deploy key, etc)."
        )
        token = ui.ask_password("Access token (will be saved in the OS keyring)")
        if not token:
            ui.die("Token cannot be empty for an HTTPS repository.")
    else:
        ui.info("SSH URL detected — authentication is delegated to your ssh-agent / SSH key.")

    ui.info("Testing access to the registry...")
    try:
        git_ops.ls_remote(url, token=token)
    except git_ops.GitError as e:
        ui.die(f"Failed to reach the registry:\n  {e}")
    ui.ok("Remote registry is reachable.")

    if method == "https":
        assert token is not None
        storage = auth.set_token(token)
        if storage == "keyring":
            ui.ok("Token saved to the OS keyring.")
        else:
            ui.warn(
                f"OS keyring unavailable in this environment — token saved at "
                f"{auth.token_file_path()} (chmod 600)."
            )

    detected = envs.detect_installed()
    if detected:
        ui.info(f"Code-agents detected on PATH: {', '.join(detected)}.")
    else:
        ui.info("No code-agent CLI detected on PATH — you can still pick one manually.")
    code_agent_root = _ask_code_agent("root", detected)
    code_agent_project = _ask_code_agent("project", detected)

    config.save(config.Config(
        registry_url=url,
        auth_method=method,
        code_agent_root=code_agent_root,
        code_agent_project=code_agent_project,
    ))
    ui.ok(f"Configuration saved at {config_file()}.")

    ui.info(f"Cloning the registry into {workspace_dir()}...")
    try:
        git_ops.clone(url, workspace_dir(), token=token)
    except git_ops.GitError as e:
        ui.die(f"Clone failed:\n  {e}")
    ui.ok(f"Workspace cloned at {workspace_dir()}.")

    ui.console.print()
    ui.console.print(
        "[ok bold]Done![/ok bold] Run [info]pskt find remote[/info] to list available packages."
    )
