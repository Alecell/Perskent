"""pskt init — configura registry remoto e clona o workspace local."""
from __future__ import annotations

import shutil

import typer

from perskent import auth, config, git_ops, ui
from perskent.paths import config_file, workspace_dir


def run(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Reconfigura mesmo se já estiver inicializado (apaga clone local e token).",
    ),
) -> None:
    if config.exists() and not force:
        ui.warn("perskent já está inicializado.")
        if not ui.ask_confirm(
            "Reconfigurar do zero? Isso vai apagar o clone local em ~/.pskt/ e remover o token.",
            default=False,
        ):
            ui.info("Cancelado, nada foi alterado.")
            raise typer.Exit()
        force = True

    if force:
        ws = workspace_dir()
        if ws.exists():
            ui.info(f"Removendo clone existente em {ws}...")
            shutil.rmtree(ws, ignore_errors=True)
        if auth.has_token():
            auth.delete_token()
        if config.exists():
            config.delete()

    ui.info("Configurando o registry remoto.")
    url = ui.ask_text("URL do repositório (HTTPS ou SSH)")
    if not url:
        ui.die("URL não pode ser vazia.")

    try:
        method = git_ops.detect_auth_method(url)
    except git_ops.GitError as e:
        ui.die(str(e))

    token: str | None = None
    if method == "https":
        ui.info(
            "URL HTTPS detectada — token de acesso será pedido (PAT do GitHub, deploy key, etc)."
        )
        token = ui.ask_password("Token de acesso (será salvo no keyring do OS)")
        if not token:
            ui.die("Token não pode ser vazio quando o repositório é HTTPS.")
    else:
        ui.info("URL SSH detectada — autenticação delegada ao ssh-agent / chave SSH do sistema.")

    ui.info("Testando acesso ao registry...")
    try:
        git_ops.ls_remote(url, token=token)
    except git_ops.GitError as e:
        ui.die(f"Falha ao acessar o registry:\n  {e}")
    ui.ok("Registry remoto acessível.")

    if method == "https":
        assert token is not None
        storage = auth.set_token(token)
        if storage == "keyring":
            ui.ok("Token salvo no keyring do OS.")
        else:
            ui.warn(
                f"Keyring do OS indisponível neste ambiente — token salvo em "
                f"{auth.token_file_path()} (chmod 600)."
            )

    config.save(config.Config(registry_url=url, auth_method=method))
    ui.ok(f"Configuração salva em {config_file()}.")

    ui.info(f"Clonando registry em {workspace_dir()}...")
    try:
        git_ops.clone(url, workspace_dir(), token=token)
    except git_ops.GitError as e:
        ui.die(f"Falha ao clonar:\n  {e}")
    ui.ok(f"Workspace clonado em {workspace_dir()}.")

    ui.console.print()
    ui.console.print(
        "[ok bold]Pronto![/ok bold] Use [info]pskt find remote[/info] pra listar pacotes "
        "(disponível na próxima fase)."
    )
