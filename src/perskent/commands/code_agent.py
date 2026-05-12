"""pskt code-agent — show or reconfigure the code-agent used per scope."""
from __future__ import annotations

import typer

from perskent import config, envs, ui


def _print_current(cfg: config.Config) -> None:
    detected = envs.detect_installed()
    detected_str = ", ".join(detected) if detected else "none"
    ui.console.print(f"[bold]Code-agents[/bold]  [muted](detected on PATH: {detected_str})[/muted]")
    ui.console.print(f"  root scope:    [info]{cfg.code_agent_root}[/info]")
    ui.console.print(f"  project scope: [info]{cfg.code_agent_project}[/info]")


def run(
    tool: str = typer.Argument(
        None,
        help=f"Code-agent to use. One of: {', '.join(envs.ENVS)}. Omit to show the current config.",
    ),
    scope: str = typer.Argument(
        None,
        help="root | project. If omitted, applies to both scopes.",
    ),
) -> None:
    cfg = config.load_or_die()

    if tool is None:
        _print_current(cfg)
        return

    if not envs.is_valid(tool):
        ui.die(f"Unknown code-agent: {tool!r}. Must be one of {', '.join(envs.ENVS)}.")

    if scope is None:
        cfg.code_agent_root = tool
        cfg.code_agent_project = tool
        target = "both scopes"
    elif scope == "root":
        cfg.code_agent_root = tool
        target = "root scope"
    elif scope == "project":
        cfg.code_agent_project = tool
        target = "project scope"
    else:
        ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")

    config.save(cfg)
    ui.ok(f"Set code-agent to '{tool}' for {target}.")
