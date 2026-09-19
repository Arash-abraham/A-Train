"""Input loading: memory-mapped reads, binary sniffing, text decoding, line splitting.

Large inputs are memory-mapped rather than copied (ROADMAP.md, §3.4); small
inputs are read directly since mapping overhead dominates below ~1 MiB.
Line splitting deliberately recognises only ``\\n`` as a terminator (with
``\\r\\n`` handled by keeping ``\\r`` as line content, matching GNU diff) —
never the wider Unicode line boundaries of ``str.splitlines``.
"""

from __future__ import annotations

import mmap
from dataclasses import dataclass
from pathlib import Path

from atrain.core.hasher import digest_bytes
from atrain.core.models import FileMeta, Newline

MMAP_THRESHOLD = 1 << 20  # 1 MiB
BINARY_SNIFF_BYTES = 8192
FALLBACK_ENCODING = "latin-1"


@dataclass(slots=True)
class LoadedFile:
    """Raw byte content of a file plus its memory-map handle (if any).

    ``close`` releases the exported memory view *before* closing the map
    (closing an ``mmap`` with live exports raises ``BufferError``).
    """

    data: bytes | memoryview
    size: int
    _mmap: mmap.mmap | None = None
    _view: memoryview | None = None

    def close(self) -> None:
        view, self._view = self._view, None
        if view is not None:
            view.release()
        handle, self._mmap = self._mmap, None
        if handle is not None:
            handle.close()

    def __enter__(self) -> LoadedFile:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def load_bytes(path: Path) -> LoadedFile:
    """Load a file's bytes, memory-mapping when large enough to benefit."""
    size = path.stat().st_size
    if size >= MMAP_THRESHOLD:
        with open(path, "rb") as fh:
            try:
                mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            except (ValueError, OSError):
                pass
            else:
                view = memoryview(mm)
                return LoadedFile(data=view, size=size, _mmap=mm, _view=view)
    return LoadedFile(data=path.read_bytes(), size=size)


def looks_binary(data: bytes | memoryview) -> bool:
    """Sniff for a NUL byte in the leading bytes (GNU diff heuristic)."""
    return b"\x00" in bytes(data[:BINARY_SNIFF_BYTES])


def has_bom(data: bytes | memoryview) -> bool:
    """True when the data starts with a known Unicode BOM."""
    head = bytes(data[:4])
    return any(head.startswith(bom) for bom, _name in _BOMS)


def is_textual(data: bytes | memoryview) -> bool:
    """Decidable-as-text check used before refusing to decode.

    Text if: a BOM is present (BOM-bearing UTF-16/32 legitimately contain
    NUL bytes), the NUL sniff is clean, or the data matches the
    UTF-16-without-BOM byte pattern.
    """
    if has_bom(data):
        return True
    if not looks_binary(data):
        return True
    return _looks_utf16_without_bom(data) is not None


_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32"),  # LE (before UTF-16 LE prefix!)
    (b"\x00\x00\xfe\xff", "utf-32"),  # BE
    (b"\xff\xfe", "utf-16"),  # LE
    (b"\xfe\xff", "utf-16"),  # BE
)


def _looks_utf16_without_bom(data: bytes | memoryview) -> str | None:
    """Heuristic: every second byte NUL across a long ASCII-ish prefix."""
    view = bytes(data[:BINARY_SNIFF_BYTES])
    if len(view) < 8 or len(view) % 2 != 0:
        return None
    even_nul = sum(1 for i in range(0, len(view), 2) if view[i] == 0)
    odd_nul = sum(1 for i in range(1, len(view), 2) if view[i] == 0)
    half = len(view) // 2
    if even_nul > half * 0.9:
        return "utf-16-be"  # NULs at even offsets => big-endian
    if odd_nul > half * 0.9:
        return "utf-16-le"
    return None


