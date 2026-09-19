"""Tests for directory-tree comparison (parallel hashing, deterministic)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from atrain.core.diff_tree import TreeOptions, compare_trees
from atrain.core.models import DiffResult, LineTag


def _make_tree(root: Path, files: dict[str, str | bytes]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")


def _entries(result: DiffResult, change: str) -> list[str]:
    return [e.path for e in result.entries if e.change == change]


def test_identical_trees(tmp_path: Path) -> None:
    files = {"a.txt": "one\n", "sub/b.txt": "two\n", "sub/deep/c.txt": "three\n"}
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, files)
    _make_tree(tb, files)
    result = compare_trees(ta, tb)
    assert result.identical
    assert set(_entries(result, "unchanged")) == set(files)
    assert result.children == {}


def test_added_removed_modified_classified(tmp_path: Path) -> None:
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, {"keep.txt": "k\n", "gone.txt": "g\n", "mod.txt": "old\n"})
    _make_tree(tb, {"keep.txt": "k\n", "mod.txt": "new\n", "fresh.txt": "f\n"})
    result = compare_trees(ta, tb)
    assert _entries(result, "added") == ["fresh.txt"]
    assert _entries(result, "removed") == ["gone.txt"]
    assert _entries(result, "modified") == ["mod.txt"]
    assert not result.identical
    # Per-file diff attached for the modified text file.
    assert "mod.txt" in result.children
    child = result.children["mod.txt"]
    assert child.hunks
    delete = next(
        line for line in child.hunks[0].lines if line.tag is LineTag.DELETE
    )
    assert delete.text == "old"


def test_empty_directories_reported(tmp_path: Path) -> None:
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, {"f.txt": "x\n"})
    ta.mkdir(exist_ok=True)
    tb.mkdir()
    (ta / "gone_dir").mkdir()
    (tb / "new_dir").mkdir()
    result = compare_trees(ta, tb)
    assert _entries(result, "added") == ["new_dir/"]
    assert _entries(result, "removed") == ["f.txt", "gone_dir/"]


def test_binary_files_in_tree(tmp_path: Path) -> None:
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, {"blob.bin": b"\x00\x01\x02same"})
    _make_tree(tb, {"blob.bin": b"\x00\x01\x02diff"})
    result = compare_trees(ta, tb)
    assert _entries(result, "modified") == ["blob.bin"]
    # Binary payloads get a region-based child diff, not a textual one.
    child = result.children["blob.bin"]
    assert child.mode == "binary"
    assert child.regions and not child.hunks


def test_nested_modified_file_paths(tmp_path: Path) -> None:
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, {"sub/deep/mod.txt": "one\n"})
    _make_tree(tb, {"sub/deep/mod.txt": "two\n"})
    result = compare_trees(ta, tb)
    assert _entries(result, "modified") == ["sub/deep/mod.txt"]
    assert "sub/deep/mod.txt" in result.children


def test_parallel_and_sequential_agree(tmp_path: Path) -> None:
    files = {f"f{i}.txt": f"content {i}\n" for i in range(30)}
    files["mod.txt"] = "before\n"
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, files)
    _make_tree(tb, files)
    (tb / "mod.txt").write_text("after\n", encoding="utf-8")
    sequential = compare_trees(ta, tb, TreeOptions(workers=1, diff_modified=False))
    parallel = compare_trees(ta, tb, TreeOptions(workers=4, diff_modified=False))
    assert [e.path + e.change for e in sequential.entries] == [
        e.path + e.change for e in parallel.entries
    ]
    assert parallel.identical == sequential.identical == False  # noqa: E712


def test_results_are_deterministic(tmp_path: Path) -> None:
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, {f"f{i}.txt": str(i) + "\n" for i in range(20)} | {"old.txt": "x\n"})
    _make_tree(tb, {f"f{i}.txt": str(i) + "\n" for i in range(20)} | {"new.txt": "x\n"})
    runs = [compare_trees(ta, tb, TreeOptions(diff_modified=False)) for _ in range(3)]
    paths = [[(e.path, e.change) for e in r.entries] for r in runs]
    assert paths[0] == paths[1] == paths[2]


@pytest.mark.skipif(os.geteuid() == 0, reason="permissions are not enforced for root")
def test_unreadable_file_yields_error_entry(tmp_path: Path) -> None:
    ta, tb = tmp_path / "a", tmp_path / "b"
    _make_tree(ta, {"secret.txt": "s\n"})
    _make_tree(tb, {"secret.txt": "s\n"})
    (ta / "secret.txt").chmod(0o000)
    try:
        result = compare_trees(ta, tb, TreeOptions(workers=1))
    finally:
        (ta / "secret.txt").chmod(0o644)
    assert _entries(result, "error") == ["secret.txt"]
    assert not result.identical
    assert result.errors


def test_workers_none_resolves() -> None:
    from atrain.core.diff_tree import _resolve_workers

    assert _resolve_workers(None) >= 1
    assert _resolve_workers(3) == 3
    assert _resolve_workers(0) >= 1
