"""Tests for ignore options (whitespace / case / regex) and CR normalisation."""

from __future__ import annotations

import pytest

from atrain.core.diff_text import TextOptions, comparison_key, diff_texts
from atrain.core.models import LineTag


def test_comparison_key_normalisations() -> None:
    opts = TextOptions()
    assert comparison_key("Hello World\n", opts) == "Hello World\n"
    strict = TextOptions(ignore_all_space=True, ignore_case=True, strip_trailing_cr=True)
    # Note: whitespace removal also consumes the line terminator, which is
    # fine — terminators are uniform within one split and equality is all
    # that matters.
    assert comparison_key("H e L l o \t W o r l d\r\n", strict) == "helloworld"


def test_ignore_space_treats_whitespace_only_changes_equal() -> None:
    assert diff_texts("a b\n", "ab  \n", TextOptions(ignore_all_space=True)) == []
    # Without the option the difference is real.
    assert len(diff_texts("a b\n", "ab\n")) == 1


def test_ignore_case() -> None:
    assert diff_texts("ABC\nx\n", "abc\nx\n", TextOptions(ignore_case=True)) == []
    hunks = diff_texts("ABC\nx\n", "abc\nx\n")
    assert len(hunks) == 1
    # Rendered lines keep their ORIGINAL case.
    delete_line = next(line for line in hunks[0].lines if line.tag is LineTag.DELETE)
    assert delete_line.text == "ABC"


def test_ignore_options_do_not_mask_real_changes() -> None:
    hunks = diff_texts(
        "value: 1\nother: A\n",
        "value: 2\nother: A\n",
        TextOptions(ignore_case=True, ignore_all_space=True),
    )
    assert len(hunks) == 1
    tags = [line.tag for line in hunks[0].lines]
    assert LineTag.DELETE in tags and LineTag.INSERT in tags


def test_ignore_matching_drops_fully_matching_hunks() -> None:
    filler = "".join(f"m{i}\n" for i in range(1, 8))  # separates hunks by >2*context
    a = f"keep\ndebug print 1\n{filler}real line\ntail\n"
    b = f"keep\ndebug print X\n{filler}REAL LINE\ntail\n"
    # Without the filter: two hunks (debug change + real change).
    assert len(diff_texts(a, b)) == 2
    # With the filter: only the debug hunk vanishes.
    hunks = diff_texts(a, b, TextOptions(ignore_matching=r"debug print"))
    assert len(hunks) == 1
    changed = [line for line in hunks[0].lines if line.tag is not LineTag.CONTEXT]
    assert changed and all("debug" not in line.text for line in changed)


def test_ignore_matching_requires_a_valid_regex() -> None:
    with pytest.raises(Exception):  # noqa: B017 — re.error is fine here
        diff_texts("a\n", "b\n", TextOptions(ignore_matching="([unclosed"))


def test_strip_trailing_cr_equates_crlf_and_lf() -> None:
    assert diff_texts("one\r\ntwo\r\n", "one\ntwo\n", TextOptions(strip_trailing_cr=True)) == []
    assert len(diff_texts("one\r\n", "one\n")) == 1


def test_options_context_controls_grouping() -> None:
    lines_a = "".join(f"l{i}\n" for i in range(30))
    lines_b = lines_a.replace("l5\n", "X\n").replace("l25\n", "Y\n")
    assert len(diff_texts(lines_a, lines_b, TextOptions(context=1))) == 2
    assert len(diff_texts(lines_a, lines_b, TextOptions(context=12))) == 1


def test_negative_context_rejected() -> None:
    with pytest.raises(ValueError):
        diff_texts("a\n", "b\n", TextOptions(context=-1))
