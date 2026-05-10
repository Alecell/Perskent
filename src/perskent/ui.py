"""UI helpers: console rich + prompts via questionary.

Concentra toda formatação de output e interação. Comandos chamam estes helpers
em vez de usar print/input direto, pra UX consistente em todo o CLI.
"""
from __future__ import annotations

import sys
from collections.abc import Sequence

import questionary
from rich.console import Console
from rich.theme import Theme

theme = Theme({
    "ok": "green",
    "warn": "yellow",
    "err": "red bold",
    "info": "cyan",
    "muted": "dim",
})

console = Console(theme=theme)


def info(msg: str) -> None:
    console.print(f"[info]→[/info] {msg}")


def ok(msg: str) -> None:
    console.print(f"[ok]✓[/ok] {msg}")


def warn(msg: str) -> None:
    console.print(f"[warn]![/warn] {msg}")


def error(msg: str) -> None:
    console.print(f"[err]✗[/err] {msg}")


def die(msg: str, code: int = 1) -> None:
    error(msg)
    sys.exit(code)


def ask_text(prompt: str, default: str | None = None) -> str:
    answer = questionary.text(prompt, default=default or "").ask()
    if answer is None:
        die("Cancelado.")
    return answer.strip()


def ask_password(prompt: str) -> str:
    answer = questionary.password(prompt).ask()
    if answer is None:
        die("Cancelado.")
    return answer


def ask_select(prompt: str, choices: Sequence[str]) -> str:
    answer = questionary.select(prompt, choices=list(choices)).ask()
    if answer is None:
        die("Cancelado.")
    return answer


def ask_confirm(prompt: str, default: bool = False) -> bool:
    answer = questionary.confirm(prompt, default=default).ask()
    if answer is None:
        die("Cancelado.")
    return answer
