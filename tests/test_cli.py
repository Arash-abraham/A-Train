"""Tests for the command-line interface (in-process and subprocess)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from atrain import __version__
from atrain.cli import EXIT_DIFFERENCES, EXIT_ERROR, EXIT_SAME, main

REPO_ROOT = Path(__file__).resolve().parent.parent


def _file(tmp_path: Path, name: str, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding=encoding, newline="")
    return path


def test_identical_files_exit_zero_and_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _file(tmp_path, "a.txt", "same\n")
    b = _file(tmp_path, "b.txt", "same\n")
    assert main([str(a), str(b)]) == EXIT_SAME
    assert capsys.readouterr().out == ""


def test_differences_exit_one_and_print_patch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _file(tmp_path, "a.txt", "one\ntwo\n")
    b = _file(tmp_path, "b.txt", "one\nTWO\n")
    assert main([str(a), str(b)]) == EXIT_DIFFERENCES
    out = capsys.readouterr().out
    assert out.startswith(f"--- {a}\n+++ {b}\n")
    assert "@@ -1,2 +1,2 @@" in out
    assert "-two\n+TWO\n" in out


def test_missing_file_exit_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "nope.txt"
    other = _file(tmp_path, "b.txt", "x\n")
    assert main([str(missing), str(other)]) == EXIT_ERROR
    assert "No such file or directory" in capsys.readouterr().err


def test_directory_argument_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "dir"
    directory.mkdir()
    other = _file(tmp_path, "b.txt", "x\n")
    assert main([str(directory), str(other)]) == EXIT_ERROR
    assert "Is a directory" in capsys.readouterr().err


def test_negative_context_exit_two(tmp_path: Path) -> None:
    a = _file(tmp_path, "a.txt", "x\n")
    b = _file(tmp_path, "b.txt", "y\n")
    assert main([str(a), str(b), "--context", "-1"]) == EXIT_ERROR


def test_unknown_encoding_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _file(tmp_path, "a.txt", "x\n")
    b = _file(tmp_path, "b.txt", "y\n")
    assert main([str(a), str(b), "--encoding", "not-an-encoding"]) == EXIT_ERROR
    assert "unknown encoding" in capsys.readouterr().err


def test_forced_wrong_encoding_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = _file(tmp_path, "good.txt", "ok\n")
    u16 = _file(tmp_path, "u16.txt", "ok\n", encoding="utf-16")
    assert main([str(good), str(u16), "--encoding", "utf-8"]) == EXIT_ERROR
    assert "cannot decode" in capsys.readouterr().err


def test_forced_encoding_matches(tmp_path: Path) -> None:
    a = _file(tmp_path, "a16.txt", "یک\nدو\n", encoding="utf-16")
    b = _file(tmp_path, "b16.txt", "یک\nسه\n", encoding="utf-16")
    assert main([str(a), str(b), "--encoding", "utf-16"]) == EXIT_DIFFERENCES


def test_binary_files_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"same\x00prefix\n then differs A")
    b.write_bytes(b"same\x00prefix\n then differs B")
    assert main([str(a), str(b)]) == EXIT_DIFFERENCES
    assert capsys.readouterr().out == f"Binary files {a} and {b} differ\n"


def test_output_option_writes_file(tmp_path: Path) -> None:
    a = _file(tmp_path, "a.txt", "old\n")
    b = _file(tmp_path, "b.txt", "new\n")
    out_file = tmp_path / "patch.diff"
    assert main([str(a), str(b), "-o", str(out_file)]) == EXIT_DIFFERENCES
    content = out_file.read_text(encoding="utf-8")
    assert content.startswith(f"--- {a}\n")
    assert "-old\n+new\n" in content


def test_context_option_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _file(tmp_path, "a.txt", "a\nb\nc\nd\ne\n")
    b = _file(tmp_path, "b.txt", "a\nb\nC\nd\ne\n")
    assert main([str(a), str(b), "-U", "0"]) == EXIT_DIFFERENCES
    out = capsys.readouterr().out
    assert "@@ -3 +3 @@\n-c\n+C\n" in out


def test_module_version_subprocess() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, "-m", "atrain", "--version"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == f"atrain {__version__}"
