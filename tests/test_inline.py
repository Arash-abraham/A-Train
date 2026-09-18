"""Tests for two-phase intra-line refinement (InlineRef)."""

from __future__ import annotations

from atrain.core.diff_text import INLINE_REF_MAX_CHARS, diff_texts
from atrain.core.models import LineTag


def _pair_of(hunks: list) -> tuple:
    delete = next(d_line for d_line in hunks[0].lines if d_line.tag is LineTag.DELETE)
    insert = next(d_line for d_line in hunks[0].lines if d_line.tag is LineTag.INSERT)
    return delete, insert


def test_simple_replacement_pair_refined() -> None:
    hunks = diff_texts("old value here\n", "new value here\n")
    delete, insert = _pair_of(hunks)
    assert delete.inline is not None and insert.inline is not None
    # "old value here" vs "new value here": nothing in common at the front
    # ('o' vs 'n'), common suffix " value here".
    assert delete.inline.prefix_len == 0
    assert delete.inline.suffix_len == len(" value here")
    assert insert.inline.prefix_len == 0
    assert insert.inline.suffix_len == len(" value here")


def test_identical_prefix_and_suffix() -> None:
    hunks = diff_texts("foo = 1\n", "foo = 2\n")
    delete, insert = _pair_of(hunks)
    assert delete.inline == insert.inline
    assert delete.inline.prefix_len == len("foo = ")
    assert delete.inline.suffix_len == 0  # the changed char IS the last one

    hunks = diff_texts("1 + foo\n", "2 + foo\n")
    delete, _ = _pair_of(hunks)
    assert delete.inline is not None
    assert delete.inline.prefix_len == 0
    assert delete.inline.suffix_len == len(" + foo")


def test_insertion_between_common_ends() -> None:
    hunks = diff_texts("alpha beta\n", "alpha XX beta\n")
    delete, insert = _pair_of(hunks)
    assert delete.inline is not None and insert.inline is not None
    assert delete.inline.prefix_len == len("alpha ")
    assert delete.inline.suffix_len == len("beta")
    assert insert.inline.prefix_len == len("alpha ")


def test_long_lines_skip_refinement() -> None:
    long_a = "x" * (INLINE_REF_MAX_CHARS + 1) + "\n"
    long_b = "x" * INLINE_REF_MAX_CHARS + "y\n"
    hunks = diff_texts(long_a, long_b)
    delete, insert = _pair_of(hunks)
    assert delete.inline is None
    assert insert.inline is None


def test_replace_block_pairs_in_order() -> None:
    hunks = diff_texts("aaa\nbbb\n", "AAA\nBBB\n")
    del_lines = [d_line for d_line in hunks[0].lines if d_line.tag is LineTag.DELETE]
    ins_lines = [d_line for d_line in hunks[0].lines if d_line.tag is LineTag.INSERT]
    assert len(del_lines) == 2 and len(ins_lines) == 2
    assert all(d_line.inline is not None for d_line in del_lines + ins_lines)
    # "aaa" vs "AAA": nothing in common.
    assert del_lines[0].inline.prefix_len == 0
    assert del_lines[0].inline.suffix_len == 0


def test_pure_add_delete_have_no_inline() -> None:
    hunks = diff_texts("a\n", "a\nb\n")
    added = next(d_line for d_line in hunks[0].lines if d_line.tag is LineTag.INSERT)
    assert added.inline is None
