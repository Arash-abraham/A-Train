"""Tests for mode auto-detection and the Git integration."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from atrain.cli import EXIT_DIFFERENCES, EXIT_ERROR, EXIT_SAME, main
from atrain.core.detect import detect_mode
from atrain.gitsupport import parse_external_diff_argv, split_revspec

# ----------------------------------------------------------- auto-detect


def _w(tmp_path: Path, name: str, data: str | bytes) -> Path:
    p = tmp_path / name
    if isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(data, encoding="utf-8")
    return p


def test_detect_dir(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert detect_mode(tmp_path / "a", tmp_path / "b") == "dir"


def test_detect_json_by_extension_and_content(tmp_path: Path) -> None:
    a = _w(tmp_path, "a.json", '{"x": 1}')
    b = _w(tmp_path, "b.json", '{"x": 2}')
    assert detect_mode(a, b) == "json"


def test_detect_invalid_json_falls_back_to_text(tmp_path: Path) -> None:
    a = _w(tmp_path, "a.json", "{not json")
    b = _w(tmp_path, "b.json", '{"x": 2}')
    assert detect_mode(a, b) == "text"


def test_detect_csv(tmp_path: Path) -> None:
    a = _w(tmp_path, "a.csv", "id,name\n1,x\n2,y\n")
    b = _w(tmp_path, "b.csv", "id,name\n1,x\n2,z\n")
    assert detect_mode(a, b) == "csv"


def test_detect_binary(tmp_path: Path) -> None:
    a = _w(tmp_path, "a.bin", b"\x00\x01\x02")
    b = _w(tmp_path, "b.txt", "plain\n")
    assert detect_mode(a, b) == "binary"


def test_detect_mixed_extensions_stay_text(tmp_path: Path) -> None:
    a = _w(tmp_path, "a.json", '{"x": 1}')
    b = _w(tmp_path, "b.txt", '{"x": 2}')
    assert detect_mode(a, b) == "text"


def test_cli_auto_json_uses_semantic_engine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _w(tmp_path, "a.json", '{"b": 1, "a": 1}')
    b = _w(tmp_path, "b.json", '{"a": 1, "b": 1}')
    # Semantically equal despite different key order → no differences.
    assert main([str(a), str(b)]) == EXIT_SAME
    b2 = _w(tmp_path, "c.json", '{"a": 1, "b": 2}')
    assert main(["--format", "json", str(a), str(b2)]) == EXIT_DIFFERENCES
    doc = json.loads(capsys.readouterr().out)
    assert doc["mode"] == "json"


def test_cli_explicit_mode_overrides_auto(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _w(tmp_path, "a.json", '{"b": 1, "a": 1}')
    b = _w(tmp_path, "b.json", '{"a": 1, "b": 1}')
    assert main(["--mode", "text", str(a), str(b)]) == EXIT_DIFFERENCES
    assert "@@" in capsys.readouterr().out


def test_cli_auto_dir(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _w(tmp_path / "a", "f.txt", "1\n")
    _w(tmp_path / "b", "f.txt", "2\n")
    assert main([str(tmp_path / "a"), str(tmp_path / "b")]) == EXIT_DIFFERENCES


# ------------------------------------------------------------------ git


def test_split_revspec() -> None:
    assert split_revspec("") == ("HEAD", None)
    assert split_revspec("HEAD~1") == ("HEAD~1", None)
    assert split_revspec("v1..v2") == ("v1", "v2")
    assert split_revspec("v1...v2") == ("v1", "v2")
    assert split_revspec("..v2") == ("HEAD", "v2")


def test_parse_external_diff_argv_requires_git_env() -> None:
    argv = ["p", "/tmp/o", "0" * 40, "100644", "/tmp/n", "1" * 40, "100644"]
    assert parse_external_diff_argv(argv, {}) is None
    call = parse_external_diff_argv(
        argv, {"GIT_DIFF_PATH_COUNTER": "1", "GIT_DIFF_PATH_TOTAL": "1"}
    )
    assert call is not None
    assert call.old_label == "a/p" and call.new_label == "b/p"
    assert parse_external_diff_argv(argv[:6], {"GIT_DIFF_PATH_COUNTER": "1"}) is None


def test_parse_external_diff_argv_with_leading_options() -> None:
    env = {"GIT_DIFF_PATH_COUNTER": "1", "GIT_DIFF_PATH_TOTAL": "1"}
    argv = ["--format", "side", "p", "/tmp/o", "0" * 40, "100644", "/tmp/n", "1" * 40, "100644"]
    call = parse_external_diff_argv(argv, env)
    assert call is not None
    assert call.options == ("--format", "side") and call.path == "p"
    assert call.new_path is None


def test_parse_external_diff_argv_handles_null_and_rename() -> None:
    env = {"GIT_DIFF_PATH_COUNTER": "1", "GIT_DIFF_PATH_TOTAL": "1"}
    call = parse_external_diff_argv(
        ["old", "/dev/null", "0" * 40, ".", "/tmp/n", "1" * 40, "100644", "new", "090"], env
    )
    assert call is not None
    assert call.old_file is None and call.old_label == "/dev/null"
    assert call.new_label == "b/new" and call.similarity == "090"


git_available = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    run("config", "commit.gpgsign", "false")
    _w(tmp_path, "f.txt", "one\ntwo\n")
    _w(tmp_path, "c.json", '{"a": 1}')
    run("add", ".")
    run("commit", "-qm", "one")
    _w(tmp_path, "f.txt", "one\nTWO\n")
    _w(tmp_path, "c.json", '{"a": 2}')
    run("commit", "-qam", "two")
    return tmp_path


@git_available
def test_git_rev_vs_worktree(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = repo / "f.txt"
    assert main(["--git", "HEAD~1", str(f)]) == EXIT_DIFFERENCES
    out = capsys.readouterr().out
    assert out.startswith(f"--- f.txt@HEAD~1\n+++ {f}\n")
    assert "-two\n+TWO\n" in out


@git_available
def test_git_rev_range_with_auto_mode(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--git", "HEAD~1..HEAD", str(repo / "c.json")]) == EXIT_DIFFERENCES
    out = capsys.readouterr().out
    assert "--- c.json@HEAD~1\n+++ c.json@HEAD\n" in out
    assert "$.a: 1 -> 2" in out  # json engine picked automatically


@git_available
def test_git_same_revision_is_silent(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--git", "HEAD", str(repo / "f.txt")]) == EXIT_SAME
    assert capsys.readouterr().out == ""


@git_available
def test_git_bad_revision_is_error(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--git", "no-such-rev", str(repo / "f.txt")]) == EXIT_ERROR
    assert "git:" in capsys.readouterr().err


def test_git_with_two_positionals_rejected(tmp_path: Path) -> None:
    a = _w(tmp_path, "a", "x")
    assert main(["--git", "HEAD", str(a), str(a)]) == EXIT_ERROR


def test_missing_target_without_git_is_usage_error(tmp_path: Path) -> None:
    a = _w(tmp_path, "a", "x")
    with pytest.raises(SystemExit) as exc:
        main([str(a)])
    assert exc.value.code == 2


def test_git_setup_prints_snippet(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--git-setup"]) == EXIT_SAME
    assert "diff.external atrain" in capsys.readouterr().out


@git_available
def test_external_diff_driver_end_to_end(repo: Path) -> None:
    proc = subprocess.run(
        ["git", "-c", "diff.external=atrain", "diff", "HEAD~1", "HEAD", "--", "f.txt"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "diff --atrain a/f.txt b/f.txt" in proc.stdout
    assert "TWO" in proc.stdout


def test_json_change_order_is_deterministic() -> None:
    from atrain.core.diff_structured import diff_json_strings

    a = '{"z": 1, "m": {"q": 1, "b": 2}, "a": [1]}'
    b = '{"a": [1, 2], "m": {"b": 3, "q": 1, "new": 0}, "k": 9}'
    paths = [n.path for n in diff_json_strings(a, b, "a", "b").nodes]
    assert paths == ["$.z", "$.m.b", "$.m.new", "$.a[1]", "$.k"]
