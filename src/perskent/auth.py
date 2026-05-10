"""Token storage for the remote registry.

Tries the OS keyring first:
- Linux:   Secret Service (GNOME Keyring, KWallet)
- macOS:   Keychain
- Windows: Credential Manager

If no keyring backend is available (common on WSL2 without gnome-keyring,
containers, headless SSH hosts without D-Bus), falls back to a file at
~/.config/pskt/token with mode 600. Less secure than a native keyring,
but works in any environment — preferable to breaking `init`.
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
    """Store the token. Returns 'keyring' if it landed in the OS keyring, or 'file' if it fell back."""
    if _try_keyring_set(token):
        _file_delete()  # ensure no stale fallback is left behind
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
    """Where the token is stored: 'keyring', 'file', or 'none'."""
    ok, value = _try_keyring_get()
    if ok and value is not None:
        return "keyring"
    if _file_get() is not None:
        return "file"
    return "none"
