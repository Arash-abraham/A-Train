"""Tests for the unified formatter, including patch-compat golden strings."""

from __future__ import annotations

from pathlib import Path

import pytest

from atrain.core.diff_text import compare_files
from atrain.core.models import compute_stats
from atrain.output.unified import hunk_header, render
from tests._applypatch import apply_unified


def _unified(a_text: str, b_text: str, tmp_path: Path, a_name = "A", b_name = "B") -> str:
    pa = tmp_path / "a.txt"
    pb = tmp_path / "b.txt"
    pa.write_text(a_text, encoding="utf-8")
    pb.write_text(b_text, encoding="utf-8")
    result = compare_files(pa, pb)
    return render(result, a_name, b_name)


def test_identical_renders_empty(tmp_path: Path) -> None:
    assert _unified("same\n", "same\n", tmp_path) == ""


def test_simple_change_golden(tmp_path: Path) -> None:
    assert _unified("alpha\nbeta\ngamma\n", "alpha\nbeta\ndelta\n", tmp_path) == (
        "--- A\n"
        "+++ B\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        " beta\n"
        "-gamma\n"
        "+delta\n"
    )


def test_insert_into_empty_golden(tmp_path: Path) -> None:
    assert _unified("", "x\n", tmp_path) == (
        "--- A\n+++ B\n@@ -0,0 +1 @@\n+x\n"
    )


def test_delete_everything_golden(tmp_path: Path) -> None:
    assert _unified("a\nb\nc\n", "", tmp_path) == (
        "--- A\n+++ B\n@@ -1,3 +0,0 @@\n-a\n-b\n-c\n"
    )


def test_missing_trailing_newline_marker(tmp_path: Path) -> None:
    expected = (
        "--- A\n"
        "+++ B\n"
        "@@ -1,2 +1,2 @@\n"
        " x\n"
        "-y\n"
        "\\ No newline at end of file\n"
        "+z\n"
        "\\ No newline at end of file\n"
    )
    assert _unified("x\ny", "x\nz", tmp_path) == expected


def test_single_context_line_omits_count(tmp_path: Path) -> None:
    assert _unified("a\n", "a\nb\n", tmp_path) == (
        "--- A\n+++ B\n@@ -1 +1,2 @@\n a\n+b\n"
    )


def test_hunk_header_ranges() -> None:
    from atrain.core.models import Hunk

    assert hunk_header(Hunk(0, 3, 0, 3)) == "@@ -1,3 +1,3 @@"
    assert hunk_header(Hunk(0, 1, 0, 1)) == "@@ -1 +1 @@"
    assert hunk_header(Hunk(0, 0, 0, 1)) == "@@ -0,0 +1 @@"


@pytest.mark.parametrize(
    ("a_text", "b_text"),
    [
        ("alpha\nbeta\ngamma\n", "alpha\nbeta\ndelta\n"),
        ("", "fresh content\n"),
        ("old content\n", ""),
        ("x\ny", "x\nz"),
        ("one\n", "one\ntwo\nthree\n"),
        ("سلام\nدنیا\n", "سلام\nجهان\n"),
    ],
)
def test_output_applies_back_to_target(
    a_text: str, b_text: str, tmp_path: Path
) -> None:
    """The invariant: applying our diff to the source reproduces the target."""
    patch = _unified(a_text, b_text, tmp_path, a_name="a", b_name="b")
    assert apply_unified(a_text, patch) == b_text


def test_stats_consistent_with_rendered_lines(tmp_path: Path) -> None:
    pa = tmp_path / "a.txt"
    pb = tmp_path / "b.txt"
    pa.write_text("keep\nremove1\nremove2\n")
    pb.write_text("keep\nadd1\nadd2\nadd3\n")
    result = compare_files(pa, pb)
    assert result.stats == compute_stats(result.hunks)
    assert result.stats == pytest.approx(
        type(result.stats)(added=3, removed=2, hunks=1)
    ) or result.stats.added == 3
