"""pskt doctor — environment diagnostics."""
from __future__ import annotations

import sys

import typer
from rich.table import Table

from perskent import auth, config, git_ops, ui
from perskent.paths import config_file, workspace_dir


def run() -> None:
    table = Table(title="pskt doctor", show_header=True, header_style="bold")
    table.add_column("Check", no_wrap=True)
    table.add_column("Status", no_wrap=True, justify="center")
    table.add_column("Details", overflow="fold")

    failures = 0

    # 1. Python version
    py_version = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)
    table.add_row(
        "Python ≥ 3.11",
        "[ok]✓[/ok]" if py_ok else "[err]✗[/err]",
        py_version,
    )
    if not py_ok:
        failures += 1

    # 2. git installed
    git_v = git_ops.git_version()
    git_ok = git_v is not None
    table.add_row(
        "git installed",
        "[ok]✓[/ok]" if git_ok else "[err]✗[/err]",
        git_v or "git not found in PATH",
    )
    if not git_ok:
        failures += 1

    # 3. config.toml
    cfg: config.Config | None = None
    cfg_path = config_file()
    if config.exists():
        try:
            cfg = config.load()
            table.add_row("config.toml", "[ok]✓[/ok]", str(cfg_path))
        except (ValueError, OSError) as e:
            table.add_row("config.toml", "[err]✗[/err]", f"corrupted: {e}")
            failures += 1
    else:
        table.add_row(
            "config.toml",
            "[err]✗[/err]",
            f"missing at {cfg_path} (run `pskt init`)",
        )
        failures += 1

    # 4. workspace
    ws = workspace_dir()
    if ws.exists() and git_ops.is_git_repo(ws):
        table.add_row("workspace ~/.pskt/", "[ok]✓[/ok]", str(ws))
    elif ws.exists():
        table.add_row(
            "workspace ~/.pskt/",
            "[err]✗[/err]",
            f"{ws} exists but is not a git repo",
        )
        failures += 1
    else:
        table.add_row(
            "workspace ~/.pskt/",
            "[err]✗[/err]",
            f"missing (run `pskt init`)",
        )
        failures += 1

    # 5. token (only if config says HTTPS)
    if cfg is not None:
        if cfg.auth_method == "https":
            tok_method = auth.storage_method()
            if tok_method == "keyring":
                table.add_row("Token", "[ok]✓[/ok]", "stored in the OS keyring")
            elif tok_method == "file":
                table.add_row(
                    "Token",
                    "[warn]✓[/warn]",
                    f"at {auth.token_file_path()} (chmod 600 fallback — OS keyring unavailable)",
                )
            else:
                table.add_row(
                    "Token",
                    "[err]✗[/err]",
                    "missing — run `pskt init --force` to reconfigure",
                )
                failures += 1
        else:
            table.add_row(
                "Auth method",
                "[muted]—[/muted]",
                "SSH (auth delegated to ssh-agent / SSH key)",
            )

    # 6. registry reachable
    if cfg is not None:
        token = auth.get_token() if cfg.auth_method == "https" else None
        try:
            git_ops.ls_remote(cfg.registry_url, token=token)
            table.add_row(
                "Remote registry reachable",
                "[ok]✓[/ok]",
                cfg.registry_url,
            )
        except git_ops.GitError as e:
            table.add_row(
                "Remote registry reachable",
                "[err]✗[/err]",
                f"{cfg.registry_url}\n{e}",
            )
            failures += 1
    else:
        table.add_row(
            "Remote registry reachable",
            "[muted]—[/muted]",
            "(run `pskt init` first)",
        )

    ui.console.print(table)

    if failures == 0:
        ui.ok("All good.")
    else:
        ui.error(f"{failures} check(s) failed.")
        raise typer.Exit(code=1)
