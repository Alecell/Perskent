"""pskt mirror — replicate artifacts across the code-agents of one scope.

Makes the code-agents configured for a scope hold the same skills/agents/
commands, so e.g. a skill you use in `.claude` also shows up in `.codex`.

Replication is **dumb/verbatim**: files are copied to the equivalent location
of each agent, with no frontmatter parsing or format conversion. Keeping a
package usable across agents is the package author's responsibility — perskent
only knows *where* each kind lives (see `envs`).

    pskt mirror                          # symmetric: union across all the scope's agents
    pskt mirror --from claude --to codex # directional: claude wins, codex receives
    pskt mirror --to codex               # every other agent → codex
    pskt mirror --only skills/foo        # restrict to one artifact (bypasses opt-in list)
    pskt mirror --scope project|root     # default: project
    pskt mirror --strategy newest|abort  # symmetric conflict policy (default: newest)
    pskt mirror --dry-run                # show the plan, touch nothing

What participates is **opt-in** via `.pskt-mirror.toml` (project) /
`~/.config/pskt/mirror.toml` (root), unless `--only` is given.

Conflicts (same artifact, different content across agents) are resolved by
**newest mtime wins**, with a warning. `--strategy abort` stops without writing
when any conflict is found. In `--from` mode the source is always authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from perskent import config, converters, envs, mirror_config, ui
from perskent import installed as installed_mod
from perskent.paths import dest_project_dir, dest_root_dir
from perskent.registry_scan import KIND_FOLDERS, KIND_SINGULAR

STRATEGY_NEWEST = "newest"
STRATEGY_ABORT = "abort"


@dataclass
class _Copy:
    env: str
    env_base: Path
    source: Path           # the artifact dir or .md file
    files: list[Path]      # paths relative to env_base
    mtime: float           # newest mtime among the files


def _dest_base(env: str, scope: str, kind: str) -> Path:
    if scope == installed_mod.ROOT:
        return dest_root_dir(env, kind)
    return dest_project_dir(env, kind)


def _find_copy(env: str, scope: str, kind: str, name: str) -> _Copy | None:
    """Locate an artifact under `env`'s dest dir, honoring the env's layout
    (single .toml/.mdc, single .md, or a skill dir), with legacy fallbacks."""
    env_base = _dest_base(env, scope, kind)
    layout = converters.dest_layout(env, kind, name)
    kind_folder = f"{kind}s"
    candidates = list(layout.glob_roots) + [f"{kind_folder}/{name}", f"{kind_folder}/{name}.md"]
    files: list[Path] = []
    for cand in candidates:
        p = env_base / cand
        if p.is_dir():
            files = sorted(f.relative_to(env_base) for f in p.rglob("*") if f.is_file())
            break
        if p.is_file():
            files = [p.relative_to(env_base)]
            break
    if not files:
        return None
    mtime = max(((env_base / f).stat().st_mtime for f in files), default=0.0)
    return _Copy(env=env, env_base=env_base, source=env_base, files=files, mtime=mtime)


def _snapshot(copy: _Copy) -> dict[str, bytes]:
    return {str(rel): (copy.env_base / rel).read_bytes() for rel in copy.files}


def _canonical_snapshot(copy: _Copy, kind: str, name: str) -> dict[str, bytes]:
    """Canonical (Claude-markdown) form of a copy, so artifacts that differ
    only by format or by pskt's own injection compare as equal."""
    return converters.canonical_files(copy.env, kind, name, _snapshot(copy))


def _target_result(winner: _Copy, kind: str, name: str, target_env: str) -> converters.ConvertResult:
    """What `target_env` should physically hold for the winner's artifact,
    pivoting through canonical (carries conversion warnings)."""
    canon = converters.canonical_files(winner.env, kind, name, _snapshot(winner))
    return converters.from_canonical(target_env, converters.build_artifact(kind, name, canon))


def _write_snapshot(snap: dict[str, bytes], target_env: str, scope: str, kind: str) -> None:
    """Write a (already projected) snapshot into the target agent's dest dir."""
    target_base = _dest_base(target_env, scope, kind)
    for rel, data in snap.items():
        tgt = target_base / rel
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tgt.write_bytes(data)


