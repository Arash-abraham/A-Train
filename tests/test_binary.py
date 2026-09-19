"""Tests for the binary diff engine (chunked compare + rolling-hash resync)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from atrain.core.diff_binary import (
    MAX_SKIP,
    WINDOW,
    _trim_common_ends,
    compare_binary,
    hexdump,
)
from atrain.core.models import BinaryRegion

RNG_SEED = 1234


def _pseudo_random_bytes(length: int, seed: int = RNG_SEED) -> bytes:
    state = seed
    out = bytearray(length)
    for i in range(length):
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        out[i] = (state >> 33) & 0xFF
    return bytes(out)


def _assert_region_invariant(a: bytes, b: bytes, regions: list[BinaryRegion]) -> None:
    """Every byte outside the regions is identical; every differing byte is covered.

    Regions pair an a-range with a b-range, so validity means: walking the
    files, replacing each a-region with its b-region reproduces *b* exactly.
    """
    rebuilt = bytearray()
    pos_a = 0
    for region in regions:
        assert region.a_start >= pos_a, "regions overlap or unsorted"
        rebuilt += a[pos_a : region.a_start]
        rebuilt += b[region.b_start : region.b_end]
        pos_a = region.a_end
    rebuilt += a[pos_a:]
    assert bytes(rebuilt) == b, "regions do not reconstruct b from a"


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_identical_binary_files(tmp_path: Path) -> None:
    data = _pseudo_random_bytes(100_000)
    result = compare_binary(_write(tmp_path, "a.bin", data), _write(tmp_path, "b.bin", data))
    assert result.identical
    assert result.regions == []


def test_single_byte_difference(tmp_path: Path) -> None:
    data = _pseudo_random_bytes(50_000)
    changed = data[:1234] + bytes([data[1234] ^ 0xFF]) + data[1235:]
    result = compare_binary(_write(tmp_path, "a.bin", data), _write(tmp_path, "b.bin", changed))
    assert not result.identical
    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.a_start == 1234 and region.a_end == 1235
    assert region.b_start == 1234 and region.b_end == 1235
    _assert_region_invariant(data, changed, result.regions)


def test_pure_insertion_in_middle(tmp_path: Path) -> None:
    data = _pseudo_random_bytes(20_000)
    inserted = data[:10_000] + _pseudo_random_bytes(1_000, seed=99) + data[10_000:]
    result = compare_binary(_write(tmp_path, "a.bin", data), _write(tmp_path, "b.bin", inserted))
    assert not result.identical
    total_inserted = sum(r.b_end - r.b_start for r in result.regions)
    total_removed = sum(r.a_end - r.a_start for r in result.regions)
    assert total_inserted == 1_000 and total_removed == 0
    _assert_region_invariant(data, inserted, result.regions)


def test_pure_deletion_in_middle(tmp_path: Path) -> None:
    data = _pseudo_random_bytes(20_000)
    deleted = data[:10_000] + data[10_500:]
    result = compare_binary(_write(tmp_path, "a.bin", data), _write(tmp_path, "b.bin", deleted))
    total_removed = sum(r.a_end - r.a_start for r in result.regions)
    total_inserted = sum(r.b_end - r.b_start for r in result.regions)
    assert total_removed == 500 and total_inserted == 0
    _assert_region_invariant(data, deleted, result.regions)


def test_multiple_separated_regions(tmp_path: Path) -> None:
    data = _pseudo_random_bytes(60_000)
    changed = bytearray(data)
    for offset in (5_000, 30_000, 55_000):
        changed[offset : offset + 3] = b"\xfa\xfb\xfc"
    b_data = bytes(changed)
    result = compare_binary(
        _write(tmp_path, "a.bin", data), _write(tmp_path, "b.bin", b_data)
    )
    assert len(result.regions) >= 3
    _assert_region_invariant(data, b_data, result.regions)


def test_completely_different_files_one_region(tmp_path: Path) -> None:
    a = _pseudo_random_bytes(8_000, seed=1)
    b = _pseudo_random_bytes(8_000, seed=2)
    result = compare_binary(_write(tmp_path, "a.bin", a), _write(tmp_path, "b.bin", b))
    assert not result.identical
    assert len(result.regions) >= 1
    _assert_region_invariant(a, b, result.regions)


def test_large_insertion_within_resync_window(tmp_path: Path) -> None:
    data = _pseudo_random_bytes(200_000)
    blob = _pseudo_random_bytes(100_000, seed=77)
    inserted = data[:100_000] + blob + data[100_000:]
    result = compare_binary(_write(tmp_path, "a.bin", data), _write(tmp_path, "b.bin", inserted))
    # 100 KB < MAX_SKIP: the engine should classify this as one insertion.
    assert sum(r.b_end - r.b_start for r in result.regions) == 100_000
    _assert_region_invariant(data, inserted, result.regions)


def test_trim_common_ends_exactness() -> None:
    a = b"common-prefix" + b"XX" + b"common-suffix"
    b = b"common-prefix" + b"YY" + b"common-suffix"
    prefix, suffix = _trim_common_ends(a, b)
    assert prefix == len(b"common-prefix")
    assert a[:prefix] == b[:prefix] == b"common-prefix"
    assert a[len(a) - suffix :] == b[len(b) - suffix :] == b"common-suffix"
    assert prefix + suffix == len(a) - 2


def test_window_constants_sane() -> None:
    assert 0 < WINDOW < MAX_SKIP


def test_hexdump_format() -> None:
    lines = list(hexdump(b"A-Train\x00\xffz", 0, 10, width=8))
    assert len(lines) == 2
    assert lines[0].startswith("00000000")
    assert "|A-Train.|" in lines[0]  # 8 bytes: 7 chars + NUL
    assert lines[1].startswith("00000008")
    assert "|.z|" in lines[1]  # \xff renders as one dot


def test_size_mismatch_detected_without_regions_work(tmp_path: Path) -> None:
    a = _pseudo_random_bytes(10_000)
    result = compare_binary(_write(tmp_path, "a.bin", a), _write(tmp_path, "b.bin", a + b"tail"))
    assert not result.identical
    _assert_region_invariant(a, a + b"tail", result.regions)


@pytest.mark.skipif(os.geteuid() == 0, reason="permissions are not enforced for root")
def test_unreadable_binary_reports_error(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.bin", b"data")
    b = _write(tmp_path, "b.bin", b"data")
    a.chmod(0o000)
    try:
        with pytest.raises(OSError):
            compare_binary(a, b)
    finally:
        a.chmod(0o644)
