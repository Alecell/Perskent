"""pskt self-update — fetch the latest perskent release and apply it.

Checks PyPI for the latest version, compares with the running build, and
runs the upgrade command that matches how the CLI was installed (pipx or
pip). Sits between the user and the underlying packaging tool so they
don't have to remember which command applies to their setup.

On Linux/macOS overwriting a running Python script is safe (open file
descriptors keep working); the same call on Windows can fail because the
interpreter holds an exclusive lock on the executable. Perskent has no
explicit Windows path today, so this command targets POSIX behavior.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from perskent import __version__, ui


_PYPI_URL = "https://pypi.org/pypi/perskent/json"
_PIPX_MARKER = "pipx/venvs/perskent"


def _latest_version_from_pypi(timeout: float = 5.0) -> str | None:
    """Fetch the latest released version from PyPI; None on any failure."""
    req = urllib.request.Request(_PYPI_URL, headers={"User-Agent": "perskent-self-update"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    version = data.get("info", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        return None
    return version.strip()


def _version_tuple(v: str) -> tuple[int, ...]:
    """Compare semver-ish versions by their numeric components.

    `0.7.0` → (0, 7, 0); non-numeric tails are dropped. Good enough for
    perskent's strict semver releases."""
    parts: list[int] = []
    for chunk in v.split("."):
        if not chunk.isdigit():
            break
        parts.append(int(chunk))
    return tuple(parts)


def _detect_install_method() -> tuple[str, list[str]]:
    """Return (label, command_argv) for the upgrade command.

    `label` is for human display; `command_argv` is what subprocess runs.

    Detection: `sys.executable` and `sys.prefix` for a pipx-managed CLI both
    point at `~/.local/share/pipx/venvs/perskent/...`. `Path.resolve()` is
    avoided here because pipx's `python` binary is a symlink to the system
    interpreter — resolving it would erase the very marker we need.
    """
    candidates = [sys.executable, sys.prefix, str(Path(__file__).resolve())]
    for c in candidates:
        if c and _PIPX_MARKER in c:
            return "pipx", ["pipx", "upgrade", "perskent"]
    return "pip", [sys.executable, "-m", "pip", "install", "--upgrade", "perskent"]


def run() -> None:
    ui.info(f"Current version: {__version__}")
    ui.info("Checking PyPI for the latest release...")
    latest = _latest_version_from_pypi()
    if latest is None:
        ui.warn(
            "Could not reach PyPI (network down or service unavailable). "
            "Try again later, or upgrade manually with `pipx upgrade perskent`."
        )
        return

    try:
        current_t = _version_tuple(__version__)
        latest_t = _version_tuple(latest)
    except ValueError:
        ui.die(f"Cannot compare versions: current={__version__!r}, latest={latest!r}.")

    if current_t and latest_t and latest_t <= current_t:
        ui.ok(f"Already on the latest release (v{__version__}).")
        return

    ui.info(f"New version available: v{__version__} → v{latest}")

    method, command = _detect_install_method()
    if method == "pipx":
        ui.info("Detected pipx installation.")
    else:
        ui.info(f"Detected pip installation (interpreter: {sys.executable}).")
    ui.info("Will run: " + " ".join(command))

    if not ui.ask_confirm("Proceed with upgrade?", default=True):
        ui.info("Cancelled.")
        return

    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError:
        if method == "pipx":
            ui.die(
                "pipx is not in PATH but the CLI was installed via pipx. "
                "Install pipx (https://pipx.pypa.io) or upgrade manually with:\n"
                f"  {sys.executable} -m pip install --upgrade perskent"
            )
        ui.die(
            "Could not execute the upgrade command. Try manually:\n"
            f"  {' '.join(command)}"
        )
        return

    if result.returncode != 0:
        ui.die(f"Upgrade command exited with status {result.returncode}.")

    ui.ok(f"Upgraded perskent to v{latest}. Run `pskt --version` in a new shell to confirm.")