def decode_text(data: bytes | memoryview, encoding: str | None = None) -> tuple[str, str]:
    """Decode raw bytes to text (ROADMAP.md, §4: UTF-8 → UTF-16 → latin-1).

    Args:
        data: Raw file bytes.
        encoding: Forced encoding (strict, overrides all detection).
        When ``None``: BOM sniff (UTF-8/16/32), then strict UTF-8, then a
        UTF-16-without-BOM heuristic, then latin-1, which always succeeds.

    Returns:
        ``(text, encoding_name)``.
    """
    if encoding is not None:
        return bytes(data).decode(encoding), encoding
    head = bytes(data[:8])
    for bom, name in _BOMS:
        if head.startswith(bom):
            return bytes(data).decode(name), name
    if not looks_binary(data):
        try:
            return bytes(data).decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            pass
    # NUL-bearing data without a BOM: UTF-8 "succeeds" on NULs but yields
    # mojibake, so try the UTF-16 pattern before giving up to latin-1.
    guessed = _looks_utf16_without_bom(data)
    if guessed is not None:
        try:
            return bytes(data).decode(guessed), guessed
        except UnicodeDecodeError:
            pass
    return bytes(data).decode(FALLBACK_ENCODING), FALLBACK_ENCODING


def split_lines(text: str) -> list[str]:
    """Split *text* into lines on ``\\n`` only, keeping the terminator.

    The final element has no trailing ``\\n`` when the text does not end
    with one; an empty input yields an empty list.
    """
    if not text:
        return []
    parts = text.split("\n")
    last = parts.pop()
    lines = [part + "\n" for part in parts]
    if last:
        lines.append(last)
    return lines


def _split_and_classify(text: str) -> tuple[list[str], Newline]:
    """``split_lines`` + ``detect_newline`` fused into one function.

    Saves the three extra full passes ``detect_newline`` would make over
    the line list (py-spy: ~12% of a 30 MB comparison, 2026-09-18).
    Semantics are identical to calling both functions.
    """
    if not text:
        return [], Newline.NONE
    parts = text.split("\n")
    last = parts.pop()
    lines = [part + "\n" for part in parts]
    if last:
        lines.append(last)
    has_lf = has_crlf = has_cr = False
    for line in lines:
        if not line.endswith("\n"):
            if line.endswith("\r"):
                has_cr = True
            continue
        if line.endswith("\r\n"):
            has_crlf = True
        else:
            has_lf = True
    if has_crlf and (has_lf or has_cr):
        newline = Newline.MIXED
    elif has_crlf:
        newline = Newline.CRLF
    elif has_lf:
        newline = Newline.LF
    elif has_cr:
        newline = Newline.CR
    else:
        newline = Newline.NONE
    return lines, newline


def line_content(line: str) -> tuple[str, bool]:
    """Return ``(content_without_terminator, ends_with_newline)``.

    ``\\r`` immediately before ``\\n`` is kept as content, mirroring GNU
    diff; CRLF *normalisation for comparison* is a separate, explicit
    ignore option introduced with the ignore options.
    """
    if line.endswith("\n"):
        return line[:-1], True
    return line, False


def detect_newline(lines: list[str]) -> Newline:
    """Classify the dominant newline style of already-split lines."""
    has_lf = any(
        line.endswith("\n") and not line.endswith("\r\n") for line in lines
    )
    has_crlf = any(line.endswith("\r\n") for line in lines)
    has_cr = any(
        line.endswith("\r") and not line.endswith("\r\n") for line in lines
    )
    if has_crlf and (has_lf or has_cr):
        return Newline.MIXED
    if has_crlf:
        return Newline.CRLF
    if has_lf:
        return Newline.LF
    if has_cr:
        return Newline.CR
    return Newline.NONE


def load_text(path: Path, encoding: str | None = None) -> tuple[list[str], FileMeta]:
    """Load and decode *path* into split lines with metadata.

    Raises:
        OSError: Propagated from file access; callers translate to CLI errors.
    """
    with load_bytes(path) as loaded:
        digest = digest_bytes(loaded.data)
        is_binary = not is_textual(loaded.data)
        if is_binary and encoding is None:
            # Auto-detection path: text engines never decode binary
            # payloads; callers decide.  A *forced* encoding overrides the
            # sniff (the user asserted the file is text, like diff --text).
            return [], FileMeta(
                path=str(path), size=loaded.size, digest=digest, is_binary=True
            )
        text, used_encoding = decode_text(loaded.data, encoding)
    lines, newline = _split_and_classify(text)
    meta = FileMeta(
        path=str(path),
        size=loaded.size,
        digest=digest,
        encoding=used_encoding,
        newline=newline,
        is_binary=is_binary,
    )
    return lines, meta
