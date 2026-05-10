"""Armazenamento do token de acesso ao registry remoto.

Tenta primeiro o keyring do OS:
- Linux: Secret Service (GNOME Keyring, KWallet)
- macOS: Keychain
- Windows: Credential Manager

Se o ambiente não tiver um backend de keyring disponível (comum em WSL2 sem
gnome-keyring rodando, contêineres, hosts SSH sem D-Bus), faz fallback pra um
arquivo em ~/.config/pskt/token com permissão 600. Menos seguro que keyring
nativo, mas funciona em qualquer ambiente — preferível a quebrar o `init`.
"""
from __future__ import annotations

import stat
from pathlib import Path

import keyring
import keyring.errors

from perskent.paths import config_dir

SERVICE_NAME = "pskt"
TOKEN_KEY = "registry-token"


def token_file_path() -> Path:
    return config_dir() / "token"


# --- keyring backend ---------------------------------------------------------

def _try_keyring_set(token: str) -> bool:
    try:
        keyring.set_password(SERVICE_NAME, TOKEN_KEY, token)
        return True
    except (keyring.errors.NoKeyringError, keyring.errors.KeyringError, RuntimeError):
        return False


def _try_keyring_get() -> tuple[bool, str | None]:
    try:
        return True, keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    except (keyring.errors.NoKeyringError, keyring.errors.KeyringError, RuntimeError):
        return False, None


def _try_keyring_delete() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, TOKEN_KEY)
    except keyring.errors.PasswordDeleteError:
        pass
    except (keyring.errors.NoKeyringError, keyring.errors.KeyringError, RuntimeError):
        pass


# --- file fallback -----------------------------------------------------------

def _file_set(token: str) -> None:
    path = token_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass


def _file_get() -> str | None:
    path = token_file_path()
    if not path.exists():
        return None
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def _file_delete() -> None:
    path = token_file_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


# --- public API --------------------------------------------------------------

def set_token(token: str) -> str:
    """Salva o token. Retorna 'keyring' se conseguiu usar o keyring do OS, ou 'file' se caiu no fallback."""
    if _try_keyring_set(token):
        _file_delete()  # garante que não fica fallback velho
        return "keyring"
    _file_set(token)
    return "file"


def get_token() -> str | None:
    ok, value = _try_keyring_get()
    if ok and value is not None:
        return value
    return _file_get()


def delete_token() -> None:
    _try_keyring_delete()
    _file_delete()


def has_token() -> bool:
    return get_token() is not None


def storage_method() -> str:
    """Onde o token está armazenado: 'keyring', 'file', ou 'none'."""
    ok, value = _try_keyring_get()
    if ok and value is not None:
        return "keyring"
    if _file_get() is not None:
        return "file"
    return "none"
