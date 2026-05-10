"""Typer entry point for the `pskt` / `perskent` CLI."""
from __future__ import annotations

import typer

from perskent import __version__
from perskent.commands import destroy as destroy_cmd
from perskent.commands import doctor as doctor_cmd
from perskent.commands import find as find_cmd
from perskent.commands import init as init_cmd
from perskent.commands import install as install_cmd
from perskent.commands import push as push_cmd
from perskent.commands import remove as remove_cmd
from perskent.commands import search as search_cmd
from perskent.commands import show as show_cmd
from perskent.commands import status as status_cmd
from perskent.commands import sync as sync_cmd
from perskent.commands import update as update_cmd

app = typer.Typer(
    name="pskt",
    help="Manage Claude Code skills, agents and commands via a private Git registry.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"perskent {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """perskent — package manager for Claude Code."""


app.command(
    "init",
    help="Configure the remote registry (URL + token) and clone the local workspace at ~/.pskt/.",
)(init_cmd.run)

app.command(
    "doctor",
    help="Environment diagnostics: git, paths, token, registry reachability.",
)(doctor_cmd.run)

app.command(
    "status",
    help="Consolidated view: workspace state, registry packages, installations (outdated/orphaned).",
)(status_cmd.run)

app.command(
    "sync",
    help="Sync ~/.pskt/ with the remote registry (git pull).",
)(sync_cmd.run)

app.add_typer(find_cmd.find_app)

app.command(
    "show",
    help="Show details of a registry package.",
)(show_cmd.run)

app.command(
    "search",
    help="Search packages by name or description.",
)(search_cmd.run)

app.command(
    "install",
    help="Install a package into ~/.claude/ (root) or ./.claude/ (project).",
)(install_cmd.run)

app.command(
    "remove",
    help="Remove an installed package.",
)(remove_cmd.run)

app.command(
    "update",
    help="Upgrade a package to the latest registry version, preserving files marked in [update].preserve.",
)(update_cmd.run)

app.command(
    "push",
    help="Publish a locally-edited package (~/.pskt/) to the remote registry: bump + commit + push.",
)(push_cmd.run)

app.command(
    "destroy",
    help="Permanently delete a package from the registry (workspace + remote). Does not affect installed copies.",
)(destroy_cmd.run)
