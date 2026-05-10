"""pskt push <name> — bump + commit + push de um pacote.

Fluxo:
1. Resolve o pacote (com kind disambig).
2. Se a pasta não tem `manifest.toml`, gera um interativamente (description,
   author, version inicial 0.1.0). Caso contrário, mostra git changes do
   pacote e pergunta bump (patch/minor/major/no bump).
3. Atualiza `version` no manifest in-place via regex (preserva comments).
4. git add `<kind>s/<name>/` + git commit + git push (askpass HTTPS).
"""
from __future__ import annotations

import re
from pathlib import Path

import typer

from perskent import auth, config, git_ops, ui
from perskent import manifest as manifest_mod
from perskent.paths import workspace_dir
from perskent.registry_scan import KIND_FOLDERS, KIND_SINGULAR


def _resolve_package_dir(query: str) -> tuple[Path, str, str]:
    """Resolve `<name>` ou `<kind>s/<name>` em (path, kind_singular, name).

    Aceita pasta existente sem manifest (pra criar um na hora).
    """
    ws = workspace_dir()

    if "/" in query:
        kind_folder, _, name = query.partition("/")
        if kind_folder not in KIND_FOLDERS:
            ui.die(
                f"Kind inválido: {kind_folder!r}. Use {' | '.join(KIND_FOLDERS)}."
            )
        pkg_dir = ws / kind_folder / name
        if not pkg_dir.is_dir():
            ui.die(
                f"Pasta '{pkg_dir}' não existe. Crie o pacote primeiro:\n"
                f"  mkdir -p {pkg_dir}"
            )
        return pkg_dir, KIND_SINGULAR[kind_folder], name

    matches: list[tuple[Path, str]] = []
    for kind_folder in KIND_FOLDERS:
        candidate = ws / kind_folder / query
        if candidate.is_dir():
            matches.append((candidate, KIND_SINGULAR[kind_folder]))

    if not matches:
        ui.die(
            f"Pacote '{query}' não existe no workspace. "
            "Crie ~/.pskt/<agents|skills|commands>/<nome>/ primeiro."
        )
    if len(matches) > 1:
        ui.warn(f"'{query}' é ambíguo — existe em múltiplos kinds:")
        for path, kind in matches:
            ui.console.print(f"  [muted]→[/muted] {kind}s/{query}")
        ui.die("Use o nome qualificado, ex.: `pskt push agents/<nome>`.")

    pkg_dir, kind = matches[0]
    return pkg_dir, kind, query


def _bump(version: str, level: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"versão não-semver: {version!r}")
    try:
        major, minor, patch = (int(p) for p in parts)
    except ValueError as e:
        raise ValueError(f"versão não-semver: {version!r}") from e
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "major":
        return f"{major + 1}.0.0"
    raise ValueError(f"level desconhecido: {level!r}")


def _replace_version_inplace(manifest_path: Path, new_version: str) -> None:
    """Substitui `version = "..."` via regex, preservando comments/format."""
    content = manifest_path.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'^(version\s*=\s*)"[^"]*"',
        rf'\1"{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise RuntimeError(
            f"não consegui localizar `version = \"...\"` em {manifest_path}"
        )
    manifest_path.write_text(new_content, encoding="utf-8")


def _generate_manifest(pkg_dir: Path, name: str, kind: str) -> None:
    """Cria manifest.toml interativamente pra pacote novo."""
    ui.info(f"Pacote {kind}s/{name} sem manifest.toml — vou criar um.")
    default_author = git_ops.git_config_value("user.name", repo=workspace_dir()) or ""

    version = ui.ask_text("Versão inicial", default="0.1.0").strip() or "0.1.0"
    description = ui.ask_text("Descrição (1 linha)").strip()
    author = ui.ask_text("Autor", default=default_author).strip()

    lines = ["[package]", f'name = "{name}"', f'version = "{version}"']
    if description:
        # Escape simples de aspas duplas dentro da string
        safe_desc = description.replace('"', '\\"')
        lines.append(f'description = "{safe_desc}"')
    if author:
        safe_author = author.replace('"', '\\"')
        lines.append(f'author = "{safe_author}"')

    content = "\n".join(lines) + "\n"
    manifest_path = pkg_dir / "manifest.toml"
    manifest_path.write_text(content, encoding="utf-8")
    ui.ok(f"manifest.toml criado: {manifest_path}")


