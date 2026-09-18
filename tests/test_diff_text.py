"""Tests for the Myers text-diff engine.

The two central properties (ROADMAP.md, §7):

1. **Validity**  — applying the produced edit script to ``a`` yields ``b``.
2. **Optimality** — the script's edit count equals the true edit distance
   computed by an independent O(NM) dynamic program.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from atrain.core.diff_text import (
    DiffTooComplex,
    _Budget,
    build_hunks,
    diff_lines,
    intern_line_pairs,
    intern_lines,
    myers_opcodes,
)
from atrain.core.models import LineTag, OpcodeTag


def _edit_distance(a: Sequence[int], b: Sequence[int]) -> int:
    """Reference O(NM) edit distance in the Myers model (insert/delete only).

    ``D = N + M - 2 * LCS(a, b)`` — substitutions are *not* operations in a
    line diff (a substitution is one deletion plus one insertion).
    """
    prev = [0] * (len(b) + 1)
    for av in a:
        curr = [0]
        for j, bv in enumerate(b):
            curr.append(prev[j] + 1 if av == bv else max(prev[j + 1], curr[j]))
        prev = curr
    lcs = prev[-1]
    return len(a) + len(b) - 2 * lcs


def _script_length(ops: Sequence) -> int:
    """Number of individual edits in an opcode script (EQUAL is free)."""
    total = 0
    for op in ops:
        if op.tag is OpcodeTag.EQUAL:
            continue
        total += op.a_end - op.a_start + op.b_end - op.b_start
    return total


def _apply_opcodes(a: Sequence[int], b: Sequence[int], ops: Sequence) -> list[int]:
    """Rebuild ``b`` from ``a`` using *ops* (validity check)."""
    if not ops:
        return list(a)  # empty script: inputs are identical
    rebuilt: list[int] = []
    for op in ops:
        if op.tag is OpcodeTag.EQUAL:
            rebuilt.extend(a[op.a_start : op.a_end])
        elif op.tag in (OpcodeTag.REPLACE, OpcodeTag.INSERT):
            rebuilt.extend(b[op.b_start : op.b_end])
    return rebuilt


def _assert_well_formed(a: Sequence[int], b: Sequence[int], ops: Sequence) -> None:
    """Opcodes must tile both sequences exactly, in order."""
    if not ops:
        # An empty script is only valid for identical inputs.
        assert list(a) == list(b), "empty script for differing inputs"
        return
    expect_a = 0
    expect_b = 0
    for op in ops:
        assert op.a_start == expect_a, f"a gap before {op}"
        assert op.b_start == expect_b, f"b gap before {op}"
        expect_a = op.a_end
        expect_b = op.b_end
    assert expect_a == len(a), "opcodes do not cover all of a"
    assert expect_b == len(b), "opcodes do not cover all of b"


def test_identical_sequences_yield_empty_script() -> None:
    assert myers_opcodes([1, 2, 3], [1, 2, 3]) == []


def test_single_deletion_and_insertion() -> None:
    ops = myers_opcodes([1, 2, 3], [1, 3])
    assert len(ops) == 3  # equal, delete, equal
    assert _apply_opcodes([1, 2, 3], [1, 3], ops) == [1, 3]
    assert _script_length(ops) == 1

    ops = myers_opcodes([1, 3], [1, 2, 3])
    assert _apply_opcodes([1, 3], [1, 2, 3], ops) == [1, 2, 3]
    assert _script_length(ops) == 1


def test_fully_disjoint_sequences() -> None:
    a, b = [0, 0, 0], [1, 1, 1, 1]
    ops = myers_opcodes(a, b)
    assert _apply_opcodes(a, b, ops) == b
    assert _script_length(ops) == _edit_distance(a, b)


@settings(max_examples=500, deadline=None)
@given(
    a=st.lists(st.integers(0, 4), max_size=14),
    b=st.lists(st.integers(0, 4), max_size=14),
)
def test_property_valid_and_optimal(a: list[int], b: list[int]) -> None:
    ops = myers_opcodes(a, b)
    _assert_well_formed(a, b, ops)
    assert _apply_opcodes(a, b, ops) == b
    assert _script_length(ops) == _edit_distance(a, b)


@settings(max_examples=200, deadline=None)
@given(
    a=st.lists(st.text(alphabet="abcن", max_size=3), max_size=10),
    b=st.lists(st.text(alphabet="abcن", max_size=3), max_size=10),
)
def test_property_on_line_lists(a: list[str], b: list[str]) -> None:
    """End-to-end over interned *lines* (strings, incl. Unicode)."""
    ids_a, ids_b = intern_line_pairs(a, b)
    ops = myers_opcodes(ids_a, ids_b)
    assert _apply_opcodes(ids_a, ids_b, ops) == ids_b
    assert _script_length(ops) == _edit_distance(ids_a, ids_b)


def test_budget_fallback_remains_valid() -> None:
    """When the budget is blown the fallback must stay a *correct* script."""
    a = [0, 1] * 400
    b = [2, 3] * 400  # disjoint alphabets => true distance 1600
    ops = myers_opcodes(a, b, budget=_Budget(2000))
    _assert_well_formed(a, b, ops)
    assert _apply_opcodes(a, b, ops) == b
    # Fallback produces at most one replacement over the differing interior.
    assert sum(1 for op in ops if op.tag is OpcodeTag.REPLACE) == 1


def test_budget_exhaustion_raises_when_uncaught() -> None:
    from atrain.core.diff_text import _run_myers

    a = [0, 1] * 400
    b = [2, 3] * 400
    with pytest.raises(DiffTooComplex):
        _run_myers(a, b, _Budget(500))


def test_intern_lines_single_sequence() -> None:
    assert intern_lines(["a", "b", "a"]) == [0, 1, 0]


def test_intern_line_pairs_shares_table() -> None:
    ids_a, ids_b = intern_line_pairs(["a", "b"], ["b", "c", "a"])
    assert ids_a == [0, 1]
    assert ids_b == [1, 2, 0]


def test_build_hunks_rejects_negative_context() -> None:
    with pytest.raises(ValueError):
        build_hunks([], [], [], context=-1)


def test_diff_lines_hunk_boundaries() -> None:
    a_lines = [f"line{i}\n" for i in range(20)]
    b_lines = list(a_lines)
    b_lines[2] = "changed\n"
    b_lines[15] = "changed too\n"
    hunks = diff_lines(a_lines, b_lines, context=2)
    # Two distant changes => two hunks.
    assert len(hunks) == 2
    first, second = hunks
    assert first.a_start == 0 and first.a_count == 5
    assert second.a_start == 13 and second.a_count == 5
    for hunk in hunks:
        tags = [line.tag for line in hunk.lines]
        assert tags.count(LineTag.DELETE) == 1
        assert tags.count(LineTag.INSERT) == 1


def test_diff_lines_close_changes_merge_into_one_hunk() -> None:
    a_lines = [f"line{i}\n" for i in range(10)]
    b_lines = list(a_lines)
    b_lines[4] = "A\n"
    b_lines[7] = "B\n"  # within 2*3 context lines of the first change
    hunks = diff_lines(a_lines, b_lines, context=3)
    assert len(hunks) == 1
