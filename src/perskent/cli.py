"""Entry point Typer do CLI `pskt` / `perskent`."""
from __future__ import annotations

import typer

from perskent import __version__
from perskent.commands import doctor as doctor_cmd
from perskent.commands import find as find_cmd
from perskent.commands import init as init_cmd
from perskent.commands import install as install_cmd
from perskent.commands import remove as remove_cmd
from perskent.commands import search as search_cmd
from perskent.commands import show as show_cmd
from perskent.commands import sync as sync_cmd
from perskent.commands import update as update_cmd

app = typer.Typer(
    name="pskt",
    help="Gerenciador de skills, agents e commands do Claude Code via Git privado.",
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
        help="Mostra a versão e sai.",
    ),
) -> None:
    """perskent — gerenciador de pacotes pro Claude Code."""


app.command(
    "init",
    help="Configura o registry remoto (URL + token) e clona o workspace local em ~/.pskt/.",
)(init_cmd.run)

app.command(
    "doctor",
    help="Diagnóstico do ambiente: git, paths, token, conectividade do registry.",
)(doctor_cmd.run)

app.command(
    "sync",
    help="Sincroniza ~/.pskt/ com o registry remoto (git pull).",
)(sync_cmd.run)

app.add_typer(find_cmd.find_app)

app.command(
    "show",
    help="Mostra detalhes de um pacote do registry.",
)(show_cmd.run)

app.command(
    "search",
    help="Busca pacotes por nome ou descrição.",
)(search_cmd.run)

app.command(
    "install",
    help="Instala um pacote em ~/.claude/ (root) ou ./.claude/ (project).",
)(install_cmd.run)

app.command(
    "remove",
    help="Remove um pacote instalado.",
)(remove_cmd.run)

app.command(
    "update",
    help="Atualiza pacote pra última versão do registry, preservando arquivos marcados em [update].preserve.",
)(update_cmd.run)
