"""Hex rendering for binary change regions (ROADMAP.md, §4 "hex display").

Reads the compared files lazily from the paths recorded in the result's
metadata (binary payloads are never stored in the result model).
"""

from __future__ import annotations

from collections.abc import Iterator

from atrain.core.models import DiffResult
from atrain.core.reader import load_bytes

PREVIEW_BYTES = 48
"""At most this many bytes are hexdumped per side of a region."""


def region_lines(
    result: DiffResult, base_a: str | None = None, base_b: str | None = None
) -> Iterator[str]:
    """Yield hexdump lines for every change region of *result*.

    ``base_a``/``base_b`` override the paths recorded in the result
    (needed when a child result's paths are relative to a tree root).
    """
    from pathlib import Path

    with load_bytes(Path(base_a or result.source.path)) as raw_a, load_bytes(
        Path(base_b or result.target.path)
    ) as raw_b:
        for region in result.regions:
            size = max(region.a_end - region.a_start, region.b_end - region.b_start)
            yield (
                f"@@ binary: 0x{region.a_start:x} (a) / 0x{region.b_start:x} (b) — "
                f"{size} byte(s) @@"
            )
            yield from _side(raw_a.data, region.a_start, region.a_end, "a")
            yield from _side(raw_b.data, region.b_start, region.b_end, "b")
            yield ""


def _side(data: bytes | memoryview, start: int, end: int, label: str) -> Iterator[str]:
    if end <= start:
        yield f"  {label}: <no bytes>"
        return
    shown_end = min(end, start + PREVIEW_BYTES)
    more = end - shown_end
    for line in _hexdump(data, start, shown_end):
        yield f"  {label}: {line}"
    if more > 0:
        yield f"  {label}: ... ({more} more byte(s))"


def _hexdump(data: bytes | memoryview, start: int, end: int, width: int = 16) -> Iterator[str]:
    for offset in range(start, end, width):
        chunk = bytes(data[offset : min(offset + width, end)])
        hex_part = " ".join(f"{byte:02x}" for byte in chunk)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        yield f"{offset:08x}  {hex_part:<{width * 3 - 1}}  |{ascii_part}|"