def run(
    name: str = typer.Argument(
        ...,
        help="Nome do pacote (ou <kind>s/<name> pra desambiguar)",
    ),
    message: str = typer.Option(
        None,
        "--message",
        "-m",
        help="Mensagem de commit (default: '<kind>s/<name> v<version>')",
    ),
) -> None:
    if not config.exists():
        ui.die("perskent não inicializado. Rode `pskt init` primeiro.")
    cfg = config.load()
    assert cfg is not None

    pkg_dir, kind, pkg_name = _resolve_package_dir(name)
    rel_path = pkg_dir.relative_to(workspace_dir())
    manifest_path = pkg_dir / "manifest.toml"

    try:
        changes = git_ops.status_porcelain(workspace_dir(), str(rel_path))
    except git_ops.GitError as e:
        ui.die(f"Falha ao ler status do workspace: {e}")

    has_manifest = manifest_path.exists()

    if has_manifest and not changes:
        ui.warn(
            f"Nenhuma mudança detectada em {kind}s/{pkg_name}. Nada a fazer."
        )
        return

    if not has_manifest:
        _generate_manifest(pkg_dir, pkg_name, kind)
    else:
        try:
            current_mf = manifest_mod.load(manifest_path)
        except manifest_mod.ManifestError as e:
            ui.die(f"manifest atual inválido: {e}")

        ui.console.print(f"[bold]Mudanças em {kind}s/{pkg_name}:[/bold]")
        for line in changes:
            ui.console.print(f"  [muted]{line}[/muted]")
        ui.console.print()

        try:
            choices_map = {
                "patch": _bump(current_mf.version, "patch"),
                "minor": _bump(current_mf.version, "minor"),
                "major": _bump(current_mf.version, "major"),
            }
        except ValueError as e:
            ui.die(f"manifest.toml tem versão inválida: {e}")

        labels = [
            f"patch  ({current_mf.version} → {choices_map['patch']})",
            f"minor  ({current_mf.version} → {choices_map['minor']})",
            f"major  ({current_mf.version} → {choices_map['major']})",
            f"no bump (mantém {current_mf.version})",
        ]
        choice = ui.ask_select("Bump version", choices=labels)

        if choice.startswith("patch"):
            new_version = choices_map["patch"]
        elif choice.startswith("minor"):
            new_version = choices_map["minor"]
        elif choice.startswith("major"):
            new_version = choices_map["major"]
        else:
            new_version = current_mf.version

        if new_version != current_mf.version:
            try:
                _replace_version_inplace(manifest_path, new_version)
            except RuntimeError as e:
                ui.die(str(e))
            ui.ok(f"version: {current_mf.version} → {new_version}")

    try:
        final_mf = manifest_mod.load(manifest_path)
    except manifest_mod.ManifestError as e:
        ui.die(f"manifest final inválido: {e}")
    default_message = f"{kind}s/{pkg_name} v{final_mf.version}"
    final_message = message or ui.ask_text("Commit message", default=default_message)
    if not final_message.strip():
        final_message = default_message

    ui.info(f"git add {rel_path}/")
    try:
        git_ops.add(workspace_dir(), str(rel_path))
    except git_ops.GitError as e:
        ui.die(f"git add falhou: {e}")

    ui.info("git commit...")
    try:
        git_ops.commit(workspace_dir(), final_message)
    except git_ops.GitError as e:
        ui.die(
            f"git commit falhou: {e}\n"
            "Se for por `user.name`/`user.email` ausente, configure com:\n"
            "  git config --global user.name \"Seu Nome\"\n"
            "  git config --global user.email \"voce@example.com\""
        )

    ui.info("git push origin HEAD:main...")
    token = auth.get_token() if cfg.auth_method == "https" else None
    try:
        git_ops.push(workspace_dir(), cfg.registry_url, token=token)
    except git_ops.GitError as e:
        ui.die(
            f"git push falhou: {e}\n"
            "O commit foi feito localmente. Resolva o motivo e rode "
            "`pskt push` de novo (vai detectar que não há mudanças e só "
            "subir o commit pendente — ou rode `git push` direto em ~/.pskt/)."
        )

    ui.ok(f"Pushed {kind}s/{pkg_name} v{final_mf.version}")
