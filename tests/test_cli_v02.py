"""CLI tests for v0.2 options: ignore flags, encoding, color, side, docs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atrain.cli import EXIT_ERROR, EXIT_SAME, main


def _file(tmp_path: Path, name: str, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding=encoding, newline="")
    return path


def test_ignore_space_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _file(tmp_path, "a.txt", "hello   world\n")
    b = _file(tmp_path, "b.txt", "helloworld\n")
    assert main([str(a), str(b), "--ignore-space"]) == EXIT_SAME
    assert capsys.readouterr().out == ""


def test_ignore_case_flag(tmp_path: Path) -> None:
    a = _file(tmp_path, "a.txt", "ABC\n")
    b = _file(tmp_path, "b.txt", "abc\n")
    assert main([str(a), str(b), "--ignore-case"]) == EXIT_SAME


def test_strip_trailing_cr_flag(tmp_path: Path) -> None:
    a = _file(tmp_path, "a.txt", "one\r\ntwo\r\n")
    b = _file(tmp_path, "b.txt", "one\ntwo\n")
    assert main([str(a), str(b), "--strip-trailing-cr"]) == EXIT_SAME


def test_ignore_matching_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _file(tmp_path, "a.txt", "stable\nTODO fix\nstable2\n")
    b = _file(tmp_path, "b.txt", "stable\nTODO done\nstable2\n")
    assert main([str(a), str(b), "--ignore-matching", "TODO"]) == EXIT_SAME
    assert capsys.readouterr().out == ""


def test_invalid_regex_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _file(tmp_path, "a.txt", "x\n")
    b = _file(tmp_path, "b.txt", "y\n")
    assert main([str(a), str(b), "--ignore-matching", "([bad"]) == EXIT_ERROR
    assert "invalid regular expression" in capsys.readouterr().err


def test_color_always_vs_never(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _file(tmp_path, "a.txt", "old\n")
    b = _file(tmp_path, "b.txt", "new\n")
    main([str(a), str(b), "--format", "color", "--color", "always"])
    assert "\x1b[" in capsys.readouterr().out
    main([str(a), str(b), "--format", "color", "--color", "never"])
    assert "\x1b[" not in capsys.readouterr().out


def test_color_auto_not_a_tty(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    a = _file(tmp_path, "a.txt", "old\n")
    b = _file(tmp_path, "b.txt", "new\n")
    main([str(a), str(b), "--format", "color"])  # capsys: not a TTY
    assert "\x1b[" not in capsys.readouterr().out


def test_side_width_option(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _file(tmp_path, "a.txt", "one\n")
    b = _file(tmp_path, "b.txt", "two\n")
    assert main([str(a), str(b), "--format", "side", "--width", "40"]) == 1
    out = capsys.readouterr().out
    data_rows = [ln for ln in out.splitlines() if ln and not ln.startswith(("--", "++", "@@"))]
    assert all(len(ln) <= 40 for ln in data_rows)


def test_html_and_json_identical_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _file(tmp_path, "a.txt", "same\n")
    b = _file(tmp_path, "b.txt", "same\n")
    assert main([str(a), str(b), "--format", "html"]) == EXIT_SAME
    assert "<!DOCTYPE html>" in capsys.readouterr().out
    capsys.readouterr()
    assert main([str(a), str(b), "--format", "json"]) == EXIT_SAME
    assert json.loads(capsys.readouterr().out)["identical"] is True


def test_html_output_written_to_file(tmp_path: Path) -> None:
    a = _file(tmp_path, "a.txt", "old\n")
    b = _file(tmp_path, "b.txt", "new\n")
    out = tmp_path / "report.html"
    assert main([str(a), str(b), "--format", "html", "-o", str(out)]) == 1
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_encoding_flag_end_to_end(tmp_path: Path) -> None:
    a = _file(tmp_path, "a16.txt", "ی\n", encoding="utf-16")
    b = _file(tmp_path, "b16.txt", "ی\n", encoding="utf-16")
    assert main([str(a), str(b)]) == EXIT_SAME  # auto-detects UTF-16 BOM
    c = _file(tmp_path, "c16.txt", "د\n", encoding="utf-16")
    assert main([str(a), str(c)]) == 1


def test_side_identical_silent(tmp_path: Path) -> None:
    a = _file(tmp_path, "a.txt", "same\n")
    b = _file(tmp_path, "b.txt", "same\n")
    assert main([str(a), str(b), "--format", "side"]) == EXIT_SAME
