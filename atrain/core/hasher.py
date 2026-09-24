"""Hashing utilities: BLAKE2 digests for files and in-memory data.

The digest provides the hash-based early exit (ROADMAP.md, §3.1): if two
inputs share size and digest they are identical and no diff is attempted.
"""

from __future__ import annotations

import mmap
from hashlib import blake2b
from pathlib import Path

Chunk = bytes | bytearray | memoryview

_CHUNK_SIZE = 1 << 20  # 1 MiB
_DIGEST_SIZE = 16  # 128-bit


def digest_bytes(data: Chunk) -> str:
    """BLAKE2b-128 hex digest of an in-memory byte sequence."""
    return blake2b(data, digest_size=_DIGEST_SIZE).hexdigest()


def file_digest(path: Path) -> str:
    """BLAKE2b-128 hex digest of a file's raw bytes, read in chunks."""
    h = blake2b(digest_size=_DIGEST_SIZE)
    with open(path, "rb") as fh:
        if getattr(fh, "fileno", None) is not None:
            try:
                # Memory-map when possible: the kernel pages in lazily and
                # avoids an extra user-space copy (ROADMAP.md, §3.4).
                with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    h.update(mm[:])
                    return h.hexdigest()
            except (ValueError, OSError):
                # Empty file (mmap of length 0 fails) or unmappable file:
                # fall through to chunked reads.
                pass
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def files_identical(path_a: Path, path_b: Path) -> bool:
    """Hash-based early exit.

    Returns:
        True  — both files are certainly identical (equal size and digest).
        False — different: unequal sizes, or (same size but) unequal
            BLAKE2b-128 digests, which is treated as conclusive.
    """
    size_a = path_a.stat().st_size
    size_b = path_b.stat().st_size
    if size_a != size_b:
        return False
    if size_a == 0:
        return True  # both empty
    return file_digest(path_a) == file_digest(path_b)
