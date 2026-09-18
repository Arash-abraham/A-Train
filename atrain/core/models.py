"""Explicit data models for comparison results.

Every comparison engine in :mod:`atrain.core` produces a
:class:`DiffResult`; every formatter in :mod:`atrain.output` consumes one.
The engine never knows about terminals, colours, or HTML (ROADMAP.md, §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Newline(Enum):
    """Dominant newline style of a text file."""

    LF = "LF"
    CRLF = "CRLF"
    CR = "CR"
    NONE = "NONE"
    MIXED = "MIXED"


class LineTag(Enum):
    """Per-line marker inside a :class:`Hunk`."""

    CONTEXT = " "
    DELETE = "-"
    INSERT = "+"


class OpcodeTag(Enum):
    """Edit-operation classification, mirroring ``difflib`` terminology."""

    EQUAL = "equal"
    REPLACE = "replace"
    DELETE = "delete"
    INSERT = "insert"


@dataclass(frozen=True, slots=True)
class FileMeta:
    """Metadata about one compared input.

    Attributes:
        path: Path exactly as given on the command line.
        size: File size in bytes.
        digest: BLAKE2b-128 hex digest of the raw bytes, or ``None`` when
            unknown (e.g. for streams that were never hashed).
        encoding: Encoding actually used to decode the file, if decoded.
        newline: Dominant newline style, if decoded.
        is_binary: True when a NUL byte was sniffed in the leading bytes.
    """

    path: str
    size: int = 0
    digest: str | None = None
    encoding: str | None = None
    newline: Newline | None = None
    is_binary: bool = False


@dataclass(frozen=True, slots=True)
class Opcode:
    """A typed edit operation over two line sequences (0-based, half-open)."""

    tag: OpcodeTag
    a_start: int
    a_end: int
    b_start: int
    b_end: int


@dataclass(frozen=True, slots=True)
class InlineRef:
    """Character-level refinement of a paired DELETE/INSERT line.

    ``prefix_len`` and ``suffix_len`` are the lengths of the equal
    leading/trailing runs shared by the two paired line texts; everything
    between is what actually changed (two-phase diffing, ROADMAP §3.5).
    """

    prefix_len: int
    suffix_len: int


@dataclass(slots=True)
class DiffLine:
    """One rendered line inside a :class:`Hunk`.

    ``text`` never contains the trailing newline; ``newline`` records whether
    the original source line ended with one, so formatters can emit
    ``\\ No newline at end of file`` markers.  ``inline`` is set only on
    DELETE/INSERT lines that were paired with an opposite-side line inside
    a REPLACE block (see :class:`InlineRef`).
    """

    tag: LineTag
    text: str
    newline: bool = True
    inline: InlineRef | None = None


@dataclass(slots=True)
class Hunk:
    """A contiguous block of changes (0-based, half-open ranges)."""

    a_start: int
    a_count: int
    b_start: int
    b_count: int
    lines: list[DiffLine] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DiffStats:
    """Summary counters derived from a result's hunks."""

    added: int
    removed: int
    hunks: int


@dataclass(slots=True)
class DiffResult:
    """The complete outcome of one comparison.

    Formatters must rely exclusively on this model; engines must never
    pre-format output.
    """

    mode: str
    source: FileMeta
    target: FileMeta
    identical: bool
    hunks: list[Hunk] = field(default_factory=list)
    stats: DiffStats = field(default_factory=lambda: DiffStats(added=0, removed=0, hunks=0))


def compute_stats(hunks: list[Hunk]) -> DiffStats:
    """Derive :class:`DiffStats` from a hunk list."""
    added = 0
    removed = 0
    for hunk in hunks:
        for line in hunk.lines:
            if line.tag is LineTag.INSERT:
                added += 1
            elif line.tag is LineTag.DELETE:
                removed += 1
    return DiffStats(added=added, removed=removed, hunks=len(hunks))
