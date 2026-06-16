"""Gemini command converter: canonical markdown <-> a single TOML file.

Gemini custom commands live at `commands/<name>.toml` with required `prompt`
and optional `description` (verified: google-gemini.github.io/gemini-cli, custom
commands, mid-2026). Canonical form is `commands/<name>.md`: the body is the
`prompt`, an optional frontmatter `description` carries over. SINGLE-FILE:
supporting files are dropped with a warning. Argument placeholders differ
(Claude `$ARGUMENTS` vs Gemini `{{args}}`) and are left as-is with a note.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from perskent.converters.base import (
    COMMAND_KEY_ORDER,
    Artifact,
    ConvertResult,
    DestLayout,
    build_frontmatter,
    dump_toml,
    ordered_fm,
    parse_frontmatter,
    parse_toml,
)


class GeminiCommandConverter:
    env = "gemini"
    kind = "command"

    def dest_layout(self, name: str) -> DestLayout:
        return DestLayout(
            primary=f"commands/{name}.toml",
            is_single_file=True,
            glob_roots=(f"commands/{name}.toml",),
        )

    def _canon(self, name: str) -> str:
        return f"commands/{name}.md"

    def _toml(self, name: str) -> str:
        return f"commands/{name}.toml"

    def to_canonical(self, art: Artifact) -> ConvertResult:
        raw = art.files.get(self._toml(art.name)) or next(iter(art.files.values()), b"")
        data = parse_toml(raw) if raw.strip() else {}
        body = (data.get("prompt") or "").encode("utf-8")
        fm: dict = {}
        if data.get("description"):
            fm["description"] = data["description"]
        md = build_frontmatter(ordered_fm(fm, COMMAND_KEY_ORDER), body) if fm else body
        return ConvertResult(files={self._canon(art.name): md})

    def from_canonical(self, art: Artifact) -> ConvertResult:
        canon = self._canon(art.name)
        raw = art.files.get(canon)
        warnings: list[str] = []
        dropped: list[str] = []
        if raw is None:
            raw = next(
                (v for k, v in art.files.items() if PurePosixPath(k).suffix == ".md"),
                b"",
            )
        for rel in art.files:
            if rel != canon:
                dropped.append(rel)
        if dropped:
            warnings.append(
                f"commands/{art.name}: Gemini commands are a single TOML file — dropped "
                f"{len(dropped)} supporting file(s): {', '.join(sorted(dropped))}."
            )
        fm, body = parse_frontmatter(raw)
        fm = fm or {}
        toml: dict = {}
        if fm.get("description"):
            toml["description"] = fm["description"]
        toml["prompt"] = body.decode("utf-8", "replace")
        ordered = {k: toml[k] for k in ("description", "prompt") if k in toml}
        return ConvertResult(
            files={self._toml(art.name): dump_toml(ordered)},
            warnings=warnings,
            dropped=dropped,
        )