def run(
    from_: str = typer.Option(
        None, "--from", help="Source code-agent (directional mode; always wins)."
    ),
    to: str = typer.Option(
        None, "--to", help="Destination code-agent (directional mode)."
    ),
    only: str = typer.Option(
        None, "--only", help="Mirror just this artifact (<kind>s/<name>); bypasses the opt-in list."
    ),
    scope: str = typer.Option(
        installed_mod.PROJECT, "--scope", "-s", help="root | project (default: project)."
    ),
    strategy: str = typer.Option(
        STRATEGY_NEWEST, "--strategy", help="Symmetric conflict policy: newest | abort."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the plan without copying anything."
    ),
) -> None:
    cfg = config.load_or_die()

    if scope not in installed_mod.SCOPES:
        ui.die(f"Invalid scope: {scope!r}. Use 'root' or 'project'.")
    if strategy not in (STRATEGY_NEWEST, STRATEGY_ABORT):
        ui.die(f"Invalid --strategy: {strategy!r}. Use 'newest' or 'abort'.")

    agents = cfg.agents_for(scope)
    if len(agents) < 2:
        ui.die(
            f"The {scope} scope has {len(agents)} code-agent configured "
            f"({', '.join(agents) or 'none'}). Mirroring needs at least two — "
            f"add one with `pskt code-agent add <tool> {scope}`."
        )

    for label, val in (("--from", from_), ("--to", to)):
        if val is not None and val not in agents:
            ui.die(
                f"{label} '{val}' is not configured for the {scope} scope "
                f"({', '.join(agents)})."
            )

    # Which artifacts participate.
    if only is not None:
        qualifieds = [only]
    else:
        qualifieds = mirror_config.include_list(scope, None)
        if not qualifieds:
            path = mirror_config.write_example(scope, None)
            ui.die(
                f"No artifacts opted in for mirroring in {scope}. "
                f"List them under [mirror].include in {path}, or pass `--only <kind>s/<name>`."
            )

    copied = 0
    skipped = 0
    conflicts: list[str] = []
    plan: list[str] = []

    for qualified in qualifieds:
        if "/" not in qualified:
            ui.warn(f"'{qualified}' is not kind-qualified (expected <kind>s/<name>) — skipped.")
            skipped += 1
            continue
        kind_folder, _, name = qualified.partition("/")
        if kind_folder not in KIND_FOLDERS:
            ui.warn(f"'{qualified}': unknown kind '{kind_folder}' — skipped.")
            skipped += 1
            continue
        kind = KIND_SINGULAR[kind_folder]

        # Existing copies among the scope's agents.
        copies: dict[str, _Copy] = {}
        for env in agents:
            if not envs.supports_kind(env, kind):
                continue
            c = _find_copy(env, scope, kind, name)
            if c is not None:
                copies[env] = c

        if not copies:
            ui.warn(f"'{qualified}' not found in any source code-agent of {scope} — skipped.")
            skipped += 1
            continue

        # Source candidates and targets, per mode.
        if from_ is not None:
            sources = [from_] if from_ in copies else []
            targets = [to] if to is not None else [e for e in agents if e != from_]
        elif to is not None:
            sources = [e for e in copies if e != to]
            targets = [to]
        else:
            sources = list(copies.keys())
            targets = list(agents)

        if not sources:
            ui.warn(f"'{qualified}' has no source copy for the requested direction — skipped.")
            skipped += 1
            continue

        winner = max((copies[e] for e in sources), key=lambda c: c.mtime)
        winner_canon = _canonical_snapshot(winner, kind, name)

        # Conflict = source candidates disagree on content (only meaningful when
        # the source isn't a single authoritative `--from`). Compared on the
        # canonical form so format differences (md vs toml) and pskt's own
        # injection never count as a difference.
        if from_ is None:
            for e in sources:
                if e != winner.env and _canonical_snapshot(copies[e], kind, name) != winner_canon:
                    conflicts.append(qualified)
                    ui.warn(
                        f"conflict on '{qualified}': '{winner.env}' is newest and wins "
                        f"over '{e}'."
                    )
                    break

        # Plan the targets that need the winner's content.
        artifact_actions = 0
        for tgt in targets:
            if tgt == winner.env:
                continue
            if not envs.supports_kind(tgt, kind):
                ui.warn(f"'{qualified}': code-agent '{tgt}' has no location for kind '{kind}' — skipped.")
                continue
            # What this target should physically hold (format-converted as
            # needed: codex agents become TOML, skills gain frontmatter, etc.).
            result = _target_result(winner, kind, name, tgt)
            target_snap = result.files
            if not target_snap:
                ui.warn(f"'{qualified}': nothing to write for '{tgt}' — skipped.")
                continue
            existing = copies.get(tgt)
            if existing is not None and _snapshot(existing) == target_snap:
                continue  # already identical
            verb = "would copy" if dry_run else "copying"
            plan.append(f"{verb} {qualified}: {winner.env} → {tgt}")
            for w in result.warnings:
                ui.warn(f"[{tgt}] {w}")
            artifact_actions += 1
            if not (dry_run or strategy == STRATEGY_ABORT):
                _write_snapshot(target_snap, tgt, scope, kind)
                copied += 1

        if artifact_actions == 0:
            skipped += 1

    # Abort mode: if any conflict surfaced, report and make no changes.
    if conflicts and strategy == STRATEGY_ABORT:
        ui.error(f"Aborted: {len(conflicts)} conflict(s) found (--strategy abort):")
        for q in sorted(set(conflicts)):
            ui.console.print(f"  [err]✗[/err] {q}")
        ui.info("Resolve them, or re-run with `--strategy newest`.")
        raise typer.Exit(1)

    if dry_run:
        if plan:
            ui.console.print("[bold]Mirror plan[/bold] (dry-run):")
            for line in plan:
                ui.console.print(f"  [muted]→[/muted] {line}")
        else:
            ui.info("Nothing to mirror — all targeted agents are already in sync.")
        return

    if copied:
        ui.ok(f"Mirrored {copied} copy(ies) across the {scope} scope.")
    else:
        ui.info(f"Nothing to mirror in {scope} — agents already in sync.")
