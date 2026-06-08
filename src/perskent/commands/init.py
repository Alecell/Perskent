"""pskt init — configure the remote registry and clone the local workspace."""
from __future__ import annotations

import shutil

import typer

from perskent import auth, config, envs, git_ops, ui
from perskent.paths import config_file, workspace_dir


def _ask_code_agents(scope_label: str, detected: list[str]) -> list[str]:
    """Prompt for which code-agent(s) to use in a given scope (multi-select).

    Detected-on-PATH agents are listed first and pre-checked; the rest follow.
    At least one must be chosen.
    """
    if detected:
        rest = [e for e in envs.ENVS if e not in detected]
        choices = detected + rest
    else:
        choices = list(envs.ENVS)
    label = "detected pre-selected" if detected else "none detected on PATH"
    while True:
        chosen = ui.ask_checkbox(
            f"Which code-agent(s) for {scope_label} scope? ({label}; space to toggle, enter to confirm)",
            choices=choices,
            default=detected,
        )
        if chosen:
            return chosen
        ui.warn("Pick at least one code-agent.")


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
    code_agents_root = _ask_code_agents("root", detected)
    code_agents_project = _ask_code_agents("project", detected)

    config.save(config.Config(
        registry_url=url,
        auth_method=method,
        code_agents_root=code_agents_root,
        code_agents_project=code_agents_project,
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
