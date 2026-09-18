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


def decode_text(data: bytes | memoryview, encoding: str | None = None) -> tuple[str, str]:
    """Decode raw bytes to text.

    Args:
        data: Raw file bytes.
        encoding: Forced encoding (strict). When ``None``: try UTF-8 first,
            then fall back to latin-1, which always succeeds and is the
            documented baseline behaviour for v0.1 (refined in v0.2 with
            BOM/UTF-16 detection — ROADMAP.md, §4).

    Returns:
        ``(text, encoding_name)``.
    """
    if encoding is not None:
        return bytes(data).decode(encoding), encoding
    try:
        return bytes(data).decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return bytes(data).decode(FALLBACK_ENCODING), FALLBACK_ENCODING


def split_lines(text: str) -> list[str]:
    """Split *text* into lines on ``\\n`` only, keeping the terminator.

    The final element has no trailing ``\\n`` when the text does not end
    with one; an empty input yields an empty list.
    """
    if not text:
        return []
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


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
        is_binary = looks_binary(loaded.data)
        if is_binary and encoding is None:
            # Auto-detection path: text engines never decode binary
            # payloads; callers decide.  A *forced* encoding overrides the
            # sniff (the user asserted the file is text, like diff --text).
            return [], FileMeta(
                path=str(path), size=loaded.size, digest=digest, is_binary=True
            )
        text, used_encoding = decode_text(loaded.data, encoding)
    lines = split_lines(text)
    meta = FileMeta(
        path=str(path),
        size=loaded.size,
        digest=digest,
        encoding=used_encoding,
        newline=detect_newline(lines),
        is_binary=is_binary,
    )
    return lines, meta
