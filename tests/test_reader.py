"""Tests for input loading: mmap, decoding, line splitting, newline detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from atrain.core.models import Newline
from atrain.core.reader import (
    MMAP_THRESHOLD,
    decode_text,
    detect_newline,
    line_content,
    load_bytes,
    load_text,
    looks_binary,
    split_lines,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("\n", ["\n"]),
        ("a", ["a"]),
        ("a\n", ["a\n"]),
        ("a\nb", ["a\n", "b"]),
        ("a\nb\n", ["a\n", "b\n"]),
        ("\n\n", ["\n", "\n"]),
        ("a\r\nb\r\n", ["a\r\n", "b\r\n"]),
        ("a\rb\n", ["a\rb\n"]),  # bare CR is content, not a separator
    ],
)
def test_split_lines(text: str, expected: list[str]) -> None:
    assert split_lines(text) == expected


@pytest.mark.parametrize(
    ("line", "expected_content", "expected_newline"),
    [
        ("x\n", "x", True),
        ("x\r\n", "x\r", True),
        ("x", "x", False),
        ("\n", "", True),
    ],
)
def test_line_content(line: str, expected_content: str, expected_newline: bool) -> None:
    content, newline = line_content(line)
    assert content == expected_content
    assert newline is expected_newline


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["a\n", "b\n"], Newline.LF),
        (["a\r\n", "b\r\n"], Newline.CRLF),
        (["a\r\n", "b\n"], Newline.MIXED),
        (["a\r\n", "b\r"], Newline.MIXED),
        (["a\r"], Newline.CR),
        (["a", "b"], Newline.NONE),
        ([], Newline.NONE),
    ],
)
def test_detect_newline(lines: list[str], expected: Newline) -> None:
    assert detect_newline(lines) is expected


def test_load_bytes_small_file_returns_bytes(tmp_path: Path) -> None:
    path = tmp_path / "small.txt"
    path.write_bytes(b"payload")
    loaded = load_bytes(path)
    with loaded:
        assert isinstance(loaded.data, bytes)
        assert loaded.data == b"payload"
        assert loaded.size == 7


def test_load_bytes_large_file_memory_mapped(tmp_path: Path) -> None:
    path = tmp_path / "large.bin"
    payload = b"x" * (MMAP_THRESHOLD + 4096)
    path.write_bytes(payload)
    loaded = load_bytes(path)
    with loaded:
        assert isinstance(loaded.data, memoryview)
        assert loaded._mmap is not None  # noqa: SLF001 — test asserts mapping path
        assert bytes(loaded.data) == payload
    assert loaded._mmap is None  # closed by the context manager


def test_looks_binary() -> None:
    assert looks_binary(b"plain text\x00with nul") is True
    assert looks_binary(b"plain text without nul" * 1000) is False
    assert looks_binary(b"\x00" + b"a" * 10000) is True  # NUL in leading bytes


def test_decode_text_utf8_then_latin1_fallback() -> None:
    text, encoding = decode_text("héllo\n".encode())
    assert text == "héllo\n"
    assert encoding == "utf-8"
    text, encoding = decode_text(b"caf\xe9\n")  # invalid UTF-8, valid latin-1
    assert text == "café\n"
    assert encoding == "latin-1"


def test_decode_text_forced_encoding_is_strict() -> None:
    assert decode_text(b"abc", "ascii") == ("abc", "ascii")
    with pytest.raises(UnicodeDecodeError):
        decode_text(b"\xff\xfe", "utf-8")


def test_load_text_metadata(tmp_path: Path) -> None:
    path = tmp_path / "meta.txt"
    path.write_bytes("خط اول\nsecond\r\n".encode())
    lines, meta = load_text(path)
    assert [line.rstrip("\n") for line in lines] == ["خط اول", "second\r"]
    assert meta.encoding == "utf-8"
    assert meta.newline is Newline.MIXED
    assert meta.is_binary is False
    assert meta.digest is not None


def test_load_text_binary_returns_no_lines(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\x00\x01\x02")
    lines, meta = load_text(path)
    assert lines == []
    assert meta.is_binary is True
