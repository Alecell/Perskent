"""Resolve which code-agent(s) a per-scope command should act on.

A scope can now target several code-agents (see `config.Config.agents_for`).
Commands like `install`/`update`/`remove` take an optional `--agent <name>|all`
and otherwise prompt. This module centralizes that resolution so the behaviour
stays identical across commands.
"""
from __future__ import annotations

from perskent import config, envs, ui

ALL = "all"


def select_targets(
    cfg: config.Config,
    scope: str,
    agent_opt: str | None,
    *,
    verb: str = "act on",
    allow_all: bool = True,
) -> list[str]:
    """Return the code-agents in `scope` to operate on.

    - `agent_opt == "all"` (and allow_all) → every agent configured for the scope.
    - `agent_opt` set → that single agent (must be configured for the scope).
    - one agent configured → it, no prompt.
    - several configured → interactive select (plus an `all` option if allowed).
    """
    agents = cfg.agents_for(scope)
    if not agents:
        ui.die(f"No code-agent configured for the {scope} scope. Run `pskt init --force`.")

    if agent_opt is not None:
        if allow_all and agent_opt == ALL:
            return list(agents)
        if agent_opt in agents:
            return [agent_opt]
        if envs.is_valid(agent_opt):
            ui.die(
                f"Code-agent '{agent_opt}' is not configured for the {scope} scope "
                f"(configured: {', '.join(agents)}). "
                f"Add it with `pskt code-agent add {agent_opt} {scope}`."
            )
        ui.die(f"Unknown code-agent: {agent_opt!r}. Must be one of {', '.join(envs.ENVS)}.")

    if len(agents) == 1:
        return list(agents)

    choices = list(agents) + ([ALL] if allow_all else [])
    choice = ui.ask_select(f"Which code-agent to {verb}?", choices=choices)
    if choice == ALL:
        return list(agents)
    return [choice]
