"""Markdown agent converters.

claude/qwen/cursor all define agents as `agents/<name>.md` (YAML frontmatter +
system-prompt body). Canonicalization just normalizes the frontmatter to a
fixed key order so the SAME agent in any of these envs — or rebuilt from a
Codex .toml — yields byte-identical canonical bytes. Supporting files pass
through verbatim.
"""
from __future__ import annotations

from perskent.converters.base import (
    AGENT_KEY_ORDER,
    Artifact,
    ConvertResult,
    DestLayout,
    normalize_md,
    parse_frontmatter,
    build_frontmatter,
    ordered_fm,
    synth_description,
)

PRIMARY = "agents/{name}.md"


class MarkdownAgentConverter:
    kind = "agent"

    def __init__(self, env: str) -> None:
        self.env = env

    def dest_layout(self, name: str) -> DestLayout:
        return DestLayout(
            primary=PRIMARY.format(name=name),
            is_single_file=False,
            glob_roots=(f"agents/{name}.md", f"agents/{name}"),
        )

    def _primary(self, name: str) -> str:
        return PRIMARY.format(name=name)

    def to_canonical(self, art: Artifact) -> ConvertResult:
        out = dict(art.files)
        prim = self._primary(art.name)
        if prim in out:
            out[prim] = normalize_md(out[prim], AGENT_KEY_ORDER)
        return ConvertResult(files=out)

    def from_canonical(self, art: Artifact) -> ConvertResult:
        out = dict(art.files)
        prim = self._primary(art.name)
        if prim in out:
            out[prim] = normalize_md(out[prim], AGENT_KEY_ORDER)
        return ConvertResult(files=out)


class OpencodeAgentConverter(MarkdownAgentConverter):
    """opencode agents are markdown too, but require a `mode` field
    (primary|subagent|all) and a `description`. `mode` is opencode-specific, so
    it is dropped on the way to canonical and re-defaulted on the way back
    (a non-default mode does not survive a canonical pivot — warned)."""

    def to_canonical(self, art: Artifact) -> ConvertResult:
        out = dict(art.files)
        prim = self._primary(art.name)
        if prim in out:
            fm, body = parse_frontmatter(out[prim])
            if fm is not None:
                fm.pop("mode", None)
                out[prim] = build_frontmatter(ordered_fm(fm, AGENT_KEY_ORDER), body)
            else:
                out[prim] = normalize_md(out[prim], AGENT_KEY_ORDER)
        return ConvertResult(files=out)

    def from_canonical(self, art: Artifact) -> ConvertResult:
        out = dict(art.files)
        warnings: list[str] = []
        prim = self._primary(art.name)
        if prim in out:
            fm, body = parse_frontmatter(out[prim])
            fm = fm or {}
            if not fm.get("description"):
                fm["description"] = synth_description(body, art.name)
                warnings.append(
                    f"agents/{art.name}: opencode requires 'description' — synthesized one."
                )
            if not fm.get("mode"):
                fm["mode"] = "subagent"
                warnings.append(
                    f"agents/{art.name}: opencode requires 'mode' — defaulted to 'subagent'; set it manually if wrong."
                )
            ordered = ordered_fm(fm, AGENT_KEY_ORDER + ("mode",))
            out[prim] = build_frontmatter(ordered, body)
        return ConvertResult(files=out, warnings=warnings)
