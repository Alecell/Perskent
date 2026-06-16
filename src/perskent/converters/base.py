"""Shared primitives for the converter layer.

perskent replicates artifacts across code-agents. Most pairs share a format and
copy verbatim, but some diverge (Codex agents are TOML, Gemini commands are
TOML, skills need YAML frontmatter to be auto-discovered). A *converter*
projects an artifact between a code-agent's on-disk format and a single
**canonical** representation — **Claude markdown** — which is what the registry
stores.

Conversion unit is the whole artifact (a file-set), not a single file, because
formats differ structurally: a Claude agent `agents/<name>.md` (+ optional
supporting files) becomes a single `agents/<name>.toml` in Codex.

This module owns the dataclasses, the Converter protocol, and the low-level
format helpers (YAML frontmatter + TOML read/write, skill-frontmatter
injection) that the concrete converters reuse.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Protocol, runtime_checkable

import tomli_w

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Artifact:
    """A whole artifact as an in-memory file-set, keyed by canonical name.

    `files` maps POSIX paths *relative to the code-agent's kind base dir*
    (e.g. "skills/foo/SKILL.md", "agents/foo.md") to raw bytes.
    """
    kind: str            # "skill" | "agent" | "command"
    name: str
    files: dict[str, bytes]


@dataclass
class ConvertResult:
    """Outcome of a projection: the target file-set plus advisory warnings."""
    files: dict[str, bytes]
    warnings: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DestLayout:
    """How a code-agent names/locates an artifact of one (kind, name).

    `primary` is the canonical-relative path of the artifact's main file or
    its directory. `is_single_file` is True when the whole artifact is one file
    (Codex agent .toml, Gemini command .toml) — no supporting-file tree.
    `glob_roots` are the paths to probe when *finding* the artifact on disk.
    """
    primary: str
    is_single_file: bool
    glob_roots: tuple[str, ...]


@runtime_checkable
class Converter(Protocol):
    env: str
    kind: str

    def dest_layout(self, name: str) -> DestLayout: ...
    def to_canonical(self, art: Artifact) -> ConvertResult: ...
    def from_canonical(self, art: Artifact) -> ConvertResult: ...


# ---------------------------------------------------------------------------
# Skill frontmatter injection (preserves the exact v1.1.0 behavior)
# ---------------------------------------------------------------------------

# Sentinel placed inside frontmatter we generate, so we can recognize (and
# undo) our own injection later. Authors are extremely unlikely to use it.
AUTO_MARKER = "pskt_auto_frontmatter"

_FRONTMATTER_RE = re.compile(rb"^---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_ROLE_RE = re.compile(r"\*\*Role:\*\*\s*([^*\n]+)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def has_frontmatter(data: bytes) -> bool:
    return data.startswith(b"---\n") or data.startswith(b"---\r\n")


def auto_block(data: bytes) -> bytes | None:
    """The leading frontmatter block iff it is one WE injected, else None."""
    m = _FRONTMATTER_RE.match(data)
    if m and AUTO_MARKER.encode("utf-8") in m.group(0):
        return m.group(0)
    return None


def synth_description(data: bytes, name: str) -> str:
    """Best-effort one-line description from a body (deterministic)."""
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


def inject_skill_frontmatter(data: bytes, name: str) -> bytes:
    """Prepend a minimal, marker-tagged YAML frontmatter block."""
    desc = synth_description(data, name)
    block = (
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"description: {json.dumps(desc, ensure_ascii=False)}\n"
        "metadata:\n"
        f"  {AUTO_MARKER}: true\n"
        "---\n\n"
    ).encode("utf-8")
    return block + data


def strip_auto(data: bytes) -> bytes:
    """Remove only the frontmatter block WE injected; keep author frontmatter."""
    block = auto_block(data)
    if block is None:
        return data
    rest = data[len(block):]
    if rest.startswith(b"\n"):  # the single blank line we add after the block
        rest = rest[1:]
    return rest


# ---------------------------------------------------------------------------
# YAML frontmatter (minimal) — enough for our controlled fields
# ---------------------------------------------------------------------------
# We deliberately avoid a full YAML dependency. Artifact frontmatter uses a
# small, predictable shape: top-level `key: scalar`, inline lists `[a, b]`,
# block lists (`- item`), and one level of nested map (`metadata:` + indented
# `key: value`). Anything else round-trips as a raw scalar string.

def _parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if raw == "":
        return ""
    if raw[0] in "\"'":
        try:
            return json.loads(raw) if raw[0] == '"' else raw[1:-1]
        except json.JSONDecodeError:
            return raw.strip("\"'")
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x) for x in _split_inline_list(inner)]
    return raw


def _split_inline_list(inner: str) -> list[str]:
    items, depth, cur = [], 0, ""
    in_str = ""
    for ch in inner:
        if in_str:
            cur += ch
            if ch == in_str:
                in_str = ""
            continue
        if ch in "\"'":
            in_str = ch
            cur += ch
        elif ch == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur)
    return items


def parse_frontmatter(raw: bytes) -> tuple[dict[str, Any] | None, bytes]:
    """Split `raw` into (frontmatter dict | None, body bytes)."""
    if not has_frontmatter(raw):
        return None, raw
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return None, raw
    block = m.group(0)
    body = raw[len(block):]
    # Consume the single conventional blank line after the closing `---`, so
    # parse(build(x)) is a true inverse (build emits exactly one).
    if body.startswith(b"\r\n"):
        body = body[2:]
    elif body.startswith(b"\n"):
        body = body[1:]
    inner = block.decode("utf-8", "replace").split("\n", 1)[1]
    inner = inner.rsplit("---", 1)[0]
    data: dict[str, Any] = {}
    cur_key: str | None = None
    for line in inner.splitlines():
        if not line.strip():
            continue
        indented = line[0] in " \t"
        stripped = line.strip()
        if stripped.startswith("- "):
            if cur_key is not None:
                data.setdefault(cur_key, [])
                if isinstance(data[cur_key], list):
                    data[cur_key].append(_parse_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key, val = key.strip(), val.strip()
        if indented and cur_key is not None and isinstance(data.get(cur_key), dict):
            data[cur_key][key] = _parse_scalar(val)
        elif val == "":
            # Parent of a nested map or block list; default to dict, may become
            # a list if `- ` items follow.
            data[key] = {}
            cur_key = key
        else:
            data[key] = _parse_scalar(val)
            cur_key = key
    return data, body


def _dump_value(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, list):
        return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in val) + "]"
    return json.dumps(val, ensure_ascii=False)


def build_frontmatter(data: dict[str, Any], body: bytes) -> bytes:
    """Emit `---\\n<frontmatter>\\n---\\n\\n<body>` deterministically."""
    lines = ["---"]
    for key, val in data.items():
        if isinstance(val, dict):
            lines.append(f"{key}:")
            for sub, subval in val.items():
                lines.append(f"  {sub}: {_dump_value(subval)}")
        else:
            lines.append(f"{key}: {_dump_value(val)}")
    lines.append("---")
    head = ("\n".join(lines) + "\n\n").encode("utf-8")
    return head + body


# ---------------------------------------------------------------------------
# TOML helpers
# ---------------------------------------------------------------------------

def parse_toml(data: bytes) -> dict[str, Any]:
    return tomllib.loads(data.decode("utf-8"))


def dump_toml(data: dict[str, Any]) -> bytes:
    return tomli_w.dumps(data).encode("utf-8")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def artifact_name(rel: str) -> str:
    """The artifact name from a kind-relative path (folder or file stem)."""
    p = PurePosixPath(rel)
    if p.name in ("SKILL.md",):
        return p.parent.name
    return p.stem


# Canonical key order for agent/command frontmatter. Normalizing to a fixed
# order is what makes a claude .md and a codex .toml of the SAME agent produce
# byte-identical canonical forms (so mirror sees them as equal, not conflicting).
AGENT_KEY_ORDER = ("name", "description", "model", "tools")
COMMAND_KEY_ORDER = ("name", "description", "argument-hint", "allowed-tools")


def ordered_fm(fm: dict[str, Any], priority: tuple[str, ...]) -> dict[str, Any]:
    """Reorder a frontmatter dict: known keys first (in `priority`), then the
    rest alphabetically, with `metadata` last. Drops empty values."""
    out: dict[str, Any] = {}
    for k in priority:
        if k in fm and fm[k] not in (None, "", [], {}):
            out[k] = fm[k]
    for k in sorted(fm):
        if k in out or k == "metadata":
            continue
        if fm[k] not in (None, "", [], {}):
            out[k] = fm[k]
    if fm.get("metadata"):
        out["metadata"] = fm["metadata"]
    return out


def normalize_md(raw: bytes, priority: tuple[str, ...]) -> bytes:
    """Canonicalize a markdown+frontmatter doc: parse, reorder keys, rebuild.

    Idempotent — normalize(normalize(x)) == normalize(x). A doc without
    frontmatter is returned unchanged.
    """
    fm, body = parse_frontmatter(raw)
    if fm is None:
        return raw
    return build_frontmatter(ordered_fm(fm, priority), body)


def is_supporting_file(rel: str, primary_stem: str) -> bool:
    """True for files that are not the artifact's single primary doc."""
    return PurePosixPath(rel).name != primary_stem
