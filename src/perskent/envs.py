"""Code-agent environments: which ones we support and where their files live.

A perskent install copies a package's files 1:1 under a destination directory.
That destination depends on which code-agent the user has configured for the
scope (root/project). This module owns that mapping.

Conventions:
- `base_relative(env, scope)` — the env's canonical base dir, relative to the
  scope's anchor (home dir for root, project root for project). Used as the
  home of the per-scope `.pskt-installed.toml`.
- `dest_relative(env, scope, kind)` — where files of a given kind are written.
  Equals `base_relative` for most (env, kind) pairs; the exceptions are
  per-env quirks (e.g. Codex skills live in `.agents/skills/`, outside `.codex/`).
- `SUPPORTED_KINDS` lists the kinds each env consumes as plain files. Kinds
  that the env only accepts inline in a config file (e.g. Codex subagents,
  declared in `config.toml`) are intentionally left out — perskent does not
  edit config files.
"""
from __future__ import annotations

import shutil

ENV_CLAUDE = "claude"
ENV_OPENCODE = "opencode"
ENV_QWEN = "qwen"
ENV_CODEX = "codex"
ENV_CURSOR = "cursor"
ENV_ZED = "zed"
ENV_CLINE = "cline"
ENV_GEMINI = "gemini"

ENVS: tuple[str, ...] = (
    ENV_CLAUDE,
    ENV_OPENCODE,
    ENV_QWEN,
    ENV_CODEX,
    ENV_CURSOR,
    ENV_ZED,
    ENV_CLINE,
    ENV_GEMINI,
)

_BASE: dict[str, dict[str, str]] = {
    ENV_CLAUDE:   {"root": ".claude",          "project": ".claude"},
    ENV_OPENCODE: {"root": ".config/opencode", "project": ".opencode"},
    ENV_QWEN:     {"root": ".qwen",            "project": ".qwen"},
    ENV_CODEX:    {"root": ".codex",           "project": ".codex"},
    # Cursor mirrors Claude's layout: agents/, skills/, commands/ live directly
    # under .cursor/ (project) and ~/.cursor/ (root). Its `rules/` dir holds a
    # different concept (always-on guidelines), which perskent does not model.
    ENV_CURSOR:   {"root": ".cursor",          "project": ".cursor"},
    # Zed reads skills from ~/.agents/skills (root) and <project>/.agents/skills
    # — the cross-tool `.agents/skills/SKILL.md` convention it shares with Codex.
    # Only skills are file-based; agent profiles live in settings.json (inline).
    ENV_ZED:      {"root": ".agents",          "project": ".agents"},
    # Cline reads skills from ~/.cline/skills and <project>/.cline/skills.
    # Its rules/workflows use other folder names (.clinerules/) that don't map
    # to perskent's agents/skills/commands layout, so only skills are modelled.
    ENV_CLINE:    {"root": ".cline",           "project": ".cline"},
    # Gemini CLI reads custom commands from ~/.gemini/commands and
    # <project>/.gemini/commands — same `commands/` folder name perskent uses.
    # (Gemini command files are TOML; making a package cross-compatible is the
    # package author's job — perskent replicates verbatim.)
    ENV_GEMINI:   {"root": ".gemini",          "project": ".gemini"},
}

# (env, kind) → override for the destination dir. Falls back to _BASE otherwise.
_KIND_OVERRIDE: dict[tuple[str, str], dict[str, str]] = {
    (ENV_CODEX, "skill"): {"root": ".agents", "project": ".agents"},
}

SUPPORTED_KINDS: dict[str, frozenset[str]] = {
    ENV_CLAUDE:   frozenset({"agent", "skill", "command"}),
    ENV_OPENCODE: frozenset({"agent", "skill", "command"}),
    ENV_QWEN:     frozenset({"agent", "skill", "command"}),
    ENV_CODEX:    frozenset({"skill"}),
    ENV_CURSOR:   frozenset({"agent", "skill", "command"}),
    ENV_ZED:      frozenset({"skill"}),
    ENV_CLINE:    frozenset({"skill"}),
    ENV_GEMINI:   frozenset({"command"}),
}

_BIN_NAMES: dict[str, str] = {
    ENV_CLAUDE: "claude",
    ENV_OPENCODE: "opencode",
    ENV_QWEN: "qwen",
    ENV_CODEX: "codex",
    ENV_CURSOR: "cursor",
    ENV_ZED: "zed",
    ENV_CLINE: "cline",
    ENV_GEMINI: "gemini",
}


def is_valid(env: str) -> bool:
    return env in ENVS


def supports_kind(env: str, kind: str) -> bool:
    return kind in SUPPORTED_KINDS.get(env, frozenset())


def base_relative(env: str, scope: str) -> str:
    """Relative path of the env's canonical base dir for the given scope."""
    return _BASE[env][scope]


def dest_relative(env: str, scope: str, kind: str) -> str:
    """Relative path where files of `kind` are written for (env, scope).

    Equals base_relative except when an env scatters a particular kind outside
    its base dir (e.g. Codex skills live in `.agents/skills/`).
    """
    override = _KIND_OVERRIDE.get((env, kind))
    if override is not None:
        return override[scope]
    return _BASE[env][scope]


def detect_installed() -> list[str]:
    """Envs whose CLI binary is present on PATH, in the canonical ENVS order."""
    return [env for env in ENVS if shutil.which(_BIN_NAMES[env])]
