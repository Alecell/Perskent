"""Git operations via subprocess.

Supports two URL schemes:
- SSH (git@host:..., ssh://...) — auth via ssh-agent / user's SSH key.
- HTTPS — auth via PAT injected dynamically through GIT_ASKPASS.

The token is NEVER written to a persistent file nor to .git/config: it's
injected into the git subprocess's environment via a temporary askpass
script that reads from PSKT_USERNAME / PSKT_TOKEN.
"""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


def is_https(url: str) -> bool:
    return url.startswith(("https://", "http://"))


def is_ssh(url: str) -> bool:
    return url.startswith(("git@", "ssh://"))


def detect_auth_method(url: str) -> str:
    if is_https(url):
        return "https"
    if is_ssh(url):
        return "ssh"
    raise GitError(
        f"Unrecognized URL scheme: {url!r}. "
        "Use HTTPS (https://...) or SSH (git@host:...)."
    )


@dataclass
class _AskpassContext:
    script_path: Path
    env: dict[str, str]


_ASKPASS_SCRIPT = """#!/bin/sh
case "$1" in
  *Username*|*username*) echo "${PSKT_USERNAME}" ;;
  *Password*|*password*) echo "${PSKT_TOKEN}" ;;
  *) echo "${PSKT_TOKEN}" ;;
esac
"""


def _make_askpass(token: str, username: str = "x-access-token") -> _AskpassContext:
    fd, path = tempfile.mkstemp(prefix="pskt-askpass-", suffix=".sh")
    os.close(fd)
    script = Path(path)
    script.write_text(_ASKPASS_SCRIPT)
    script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    env = os.environ.copy()
    env["GIT_ASKPASS"] = str(script)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["PSKT_USERNAME"] = username
    env["PSKT_TOKEN"] = token
    return _AskpassContext(script_path=script, env=env)


def _cleanup_askpass(ctx: _AskpassContext | None) -> None:
    if ctx is None:
        return
    try:
        ctx.script_path.unlink(missing_ok=True)
    except OSError:
        pass


def _build_env(url: str, token: str | None) -> tuple[dict | None, _AskpassContext | None]:
    """Returns (env, ctx) — caller must clean up `ctx` afterwards."""
    if is_https(url) and token:
        ctx = _make_askpass(token)
        return ctx.env, ctx
    return None, None


def _run(
    args: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GitError("git is not installed or not in PATH.") from e
    if check and result.returncode != 0:
        msg = (result.stderr or result.stdout or f"git failed (rc={result.returncode})").strip()
        raise GitError(msg)
    return result


def git_version() -> str | None:
    try:
        result = _run(["--version"])
    except GitError:
        return None
    return result.stdout.strip() or None


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def ls_remote(url: str, token: str | None = None) -> None:
    """Test reachability and auth against the remote. Raises GitError on failure."""
    env, ctx = _build_env(url, token)
    try:
        _run(["ls-remote", url], env=env)
    finally:
        _cleanup_askpass(ctx)


def clone(url: str, dest: Path, token: str | None = None) -> None:
    """Clone the registry into `dest`. Fails if `dest` exists and is non-empty."""
    if dest.exists() and any(dest.iterdir()):
        raise GitError(f"Destination '{dest}' already exists and is not empty.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    env, ctx = _build_env(url, token)
    try:
        _run(["clone", url, str(dest)], env=env)
    finally:
        _cleanup_askpass(ctx)


def pull(repo: Path, url: str, token: str | None = None) -> None:
    """git pull --ff-only on the given repo."""
    env, ctx = _build_env(url, token)
    try:
        _run(["pull", "--ff-only"], cwd=repo, env=env)
    finally:
        _cleanup_askpass(ctx)


def head_commit(repo: Path) -> str | None:
    """Return the HEAD SHA, or None if the repo has no commits yet."""
    try:
        result = _run(["rev-parse", "HEAD"], cwd=repo)
    except GitError:
        return None
    sha = result.stdout.strip()
    return sha or None


def commits_between(repo: Path, old: str, new: str) -> int:
    """Count commits between two SHAs (old..new)."""
    result = _run(["rev-list", "--count", f"{old}..{new}"], cwd=repo)
    try:
        return int(result.stdout.strip())
    except ValueError as e:
        raise GitError(f"unexpected rev-list output: {result.stdout!r}") from e


def status_porcelain(repo: Path, path_filter: str | None = None) -> list[str]:
    """Return lines from `git status --porcelain` (filtered to a path if given)."""
    args = ["status", "--porcelain"]
    if path_filter:
        args.extend(["--", path_filter])
    result = _run(args, cwd=repo)
    return [line for line in result.stdout.splitlines() if line.strip()]


def add(repo: Path, path: str) -> None:
    """git add <path>."""
    _run(["add", "--", path], cwd=repo)


def commit(repo: Path, message: str) -> None:
    """git commit -m <message>. Fails clearly if user.name/email is not configured."""
    _run(["commit", "-m", message], cwd=repo)


def push(repo: Path, url: str, token: str | None = None, *, branch: str = "main") -> None:
    """git push origin HEAD:<branch>.

    Uses HEAD:<branch> to be explicit about the destination even in repos
    that were just cloned and don't have a properly configured upstream.
    """
    env, ctx = _build_env(url, token)
    try:
        _run(["push", "origin", f"HEAD:{branch}"], cwd=repo, env=env)
    finally:
        _cleanup_askpass(ctx)


def git_config_value(key: str, repo: Path | None = None) -> str | None:
    """Read a git config value. Returns None if unset."""
    args = ["config", "--get", key]
    try:
        result = _run(args, cwd=repo, check=False)
    except GitError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None
