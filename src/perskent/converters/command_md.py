"""Markdown command converters.

claude/opencode/qwen all express custom commands as `commands/<name>.md` where
the body is the prompt template (opencode's `template`/qwen's body are the same
markdown body). Canonicalization normalizes frontmatter key order; bodies pass
through verbatim. Argument-placeholder dialects differ across tools
($ARGUMENTS vs {{args}}) but rewriting them risks corruption, so they are left
as-is (the package author owns cross-tool placeholder compatibility).
"""
from __future__ import annotations

from perskent.converters.base import (
    COMMAND_KEY_ORDER,
    Artifact,
    ConvertResult,
    DestLayout,
    normalize_md,
)


class MarkdownCommandConverter:
    kind = "command"

    def __init__(self, env: str) -> None:
        self.env = env

    def dest_layout(self, name: str) -> DestLayout:
        return DestLayout(
            primary=f"commands/{name}.md",
            is_single_file=False,
            glob_roots=(f"commands/{name}.md", f"commands/{name}"),
        )

    def _primary(self, name: str) -> str:
        return f"commands/{name}.md"

    def _normalize(self, art: Artifact) -> dict[str, bytes]:
        out = dict(art.files)
        prim = self._primary(art.name)
        if prim in out:
            out[prim] = normalize_md(out[prim], COMMAND_KEY_ORDER)
        return out

    def to_canonical(self, art: Artifact) -> ConvertResult:
        return ConvertResult(files=self._normalize(art))

    def from_canonical(self, art: Artifact) -> ConvertResult:
        return ConvertResult(files=self._normalize(art))
