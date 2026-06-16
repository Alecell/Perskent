"""Per-target content projection for cross-agent replication.

perskent copies artifacts verbatim, with ONE deliberate exception: Codex only
*auto-discovers* a skill when its `SKILL.md` carries YAML frontmatter
(`name` + `description`). A skill authored for another agent (e.g. a Claude
persona that is loaded by path) may have no frontmatter at all — copied
verbatim into `~/.codex/skills/`, Codex would not index it.

So when a skill flows **into** Codex without frontmatter, we synthesize a
minimal block and tag it with `AUTO_MARKER`. The marker makes the operation
reversible: if that same file ever flows back **out** to a non-Codex agent
(symmetric mirroring, codex picked as the newest copy), we strip our injected
block first, so the canonical copy elsewhere stays pristine. Author-written
frontmatter is never touched, in either direction.

`project(env, rel, data)` — what `env` should physically contain for `rel`.
`canonical(rel, data)` — content with any auto-injected block removed, used to
compare copies across agents without our own injection causing false diffs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from perskent import envs

# Sentinel placed inside the frontmatter we generate, so we can recognize (and
# undo) our own injection later. Authors are extremely unlikely to use it.
AUTO_MARKER = "pskt_auto_frontmatter"

# A YAML frontmatter block at the very start of the file: `---\n ... \n---\n`.
_FRONTMATTER_RE = re.compile(rb"^---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_ROLE_RE = re.compile(r"\*\*Role:\*\*\s*([^*\n]+)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _is_skill_doc(rel: str) -> bool:
    return Path(rel).name == "SKILL.md"


def _has_frontmatter(data: bytes) -> bool:
    return data.startswith(b"---\n") or data.startswith(b"---\r\n")


def _auto_block(data: bytes) -> bytes | None:
    """The leading frontmatter block iff it is one WE injected, else None."""
    m = _FRONTMATTER_RE.match(data)
    if m and AUTO_MARKER.encode("utf-8") in m.group(0):
        return m.group(0)
    return None


def _synth_description(data: bytes, name: str) -> str:
    """Best-effort one-line description from the skill body (deterministic)."""
    text = data.decode("utf-8", "replace")
    m = _ROLE_RE.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip().strip("—-").strip()
    m = _HEADING_RE.search(text)
    if m and m.group(1).strip():
        return re.sub(r"[*_`]", "", m.group(1)).strip()
    for line in text.splitlines():
        s = line.strip().lstrip(">").strip()
        if s and not s.startswith(("<!--", "---", "#")):
            return re.sub(r"[*_`]", "", s)[:200].strip()
    return f"{name} skill."


def _inject(data: bytes, name: str) -> bytes:
    desc = _synth_description(data, name)
    block = (
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"description: {json.dumps(desc, ensure_ascii=False)}\n"
        "metadata:\n"
        f"  {AUTO_MARKER}: true\n"
        "---\n\n"
    ).encode("utf-8")
    return block + data


def _strip_auto(data: bytes) -> bytes:
    block = _auto_block(data)
    if block is None:
        return data
    rest = data[len(block):]
    if rest.startswith(b"\n"):  # the single blank line we add after the block
        rest = rest[1:]
    return rest


def canonical(rel: str, data: bytes) -> bytes:
    """Content with any pskt-injected frontmatter removed (for comparisons)."""
    if _is_skill_doc(rel):
        return _strip_auto(data)
    return data


def project(env: str, rel: str, data: bytes) -> bytes:
    """What `env` should hold for `rel`, given canonical-ish `data`.

    - Into Codex: ensure a skill has frontmatter (inject if missing).
    - Into any other agent: never carry OUR injected block (keep copies clean).
    """
    if not _is_skill_doc(rel):
        return data
    if env == envs.ENV_CODEX:
        if _has_frontmatter(data):
            return data  # author frontmatter, or already-injected — leave it
        return _inject(data, Path(rel).parent.name)
    return _strip_auto(data)
