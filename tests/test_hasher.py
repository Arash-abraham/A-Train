"""Tests for BLAKE2 hashing and the hash-based early exit."""

from __future__ import annotations

from hashlib import blake2b
from pathlib import Path

from atrain.core.hasher import digest_bytes, file_digest, files_identical


def test_digest_bytes_matches_hashlib_reference() -> None:
    for data in (b"", b"a", b"hello world" * 1000):
        expected = blake2b(data, digest_size=16).hexdigest()
        assert digest_bytes(data) == expected


def test_digest_distinguishes_similar_inputs() -> None:
    assert digest_bytes(b"aaa") != digest_bytes(b"aab")
    assert digest_bytes(b"a" * 64) != digest_bytes(b"a" * 65)


def test_file_digest_matches_in_memory_digest(tmp_path: Path) -> None:
    # 2 MiB file: exercises the memory-mapped path inside file_digest.
    payload = (b"atrain-" * (1 << 18))[: 2 << 20]
    path = tmp_path / "big.bin"
    path.write_bytes(payload)
    assert file_digest(path) == digest_bytes(payload)


def test_file_digest_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    assert file_digest(path) == digest_bytes(b"")


def test_files_identical_verdicts(tmp_path: Path) -> None:
    empty_a = tmp_path / "a"
    empty_b = tmp_path / "b"
    empty_a.write_bytes(b"")
    empty_b.write_bytes(b"")
    assert files_identical(empty_a, empty_b) is True  # both empty

    one = tmp_path / "one"
    one_again = tmp_path / "one_again"
    one.write_bytes(b"identical content\n")
    one_again.write_bytes(b"identical content\n")
    assert files_identical(one, one_again) is True

    short = tmp_path / "short"
    short.write_bytes(b"short")
    assert files_identical(one, short) is False  # size mismatch

    other = tmp_path / "other"
    other.write_bytes(b"identical contenT\n")  # same size, different bytes
    assert files_identical(one, other) is False  # digest mismatch is conclusive
