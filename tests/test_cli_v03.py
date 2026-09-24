"""CLI tests for v0.3 modes: binary, json, csv, dir."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atrain.cli import EXIT_ERROR, EXIT_SAME, main


def test_binary_mode_identical_exit_zero(tmp_path: Path) -> None:
    data = b"binary\x00payload\n"
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(data)
    b.write_bytes(data)
    assert main(["--mode", "binary", str(a), str(b)]) == EXIT_SAME


def test_binary_mode_hex_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"same-prefix-XYZ-suffix")
    b.write_bytes(b"same-prefix-xyz-suffix")
    assert main(["--mode", "binary", str(a), str(b)]) == 1
    out = capsys.readouterr().out
    # Skip-resync pairs the whole changed run: "XYZ" vs "xyz" (3 bytes).
    assert "3 byte(s)" in out
    assert "58 59 5a" in out  # "XYZ" in hex on side a
    assert "78 79 7a" in out  # "xyz" in hex on side b


def test_binary_mode_json_regions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"AAAA" + b"\x01")
    b.write_bytes(b"AAAA" + b"\x02")
    assert main(["--mode", "binary", "--format", "json", str(a), str(b)]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["mode"] == "binary"
    assert doc["regions"][0]["a_start"] == 4


def test_json_mode_reordered_keys_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text('{"a": 1, "b": 2}', encoding="utf-8")
    b.write_text('{\n  "b": 2,\n  "a": 1\n}', encoding="utf-8")
    assert main(["--mode", "json", str(a), str(b)]) == EXIT_SAME
    assert capsys.readouterr().out == ""


def test_json_mode_path_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text('{"count": 3}', encoding="utf-8")
    b.write_text('{"count": 4}', encoding="utf-8")
    assert main(["--mode", "json", str(a), str(b)]) == 1
    out = capsys.readouterr().out
    assert "~ $.count: 3 -> 4" in out


def test_json_mode_invalid_json_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text("{not json", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")
    assert main(["--mode", "json", str(a), str(b)]) == EXIT_ERROR
    assert "invalid JSON" in capsys.readouterr().err


def test_csv_mode_with_key_column(tmp_path: Path) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text("id,qty\n7,1\n", encoding="utf-8")
    b.write_text("id,qty\n7,2\n", encoding="utf-8")
    assert main(["--mode", "csv", "--key-col", "id", str(a), str(b)]) == 1
    assert main(["--mode", "csv", "--key-col", "1", str(a), str(b)]) == 1


def test_csv_mode_unknown_key_column_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text("id,qty\n7,1\n", encoding="utf-8")
    b.write_text("id,qty\n7,2\n", encoding="utf-8")
    assert main(["--mode", "csv", "--key-col", "nope", str(a), str(b)]) == EXIT_ERROR
    assert "not found" in capsys.readouterr().err


def test_dir_mode_exit_codes_and_layout(tmp_path: Path) -> None:
    ta = tmp_path / "v1"
    tb = tmp_path / "v2"
    (ta / "sub").mkdir(parents=True)
    (tb / "sub").mkdir(parents=True)
    (ta / "sub" / "mod.txt").write_text("one\n", encoding="utf-8")
    (tb / "sub" / "mod.txt").write_text("two\n", encoding="utf-8")
    (ta / "removed.txt").write_text("x\n", encoding="utf-8")
    (tb / "added.txt").write_text("y\n", encoding="utf-8")
    assert main(["--mode", "dir", str(ta), str(tb)]) == 1
    # Identical trees exit 0 silently.
    tc = tmp_path / "v3"
    (tc / "sub").mkdir(parents=True)
    (tc / "sub" / "mod.txt").write_text("one\n", encoding="utf-8")
    (tc / "removed.txt").write_text("x\n", encoding="utf-8")
    assert main(["--mode", "dir", str(ta), str(tc)]) == EXIT_SAME


def test_dir_mode_requires_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b"
    a.write_text("x\n", encoding="utf-8")
    b.mkdir()
    assert main(["--mode", "dir", str(a), str(b)]) == EXIT_ERROR
    assert "requires directories" in capsys.readouterr().err


def test_side_format_rejected_for_json_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text("{}", encoding="utf-8")
    b.write_text('{"x": 1}', encoding="utf-8")
    assert main(["--mode", "json", "--format", "side", str(a), str(b)]) == EXIT_ERROR
    assert "side-by-side" in capsys.readouterr().err


def test_dir_mode_json_document_includes_children(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ta = tmp_path / "v1"
    tb = tmp_path / "v2"
    ta.mkdir()
    tb.mkdir()
    (ta / "m.txt").write_text("one\n", encoding="utf-8")
    (tb / "m.txt").write_text("two\n", encoding="utf-8")
    assert main(["--mode", "dir", "--format", "json", str(ta), str(tb)]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["mode"] == "dir"
    assert doc["children"]["m.txt"]["hunks"]


def test_workers_option_accepted(tmp_path: Path) -> None:
    ta = tmp_path / "v1"
    tb = tmp_path / "v2"
    ta.mkdir()
    tb.mkdir()
    (ta / "f.txt").write_text("x\n", encoding="utf-8")
    (tb / "f.txt").write_text("x\n", encoding="utf-8")
    assert main(["--mode", "dir", "--workers", "2", str(ta), str(tb)]) == EXIT_SAME
