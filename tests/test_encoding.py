"""Tests for automatic encoding detection (BOM / UTF-8 / UTF-16 / latin-1)."""

from __future__ import annotations

from pathlib import Path

from atrain.core.reader import decode_text, load_text


def test_bom_utf8() -> None:
    data = "héllo\n".encode("utf-8-sig")
    text, encoding = decode_text(data)
    assert text == "héllo\n"
    assert encoding == "utf-8-sig"


def test_bom_utf16_le_and_be() -> None:
    data_le = "سلام\n".encode("utf-16")  # includes native BOM (LE on x86)
    text, encoding = decode_text(data_le)
    assert text == "سلام\n"
    assert encoding == "utf-16"

    data_be = b"\xfe\xff" + "hello\n".encode("utf-16-be")
    text, encoding = decode_text(data_be)
    assert text == "hello\n"
    assert encoding == "utf-16"


def test_utf16_without_bom_detected_by_heuristic() -> None:
    data = "plain ascii text\nsecond line\n".encode("utf-16-le")  # no BOM
    text, encoding = decode_text(data)
    assert text == "plain ascii text\nsecond line\n"
    assert encoding == "utf-16-le"


def test_utf32_bom() -> None:
    data = "x\n".encode("utf-32")
    text, encoding = decode_text(data)
    assert text == "x\n"
    assert encoding == "utf-32"


def test_plain_utf8_preferred() -> None:
    text, encoding = decode_text("naïve\n".encode())
    assert text == "naïve\n"
    assert encoding == "utf-8"


def test_latin1_fallback() -> None:
    text, encoding = decode_text(b"caf\xe9\n")
    assert text == "café\n"
    assert encoding == "latin-1"


def test_forced_encoding_beats_detection(tmp_path: Path) -> None:
    path = tmp_path / "forced.txt"
    path.write_bytes("data\n".encode("utf-16"))
    lines, meta = load_text(path, "utf-16")
    assert lines == ["data\n"]
    assert meta.encoding == "utf-16"


def test_load_text_reports_detected_encoding(tmp_path: Path) -> None:
    path = tmp_path / "u16.txt"
    path.write_bytes("یک\nدو\n".encode("utf-16"))
    lines, meta = load_text(path)
    assert lines == ["یک\n", "دو\n"]
    assert meta.encoding == "utf-16"


def test_invalid_utf16_heuristic_falls_back_to_latin1() -> None:
    # Odd number of NUL-ish bytes that defeats both UTF-8 and the
    # UTF-16 heuristic: must not raise.
    data = b"\xe9\xe9\xe9\xe9\xa1\xa1\xa1\xa1\xa1"  # odd length, high bytes
    text, encoding = decode_text(data)
    assert encoding == "latin-1"
    assert isinstance(text, str)
