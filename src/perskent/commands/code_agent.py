"""pskt code-agent — show or manage the code-agent(s) used per scope.

A scope can target several code-agents at once (so the same skill/agent/command
can live in `.claude`, `.codex`, … side by side and be kept in sync with
`pskt mirror`).

    pskt code-agent                     # show the current config
    pskt code-agent add codex           # add to BOTH scopes
    pskt code-agent add cursor project  # add to the project scope only
    pskt code-agent remove qwen root    # remove from the root scope
    pskt code-agent set claude codex    # replace BOTH scopes' lists
"""
from __future__ import annotations

import typer

from perskent import config, envs, ui
from perskent import installed as installed_mod

code_agent_app = typer.Typer(
    name="code-agent",
    help="Show or manage the code-agent(s) used per scope.",
    no_args_is_help=False,
    invoke_without_command=True,
)


def _show(cfg: config.Config) -> None:
    detected = envs.detect_installed()
    detected_str = ", ".join(detected) if detected else "none"
    ui.console.print(f"[bold]Code-agents[/bold]  [muted](detected on PATH: {detected_str})[/muted]")
    ui.console.print(f"  root scope:    [info]{', '.join(cfg.code_agents_root)}[/info]")
    ui.console.print(f"  project scope: [info]{', '.join(cfg.code_agents_project)}[/info]")


def _scopes(scope: str | None) -> list[str]:
    if scope is None:
        return list(installed_mod.SCOPES)
    if scope not in installed_mod.SCOPES:
        ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")
    return [scope]


def _get_list(cfg: config.Config, scope: str) -> list[str]:
    return cfg.code_agents_root if scope == installed_mod.ROOT else cfg.code_agents_project


def _set_list(cfg: config.Config, scope: str, value: list[str]) -> None:
    if scope == installed_mod.ROOT:
        cfg.code_agents_root = value
    else:
        cfg.code_agents_project = value


@code_agent_app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    cfg = config.load_or_die()
    _show(cfg)


@code_agent_app.command("add", help="Add a code-agent to a scope (or both scopes if omitted).")
def add(
    tool: str = typer.Argument(..., help=f"One of: {', '.join(envs.ENVS)}."),
    scope: str = typer.Argument(None, help="root | project. Omit to apply to both."),
) -> None:
    cfg = config.load_or_die()
    if not envs.is_valid(tool):
        ui.die(f"Unknown code-agent: {tool!r}. Must be one of {', '.join(envs.ENVS)}.")
    for sc in _scopes(scope):
        current = _get_list(cfg, sc)
        if tool in current:
            ui.warn(f"'{tool}' is already configured for the {sc} scope.")
            continue
        _set_list(cfg, sc, [*current, tool])
        ui.ok(f"Added '{tool}' to the {sc} scope.")
    config.save(cfg)


@code_agent_app.command("remove", help="Remove a code-agent from a scope (or both scopes if omitted).")
def remove(
    tool: str = typer.Argument(..., help=f"One of: {', '.join(envs.ENVS)}."),
    scope: str = typer.Argument(None, help="root | project. Omit to apply to both."),
) -> None:
    cfg = config.load_or_die()
    for sc in _scopes(scope):
        current = _get_list(cfg, sc)
        if tool not in current:
            ui.warn(f"'{tool}' is not configured for the {sc} scope.")
            continue
        if len(current) == 1:
            ui.die(
                f"Cannot remove '{tool}': the {sc} scope must keep at least one code-agent. "
                f"Use `pskt code-agent set <tool> {sc}` to switch instead."
            )
        _set_list(cfg, sc, [e for e in current if e != tool])
        ui.ok(f"Removed '{tool}' from the {sc} scope.")
    config.save(cfg)


@code_agent_app.command("set", help="Replace a scope's code-agent list (or both scopes if omitted).")
def set_(
    tools: list[str] = typer.Argument(..., help=f"One or more of: {', '.join(envs.ENVS)}."),
    scope: str = typer.Option(None, "--scope", "-s", help="root | project. Omit to apply to both."),
) -> None:
    cfg = config.load_or_die()
    cleaned: list[str] = []
    for t in tools:
        if not envs.is_valid(t):
            ui.die(f"Unknown code-agent: {t!r}. Must be one of {', '.join(envs.ENVS)}.")
        if t not in cleaned:
            cleaned.append(t)
    for sc in _scopes(scope):
        _set_list(cfg, sc, list(cleaned))
        ui.ok(f"Set {sc} scope code-agents to: {', '.join(cleaned)}.")
    config.save(cfg)
