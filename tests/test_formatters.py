"""Tests for the color, side-by-side, HTML and JSON formatters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atrain import __version__
from atrain.core.diff_text import TextOptions, compare_files
from atrain.core.models import FileMeta
from atrain.output import color, html_report, json_out, side_by_side
from atrain.output.color import BOLD, CYAN, GREEN, RED, RESET


def _result(tmp_path: Path, a_text: str, b_text: str) -> object:
    pa = tmp_path / "a.txt"
    pb = tmp_path / "b.txt"
    pa.write_text(a_text, encoding="utf-8")
    pb.write_text(b_text, encoding="utf-8")
    return compare_files(pa, pb, TextOptions())


# ---------------------------------------------------------------- color

def test_color_render_ansi_and_numbers(tmp_path: Path) -> None:
    import re

    result = _result(tmp_path, "keep\nold\nend\n", "keep\nnew\nend\n")
    text = color.render(result, "a.txt", "b.txt", color=True)  # type: ignore[arg-type]
    assert f"{BOLD}{CYAN}--- a.txt{RESET}" in text
    assert "@@ -1,3 +1,3 @@" in text
    assert RED in text and GREEN in text
    plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
    assert "   1    1" in plain  # both line numbers on the context row
    assert "   3    3" in plain


def test_color_render_plain_mode_has_no_ansi(tmp_path: Path) -> None:
    result = _result(tmp_path, "old\n", "new\n")
    text = color.render(result, "a", "b", color=False)  # type: ignore[arg-type]
    assert "\x1b[" not in text
    assert "- old" in text and "+ new" in text


def test_color_identical_empty_and_binary_notice(tmp_path: Path) -> None:
    assert color.render(_result(tmp_path, "x\n", "x\n"), "a", "b") == ""
    binary = _result(tmp_path, "x\n", "x\n")
    binary.target = FileMeta(path="b", size=1, is_binary=True)  # type: ignore[union-attr]
    binary.identical = False  # type: ignore[union-attr]
    text = color.render(binary, "a", "b", color=True)  # type: ignore[arg-type]
    assert "Binary files differ" in text


# ------------------------------------------------------- side by side

def test_side_layout_and_marks(tmp_path: Path) -> None:
    result = _result(tmp_path, "keep\ndeleted\nmore\n", "keep\ninserted\nmore\n")
    text = side_by_side.render(result, "a.txt", "b.txt", width=60)  # type: ignore[arg-type]
    lines = text.splitlines()
    assert lines[0].startswith("--- a.txt") and "+++ b.txt" in lines[0]
    assert "|" in text and "keep" in text and "inserted" in text
    # Column width respected: data rows are at most ~2 columns + gutter.
    data_rows = [ln for ln in lines if ln and not ln.startswith(("---", "+++"))]
    assert all(len(ln) <= 60 for ln in data_rows)


def test_side_delete_only_and_insert_only_marks(tmp_path: Path) -> None:
    # "two" pairs with "three" ('|'); "four" is insert-only ('>').
    result = _result(tmp_path, "one\ntwo\n", "one\nthree\nfour\n")
    text = side_by_side.render(result, "a", "b", width=60)  # type: ignore[arg-type]
    assert "|" in text and ">" in text

    # A pure deletion renders '<'.
    result = _result(tmp_path, "one\ntwo\nthree\n", "one\nthree\n")
    text = side_by_side.render(result, "a", "b", width=60)  # type: ignore[arg-type]
    assert "<" in text and "two" in text


def test_side_identical_empty(tmp_path: Path) -> None:
    assert side_by_side.render(_result(tmp_path, "x\n", "x\n"), "a", "b") == ""


def test_side_truncates_long_lines(tmp_path: Path) -> None:
    long_line = "z" * 500
    result = _result(tmp_path, f"{long_line}\n", "short\n")
    text = side_by_side.render(result, "a", "b", width=60)  # type: ignore[arg-type]
    assert "z" * 500 not in text


# ---------------------------------------------------------------- html

def test_html_self_contained_and_escaped(tmp_path: Path) -> None:
    result = _result(
        tmp_path,
        "<script>alert('xss')</script>\nkeep\n",
        "<b>safe</b>\nkeep\n",
    )
    text = html_report.render(result, "a.txt", "b.txt")  # type: ignore[arg-type]
    assert text.startswith("<!DOCTYPE html>")
    assert "<script>alert" not in text  # escaped (may sit inside <mark>)
    assert "alert" in text  # the content is still shown, just escaped
    assert "http://" not in text and "https://" not in text  # no external refs
    assert 'class="del"' in text and 'class="ins"' in text


def test_html_identical_notice(tmp_path: Path) -> None:
    result = _result(tmp_path, "same\n", "same\n")
    text = html_report.render(result, "a", "b")  # type: ignore[arg-type]
    assert "Files are identical" in text


def test_html_inline_highlight(tmp_path: Path) -> None:
    result = _result(tmp_path, "old value\n", "new value\n")
    text = html_report.render(result, "a", "b")  # type: ignore[arg-type]
    assert "<mark>" in text


# ---------------------------------------------------------------- json

def test_json_structure_round_trip(tmp_path: Path) -> None:
    result = _result(tmp_path, "keep\nold\n", "keep\nnew\n")
    doc = json.loads(json_out.render(result))  # type: ignore[arg-type]
    assert doc["tool"] == "atrain" and doc["version"] == __version__
    assert doc["mode"] == "text" and doc["identical"] is False
    assert doc["stats"] == {"added": 1, "removed": 1, "hunks": 1}
    assert doc["source"]["path"].endswith("a.txt")
    assert doc["source"]["encoding"] == "utf-8"
    hunk = doc["hunks"][0]
    assert hunk["a_start"] == 0 and hunk["b_start"] == 0
    tags = [line["tag"] for line in hunk["lines"]]
    assert tags == [" ", "-", "+"]  # file ends right after the change
    delete = next(line for line in hunk["lines"] if line["tag"] == "-")
    assert delete["inline"] is not None


def test_json_identical_documents_are_valid(tmp_path: Path) -> None:
    result = _result(tmp_path, "same\n", "same\n")
    doc = json.loads(json_out.render(result))  # type: ignore[arg-type]
    assert doc["identical"] is True and doc["hunks"] == []


def test_json_deterministic(tmp_path: Path) -> None:
    r1 = json_out.render(_result(tmp_path, "a\nb\n", "a\nc\n"))  # type: ignore[arg-type]
    r2 = json_out.render(_result(tmp_path, "a\nb\n", "a\nc\n"))  # type: ignore[arg-type]
    assert r1 == r2


@pytest.mark.parametrize(
    "a_text,b_text",
    [("x\n", "y\n"), ("", "content\n"), ("content\n", "")],
)
def test_cli_formats_via_main(
    a_text: str, b_text: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from atrain.cli import EXIT_DIFFERENCES, main

    pa = tmp_path / "a.txt"
    pb = tmp_path / "b.txt"
    pa.write_text(a_text, encoding="utf-8")
    pb.write_text(b_text, encoding="utf-8")
    for fmt in ("unified", "color", "side", "html", "json"):
        capsys.readouterr()
        assert main([str(pa), str(pb), "--format", fmt]) == EXIT_DIFFERENCES
        out = capsys.readouterr().out
        if fmt in ("unified", "color", "side"):
            assert "@@" in out or "Binary" in out or fmt == "color"
        elif fmt == "html":
            assert out.startswith("<!DOCTYPE html>")
        else:
            json.loads(out)
