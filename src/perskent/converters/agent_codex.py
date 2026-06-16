"""Codex agent converter: canonical markdown <-> a single TOML file.

Codex agents live at `agents/<name>.toml` (flat table) with required
`name`/`description`/`developer_instructions` and optional `model`/
`model_reasoning_effort`/`sandbox_mode`/`nickname_candidates`
(verified: developers.openai.com/codex/subagents, mid-2026).

Canonical form is `agents/<name>.md` (frontmatter + body). The body IS the
`developer_instructions`. Codex-only fields are stashed in the canonical
frontmatter under `x-codex-*` so a codex->claude->codex round-trip preserves
them. This is a SINGLE-FILE converter: supporting files (templates/, extra md)
have no home in Codex and are dropped with a warning.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from perskent.converters.base import (
    AGENT_KEY_ORDER,
    Artifact,
    ConvertResult,
    DestLayout,
    build_frontmatter,
    dump_toml,
    ordered_fm,
    parse_frontmatter,
    parse_toml,
    synth_description,
)

_X_REASONING = "x-codex-reasoning"
_X_SANDBOX = "x-codex-sandbox"
_X_NICKNAMES = "x-codex-nicknames"
_CANON_ORDER = AGENT_KEY_ORDER + (_X_REASONING, _X_SANDBOX, _X_NICKNAMES)


class CodexAgentConverter:
    env = "codex"
    kind = "agent"

    def dest_layout(self, name: str) -> DestLayout:
        return DestLayout(
            primary=f"agents/{name}.toml",
            is_single_file=True,
            glob_roots=(f"agents/{name}.toml",),
        )

    def _canon_primary(self, name: str) -> str:
        return f"agents/{name}.md"

    def _toml_primary(self, name: str) -> str:
        return f"agents/{name}.toml"

    def to_canonical(self, art: Artifact) -> ConvertResult:
        """codex .toml -> canonical .md"""
        toml_path = self._toml_primary(art.name)
        raw = art.files.get(toml_path)
        if raw is None:
            # Be forgiving: take the only file present.
            raw = next(iter(art.files.values()), b"")
        data = parse_toml(raw) if raw.strip() else {}
        fm: dict = {}
        if data.get("name"):
            fm["name"] = data["name"]
        else:
            fm["name"] = art.name
        if data.get("description"):
            fm["description"] = data["description"]
        if data.get("model"):
            fm["model"] = data["model"]
        if data.get("model_reasoning_effort"):
            fm[_X_REASONING] = data["model_reasoning_effort"]
        if data.get("sandbox_mode"):
            fm[_X_SANDBOX] = data["sandbox_mode"]
        if data.get("nickname_candidates"):
            fm[_X_NICKNAMES] = data["nickname_candidates"]
        body = (data.get("developer_instructions") or "").encode("utf-8")
        md = build_frontmatter(ordered_fm(fm, _CANON_ORDER), body)
        return ConvertResult(files={self._canon_primary(art.name): md})

    def from_canonical(self, art: Artifact) -> ConvertResult:
        """canonical .md -> codex .toml (single file; supporting files dropped)"""
        canon_path = self._canon_primary(art.name)
        raw = art.files.get(canon_path)
        warnings: list[str] = []
        dropped: list[str] = []
        if raw is None:
            raw = next(
                (v for k, v in art.files.items() if PurePosixPath(k).suffix == ".md"),
                b"",
            )
        fm, body = parse_frontmatter(raw)
        fm = fm or {}

        for rel in art.files:
            if rel != canon_path:
                dropped.append(rel)
        if dropped:
            warnings.append(
                f"agents/{art.name}: Codex agents are a single TOML file — dropped "
                f"{len(dropped)} supporting file(s): {', '.join(sorted(dropped))}."
            )
        if fm.get("tools"):
            warnings.append(
                f"agents/{art.name}: 'tools' has no Codex equivalent — dropped."
            )

        toml: dict = {
            "name": fm.get("name") or art.name,
            "description": fm.get("description") or synth_description(body, art.name),
            "developer_instructions": body.decode("utf-8", "replace"),
        }
        if fm.get("model"):
            toml["model"] = fm["model"]
        if fm.get(_X_REASONING):
            toml["model_reasoning_effort"] = fm[_X_REASONING]
        if fm.get(_X_SANDBOX):
            toml["sandbox_mode"] = fm[_X_SANDBOX]
        if fm.get(_X_NICKNAMES):
            toml["nickname_candidates"] = fm[_X_NICKNAMES]

        # Deterministic key order for stable output.
        ordered = {k: toml[k] for k in (
            "name", "description", "model", "model_reasoning_effort",
            "sandbox_mode", "nickname_candidates", "developer_instructions",
        ) if k in toml}
        return ConvertResult(
            files={self._toml_primary(art.name): dump_toml(ordered)},
            warnings=warnings,
            dropped=dropped,
        )
