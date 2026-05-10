"""pskt doctor — diagnóstico do ambiente."""
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
    table.add_column("Detalhes", overflow="fold")

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
        "git instalado",
        "[ok]✓[/ok]" if git_ok else "[err]✗[/err]",
        git_v or "git não encontrado no PATH",
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
            table.add_row("config.toml", "[err]✗[/err]", f"corrompido: {e}")
            failures += 1
    else:
        table.add_row(
            "config.toml",
            "[err]✗[/err]",
            f"ausente em {cfg_path} (rode `pskt init`)",
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
            f"{ws} existe mas não é um repo git",
        )
        failures += 1
    else:
        table.add_row(
            "workspace ~/.pskt/",
            "[err]✗[/err]",
            f"ausente (rode `pskt init`)",
        )
        failures += 1

    # 5. token (só se config diz HTTPS)
    if cfg is not None:
        if cfg.auth_method == "https":
            tok_method = auth.storage_method()
            if tok_method == "keyring":
                table.add_row("Token", "[ok]✓[/ok]", "armazenado no keyring do OS")
            elif tok_method == "file":
                table.add_row(
                    "Token",
                    "[warn]✓[/warn]",
                    f"em {auth.token_file_path()} (fallback chmod 600 — keyring do OS indisponível)",
                )
            else:
                table.add_row(
                    "Token",
                    "[err]✗[/err]",
                    "ausente — rode `pskt init --force` pra reconfigurar",
                )
                failures += 1
        else:
            table.add_row(
                "Auth method",
                "[muted]—[/muted]",
                "SSH (autenticação delegada ao ssh-agent / chave SSH do sistema)",
            )

    # 6. registry reachable
    if cfg is not None:
        token = auth.get_token() if cfg.auth_method == "https" else None
        try:
            git_ops.ls_remote(cfg.registry_url, token=token)
            table.add_row(
                "Registry remoto acessível",
                "[ok]✓[/ok]",
                cfg.registry_url,
            )
        except git_ops.GitError as e:
            table.add_row(
                "Registry remoto acessível",
                "[err]✗[/err]",
                f"{cfg.registry_url}\n{e}",
            )
            failures += 1
    else:
        table.add_row(
            "Registry remoto acessível",
            "[muted]—[/muted]",
            "(rode `pskt init` primeiro)",
        )

    ui.console.print(table)

    if failures == 0:
        ui.ok("Tudo certo.")
    else:
        ui.error(f"{failures} check(s) com problema.")
        raise typer.Exit(code=1)
