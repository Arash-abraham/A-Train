"""Binary diff engine: chunked comparison + rolling-hash region detection.

Algorithm (ROADMAP.md, §4 "binary" mode):

1. Hash-based early exit (size + BLAKE2b digest).
2. Trim the common byte prefix and suffix with block scans, then refine
   the boundary blocks byte-wise — cheap and exact.
3. Walk the differing interior in blocks.  When blocks diverge, try to
   **resync** with a Rabin–Karp-style rolling hash: search a bounded
   window of the *other* file for the current block's fingerprint.  A hit
   after *k* bytes classifies a pure insertion/deletion (``k`` bytes),
   which is reported as its own region instead of one giant "everything
   changed" blob.
4. Resync failure degrades gracefully: the remaining interior becomes a
   single region.  Correctness is unconditional — the postcondition
   (bytes outside reported regions are identical in both files, and every
   differing byte lies inside some region) is property-tested.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from atrain.core.hasher import digest_bytes
from atrain.core.models import BinaryRegion, DiffResult, FileMeta
from atrain.core.reader import load_bytes, looks_binary

BLOCK = 4096
WINDOW = 256  # rolling-hash fingerprint length
MAX_SKIP = 1 << 20  # never search more than 1 MiB for a resync point
SKIP_CANDIDATES = 64  # try needle starts b[pb+c] for c in 0..SKIP_CANDIDATES
_HASH_MOD = (1 << 61) - 1
_HASH_BASE = 1_000_003


def _rolling_init(window: bytes) -> tuple[int, int]:
    """Return ``(hash, base_pow)`` for *window* (polynomial rolling hash)."""
    h = 0
    for byte in window:
        h = (h * _HASH_BASE + byte) % _HASH_MOD
    pow_ = pow(_HASH_BASE, len(window) - 1, _HASH_MOD)
    return h, pow_


def _rolling_next(h: int, pow_: int, drop: int, add: int) -> int:
    """Slide the window one byte: drop *drop*, append *add*."""
    return ((h - drop * pow_) * _HASH_BASE + add) % _HASH_MOD


def _find_any_window(
    scan: bytes | memoryview,
    scan_start: int,
    scan_end: int,
    needle_src: bytes | memoryview,
    needle_start: int,
    window: int,
    max_candidates: int,
) -> tuple[int, int] | None:
    """Find ``(scan_pos, c)`` with ``scan[scan_pos:scan_pos+W] == needle_src[needle_start+c:...]``.

    One rolling pass over *scan* against the candidate needle set
    (``c = 0..max_candidates``); hash matches are verified byte-wise, so
    collisions can never yield a wrong answer.  Returns ``None`` when no
    candidate matches.
    """
    needles: list[tuple[int, bytes, int]] = []
    for c in range(max_candidates + 1):
        start = needle_start + c
        if start + window > len(needle_src):
            break
        needle = bytes(needle_src[start : start + window])
        needles.append((c, needle, _rolling_init(needle)[0]))
    if not needles:
        return None
    w = len(needles[0][1])
    if scan_end - scan_start < w:
        return None
    pow_ = pow(_HASH_BASE, w - 1, _HASH_MOD)
    h, _ = _rolling_init(bytes(scan[scan_start : scan_start + w]))
    for pos in range(scan_start, scan_end - w + 1):
        if h in {nh for _c, _n, nh in needles}:
            for c, needle, nh in needles:
                if h == nh and bytes(scan[pos : pos + w]) == needle:
                    if pos == scan_start and c == 0:
                        break  # no progress; keep scanning
                    return pos, c
        if pos + w < scan_end:
            h = _rolling_next(h, pow_, scan[pos], scan[pos + w])
    return None


def _trim_common_ends(
    a: bytes | memoryview, b: bytes | memoryview
) -> tuple[int, int]:
    """Lengths of the common byte prefix and suffix (block + byte refine)."""
    limit = min(len(a), len(b))
    prefix = 0
    while prefix < limit:
        step = min(BLOCK, limit - prefix)
        if a[prefix : prefix + step] != b[prefix : prefix + step]:
            for k in range(step):
                if a[prefix + k] != b[prefix + k]:
                    return prefix + k, _common_suffix(a, b, limit, prefix + k)
        prefix += step
    return prefix, _common_suffix(a, b, limit, prefix)


def _common_suffix(a: bytes | memoryview, b: bytes | memoryview, limit: int, prefix: int) -> int:
    suffix = 0
    while suffix < limit - prefix:
        step = min(BLOCK, limit - prefix - suffix)
        end_a = len(a) - suffix
        end_b = len(b) - suffix
        if a[end_a - step : end_a] != b[end_b - step : end_b]:
            # Scan the block from its right edge: the first mismatch found
            # this way leaves a maximal common suffix.
            for k in range(1, step + 1):
                if a[end_a - k] != b[end_b - k]:
                    return suffix + k - 1
        suffix += step
    return suffix


def _regions(
    a: bytes | memoryview, b: bytes | memoryview, prefix: int, suffix: int
) -> Iterator[BinaryRegion]:
    """Yield differing regions of the interior via block walk + resync."""
    a_end = len(a) - suffix
    b_end = len(b) - suffix
    pa, pb = prefix, prefix
    while pa < a_end or pb < b_end:
        remaining_a = a_end - pa
        remaining_b = b_end - pb
        step = min(BLOCK, remaining_a, remaining_b)
        if step > 0 and a[pa : pa + step] == b[pb : pb + step]:
            pa += step
            pb += step
            continue
        # Divergence: resync b[pb+c ..] (c = 0..SKIP_CANDIDATES) inside a's
        # near future — handles insertions, deletions *and* small local
        # rewrites that only corrupt the first bytes of the needle.
        w = max(8, min(WINDOW, remaining_b))
        hit = _find_any_window(
            a, pa, min(a_end, pa + MAX_SKIP), b, pb, w, SKIP_CANDIDATES
        ) if remaining_b >= w else None
        if hit is not None:
            a_pos, c = hit
            yield BinaryRegion(pa, a_pos, pb, pb + c)
            pa, pb = a_pos, pb + c
            continue
        w = max(8, min(WINDOW, remaining_a))
        hit = _find_any_window(
            b, pb, min(b_end, pb + MAX_SKIP), a, pa, w, SKIP_CANDIDATES
        ) if remaining_a >= w else None
        if hit is not None:
            b_pos, c = hit
            yield BinaryRegion(pa, pa + c, pb, b_pos)
            pa, pb = pa + c, b_pos
            continue
        # No resync within reach: one coarse region for the rest.
        yield BinaryRegion(pa, a_end, pb, b_end)
        return


def compare_binary(path_a: Path, path_b: Path) -> DiffResult:
    """Compare two files byte-wise, reporting change regions."""
    with load_bytes(path_a) as raw_a, load_bytes(path_b) as raw_b:
        meta_a = FileMeta(
            path=str(path_a),
            size=raw_a.size,
            digest=digest_bytes(raw_a.data),
            is_binary=looks_binary(raw_a.data),
        )
        meta_b = FileMeta(
            path=str(path_b),
            size=raw_b.size,
            digest=digest_bytes(raw_b.data),
            is_binary=looks_binary(raw_b.data),
        )
        result = DiffResult(mode="binary", source=meta_a, target=meta_b, identical=False)
        if meta_a.digest == meta_b.digest and meta_a.size == meta_b.size:
            result.identical = True
            return result
        prefix, suffix = _trim_common_ends(raw_a.data, raw_b.data)
        result.regions = list(_regions(raw_a.data, raw_b.data, prefix, suffix))
        return result


def hexdump(data: bytes | memoryview, start: int, end: int, width: int = 16) -> Iterator[str]:
    """Classic hexdump lines for ``data[start:end]`` (offset + hex + ASCII)."""
    for offset in range(start, end, width):
        chunk = bytes(data[offset : min(offset + width, end)])
        hex_part = " ".join(f"{byte:02x}" for byte in chunk)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        yield f"{offset:08x}  {hex_part:<{width * 3 - 1}}  |{ascii_part}|"
