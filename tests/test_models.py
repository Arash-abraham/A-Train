"""Tests for the result data models."""

from __future__ import annotations

import dataclasses

import pytest

from atrain.core.models import (
    DiffLine,
    DiffResult,
    DiffStats,
    FileMeta,
    Hunk,
    LineTag,
    Newline,
    Opcode,
    OpcodeTag,
    compute_stats,
)


def _hunk(lines: list[LineTag]) -> Hunk:
    return Hunk(
        a_start=0,
        a_count=sum(1 for t in lines if t is not LineTag.INSERT),
        b_start=0,
        b_count=sum(1 for t in lines if t is not LineTag.DELETE),
        lines=[DiffLine(tag=t, text="x") for t in lines],
    )


def test_compute_stats_counts_lines_per_tag() -> None:
    hunks = [
        _hunk([LineTag.CONTEXT, LineTag.DELETE, LineTag.INSERT]),
        _hunk([LineTag.INSERT, LineTag.INSERT]),
    ]
    stats = compute_stats(hunks)
    assert stats == DiffStats(added=3, removed=1, hunks=2)


def test_compute_stats_empty() -> None:
    assert compute_stats([]) == DiffStats(added=0, removed=0, hunks=0)


def test_file_meta_is_frozen() -> None:
    meta = FileMeta(path="a.txt", size=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.size = 5  # type: ignore[misc]


def test_opcode_is_frozen_and_hashable() -> None:
    op = Opcode(OpcodeTag.EQUAL, 0, 1, 0, 1)
    assert op == Opcode(OpcodeTag.EQUAL, 0, 1, 0, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        op.a_end = 9  # type: ignore[misc]


def test_diff_result_defaults() -> None:
    meta = FileMeta(path="a", size=0)
    result = DiffResult(mode="text", source=meta, target=meta, identical=True)
    assert result.hunks == []
    assert result.stats == DiffStats(added=0, removed=0, hunks=0)


def test_newline_enum_values() -> None:
    assert {member.name for member in Newline} == {"LF", "CRLF", "CR", "NONE", "MIXED"}
