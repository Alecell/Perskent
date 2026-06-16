"""Trivial converters: verbatim identity and explicit skip."""
from __future__ import annotations

from perskent.converters.base import Artifact, ConvertResult, DestLayout


class IdentityConverter:
    """Verbatim copy: the env's format IS the canonical format (no transform)."""

    def __init__(self, env: str, kind: str) -> None:
        self.env = env
        self.kind = kind

    def dest_layout(self, name: str) -> DestLayout:
        folder = f"{self.kind}s"
        return DestLayout(
            primary=f"{folder}/{name}.md",
            is_single_file=False,
            glob_roots=(f"{folder}/{name}", f"{folder}/{name}.md"),
        )

    def to_canonical(self, art: Artifact) -> ConvertResult:
        return ConvertResult(files=dict(art.files))

    def from_canonical(self, art: Artifact) -> ConvertResult:
        return ConvertResult(files=dict(art.files))


class SkipConverter:
    """A (env, kind) pair with no real concept in the target — never converts.

    Reaching this at runtime means a gate (SUPPORTED_KINDS) let a pair through
    that it should not have; callers treat a Skip as "no location for kind".
    """

    def __init__(self, env: str, kind: str) -> None:
        self.env = env
        self.kind = kind

    def dest_layout(self, name: str) -> DestLayout:
        folder = f"{self.kind}s"
        return DestLayout(primary=f"{folder}/{name}", is_single_file=False, glob_roots=())

    def to_canonical(self, art: Artifact) -> ConvertResult:
        return ConvertResult(files={}, warnings=[
            f"{self.env} has no concept of {self.kind} — skipped."
        ])

    def from_canonical(self, art: Artifact) -> ConvertResult:
        return ConvertResult(files={}, warnings=[
            f"{self.env} has no concept of {self.kind} — skipped."
        ])

    @property
    def is_skip(self) -> bool:
        return True
