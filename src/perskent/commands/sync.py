"""pskt sync — git pull no workspace local."""
from __future__ import annotations

from perskent import auth, config, git_ops, ui
from perskent.paths import workspace_dir


def run() -> None:
    if not config.exists():
        ui.die("perskent não inicializado. Rode `pskt init` primeiro.")
    cfg = config.load()
    assert cfg is not None  # exists() já garantiu

    ws = workspace_dir()
    if not ws.exists() or not git_ops.is_git_repo(ws):
        ui.die(f"Workspace ausente em {ws}. Rode `pskt init --force` pra reconfigurar.")

    token = auth.get_token() if cfg.auth_method == "https" else None

    ui.info(f"Sincronizando registry em {ws}...")
    before = git_ops.head_commit(ws)

    try:
        git_ops.pull(ws, cfg.registry_url, token=token)
    except git_ops.GitError as e:
        # Caso comum: repo recém-criado no GitHub, ainda sem commits → pull falha sem upstream.
        # Não é erro fatal, é só "nada pra puxar ainda".
        if before is None:
            ui.warn(
                "Registry remoto está vazio (nenhum commit ainda). "
                "Crie pacotes em ~/.pskt/<agents|skills|commands>/<nome>/ "
                "e dê push (disponível na próxima fase)."
            )
            return
        ui.die(f"Falha no pull:\n  {e}")

    after = git_ops.head_commit(ws)

    if before is None and after is None:
        ui.warn("Registry remoto está vazio.")
        return
    if before is None:
        ui.ok(f"Registry sincronizado pela primeira vez (HEAD: {after[:7]}).")
        return
    if before == after:
        ui.ok("Já está atualizado.")
        return

    try:
        count = git_ops.commits_between(ws, before, after)
        ui.ok(f"Sincronizado: {count} commit(s) novo(s).")
    except git_ops.GitError:
        ui.ok("Sincronizado.")
