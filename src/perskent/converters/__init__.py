"""Converter registry + public API.

A converter projects an artifact between a code-agent's on-disk format and the
canonical (Claude-markdown) form. The registry is keyed by (env, kind); pairs
with no entry resolve to a SkipConverter (no concept in that env).

`SUPPORTED_KINDS` in `envs` is the GATE (what is offered); this registry is the
MECHANISM (how it converts). A consistency test asserts they agree.
"""
from __future__ import annotations

from perskent.converters.base import (
    AUTO_MARKER,
    Artifact,
    ConvertResult,
    Converter,
    DestLayout,
)
from perskent.converters.agent_codex import CodexAgentConverter
from perskent.converters.agent_md import MarkdownAgentConverter, OpencodeAgentConverter
from perskent.converters.command_gemini import GeminiCommandConverter
from perskent.converters.command_md import MarkdownCommandConverter
from perskent.converters.noop import IdentityConverter, SkipConverter
from perskent.converters.skill import SkillConverter

__all__ = [
    "Artifact",
    "ConvertResult",
    "DestLayout",
    "AUTO_MARKER",
    "converter_for",
    "to_canonical",
    "from_canonical",
    "canonical_files",
    "dest_layout",
    "build_artifact",
]

_SKILL_ENVS = ("claude", "codex", "opencode", "qwen", "cursor", "zed", "cline")
_MD_AGENT_ENVS = ("claude", "qwen", "cursor")
_MD_COMMAND_ENVS = ("claude", "opencode", "qwen")

_REGISTRY: dict[tuple[str, str], Converter] = {}


def _register(conv: Converter) -> None:
    _REGISTRY[(conv.env, conv.kind)] = conv


for _env in _SKILL_ENVS:
    _register(SkillConverter(_env))
for _env in _MD_AGENT_ENVS:
    _register(MarkdownAgentConverter(_env))
_register(OpencodeAgentConverter("opencode"))
_register(CodexAgentConverter())
for _env in _MD_COMMAND_ENVS:
    _register(MarkdownCommandConverter(_env))
_register(GeminiCommandConverter())


def converter_for(env: str, kind: str) -> Converter:
    """The converter for (env, kind), or a SkipConverter if none is registered."""
    conv = _REGISTRY.get((env, kind))
    if conv is None:
        return SkipConverter(env, kind)
    return conv


def is_skip(env: str, kind: str) -> bool:
    return (env, kind) not in _REGISTRY


def registered_pairs() -> frozenset[tuple[str, str]]:
    return frozenset(_REGISTRY)


def build_artifact(kind: str, name: str, files: dict[str, bytes]) -> Artifact:
    return Artifact(kind=kind, name=name, files=dict(files))


def to_canonical(env: str, art: Artifact) -> ConvertResult:
    return converter_for(env, art.kind).to_canonical(art)


def from_canonical(env: str, art: Artifact) -> ConvertResult:
    return converter_for(env, art.kind).from_canonical(art)


def canonical_files(env: str, kind: str, name: str, files: dict[str, bytes]) -> dict[str, bytes]:
    """Canonical file-set for comparison (warnings dropped)."""
    return to_canonical(env, build_artifact(kind, name, files)).files


def dest_layout(env: str, kind: str, name: str) -> DestLayout:
    return converter_for(env, kind).dest_layout(name)
