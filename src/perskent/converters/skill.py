"""Skill converter — SKILL.md is a shared standard across code-agents.

Skills copy verbatim, with one functional adjustment: a code-agent only
*auto-discovers* a skill whose SKILL.md carries YAML frontmatter
(`name`/`description`). A skill authored for Claude and loaded by path may have
none. So `from_canonical` injects a minimal, marker-tagged block for every
target EXCEPT Claude (the canonical/authoring env, kept pristine), and
`to_canonical` strips any block WE injected. Author frontmatter is untouched.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from perskent.converters.base import (
    Artifact,
    ConvertResult,
    DestLayout,
    has_frontmatter,
    inject_skill_frontmatter,
    strip_auto,
)

CANONICAL_ENV = "claude"


class SkillConverter:
    kind = "skill"

    def __init__(self, env: str) -> None:
        self.env = env

    def dest_layout(self, name: str) -> DestLayout:
        return DestLayout(
            primary=f"skills/{name}/SKILL.md",
            is_single_file=False,
            glob_roots=(f"skills/{name}",),
        )

    def _skill_doc(self, art: Artifact) -> str | None:
        for rel in art.files:
            if PurePosixPath(rel).name == "SKILL.md":
                return rel
        return None

    def to_canonical(self, art: Artifact) -> ConvertResult:
        out = dict(art.files)
        doc = self._skill_doc(art)
        if doc is not None:
            out[doc] = strip_auto(out[doc])
        return ConvertResult(files=out)

    def from_canonical(self, art: Artifact) -> ConvertResult:
        out = dict(art.files)
        warnings: list[str] = []
        doc = self._skill_doc(art)
        if doc is not None and self.env != CANONICAL_ENV:
            data = out[doc]
            if not has_frontmatter(data):
                if not data.strip():
                    warnings.append(f"skills/{art.name}: empty SKILL.md body.")
                out[doc] = inject_skill_frontmatter(data, art.name)
        elif doc is not None:
            # Canonical env: keep pristine (strip any leftover injected block).
            out[doc] = strip_auto(out[doc])
        return ConvertResult(files=out, warnings=warnings)
