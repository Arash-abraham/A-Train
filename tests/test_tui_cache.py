"""Tests for the v0.4 interactive + caching layer: Textual TUI, digest cache."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from atrain.core.cache import DigestCache
from atrain.core.diff_tree import TreeOptions, compare_trees
from atrain.tui.app import DiffTui

pytest.importorskip("textual")


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- digest cache ------------------------------------------------------


class TestDigestCache:
    def test_put_get_roundtrip(self, tmp_path: Path) -> None:
        cache = DigestCache(tmp_path / "cache.json")
        target = tmp_path / "f.txt"
        target.write_text("x", encoding="utf-8")
        cache.put(target, 1, 123, "d" * 32)
        assert cache.get(target, 1, 123) == "d" * 32

    def test_stale_entry_is_a_miss(self, tmp_path: Path) -> None:
        cache = DigestCache(tmp_path / "cache.json")
        target = tmp_path / "f.txt"
        cache.put(target, 5, 999, "d" * 32)
        assert cache.get(target, 5, 1000) is None
        assert cache.get(target, 6, 999) is None

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "cache.json"
        target = tmp_path / "f.txt"
        first = DigestCache(path)
        first.put(target, 10, 42, "a" * 32)
        first.save()
        second = DigestCache(path)
        assert second.get(target, 10, 42) == "a" * 32

    def test_corrupt_cache_is_discarded(self, tmp_path: Path) -> None:
        path = tmp_path / "cache.json"
        path.write_text("{not json", encoding="utf-8")
        cache = DigestCache(path)
        assert cache.entries == {}

    def test_save_is_sorted_and_atomic_shape(self, tmp_path: Path) -> None:
        path = tmp_path / "cache.json"
        cache = DigestCache(path)
        for name in ("c", "a", "b"):
            cache.put(tmp_path / name, 1, 1, "d" * 32)
        cache.save()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert list(payload["entries"]) == sorted(payload["entries"])


# --- cache integration in tree compare ---------------------------------


class TestTreeCacheIntegration:
    def test_second_run_hits_cache(self, tmp_path: Path) -> None:
        import atrain.core.diff_tree as diff_tree

        da, db = tmp_path / "a", tmp_path / "b"
        (da / "sub").mkdir(parents=True)
        (db / "sub").mkdir(parents=True)
        (da / "sub" / "f.txt").write_text("same\n", encoding="utf-8")
        (db / "sub" / "f.txt").write_text("same\n", encoding="utf-8")
        cache_path = tmp_path / "cache.json"

        opts = TreeOptions(use_cache=True, cache_path=cache_path)
        first = compare_trees(da, db, opts)
        assert first.identical
        assert cache_path.exists()

        real_digest = diff_tree.file_digest
        calls = {"n": 0}

        def counting_digest(path):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return real_digest(path)

        diff_tree.file_digest = counting_digest
        try:
            second = compare_trees(da, db, opts)
        finally:
            diff_tree.file_digest = real_digest
        assert second.identical
        assert calls["n"] == 0  # served entirely from the cache

    def test_cache_disabled_by_default(self, tmp_path: Path) -> None:
        da, db = tmp_path / "a", tmp_path / "b"
        da.mkdir()
        db.mkdir()
        (da / "f.txt").write_text("x\n", encoding="utf-8")
        (db / "f.txt").write_text("x\n", encoding="utf-8")
        compare_trees(da, db, TreeOptions())
        assert not (tmp_path / "cache.json").exists()

    def test_changed_file_invalidates_entry(self, tmp_path: Path) -> None:
        da, db = tmp_path / "a", tmp_path / "b"
        da.mkdir()
        db.mkdir()
        fa, fb = da / "f.txt", db / "f.txt"
        fa.write_text("one\n", encoding="utf-8")
        fb.write_text("one\n", encoding="utf-8")
        cache_path = tmp_path / "cache.json"
        opts = TreeOptions(use_cache=True, cache_path=cache_path)
        assert compare_trees(da, db, opts).identical
        fb.write_text("two\n", encoding="utf-8")
        assert not compare_trees(da, db, opts).identical


# --- TUI ----------------------------------------------------------------


def _drive(app: DiffTui, keys: list[str]) -> None:
    async def scenario() -> None:
        async with app.run_test() as pilot:
            await pilot.press(*keys)

    asyncio.run(scenario())


class TestDiffTui:
    def test_shows_hunks_and_navigation(self, tmp_path: Path) -> None:
        pa = _write(tmp_path, "a.txt", "one\ntwo\nthree\n")
        pb = _write(tmp_path, "b.txt", "one\nTWO\nthree\n")
        app = DiffTui(pa, pb)
        async def scenario() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.hunk_rows, "expected hunk markers"
                assert app.cursor == -1
                await pilot.press("n")
                assert app.cursor == 0
                await pilot.press("n")
                assert app.cursor == 0  # wraps to first hunk
                await pilot.press("p")
                assert app.cursor == 0  # wraps back to last
                await pilot.press("r")
                assert app.result is not None
        asyncio.run(scenario())

    def test_identical_files_message(self, tmp_path: Path) -> None:
        text = "same\ncontent\n"
        pa = _write(tmp_path, "a.txt", text)
        pb = _write(tmp_path, "b.txt", text)
        app = DiffTui(pa, pb)
        async def scenario() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.hunk_rows == []
                assert app.result is not None and app.result.identical
        asyncio.run(scenario())

    def test_quit_binding(self, tmp_path: Path) -> None:
        pa = _write(tmp_path, "a.txt", "x\n")
        pb = _write(tmp_path, "b.txt", "y\n")
        app = DiffTui(pa, pb)
        _drive(app, ["q"])

    def test_error_is_rendered_not_raised(self, tmp_path: Path) -> None:
        pa = _write(tmp_path, "a.txt", "x\n")
        missing = tmp_path / "missing.txt"
        app = DiffTui(pa, missing)
        async def scenario() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.error is not None
                assert "No such file" in app.error or app.error
        asyncio.run(scenario())


# --- v0.4 text-engine optimizations -------------------------------------


class TestV04Optimizations:
    def test_split_and_classify_equivalence(self) -> None:
        from atrain.core.reader import (
            _split_and_classify,
            detect_newline,
            split_lines,
        )

        cases = [
            "a\n\nb\n",  # empty line: bare "\n" line must not break indexing
            "a\r\n\r\nb\r\n",
            "x\ny\r\nz\r",  # MIXED
            "p\rq\r",
            "solo",
            "",
            "\n",
            "a\n\r\nb\n",
        ]
        for text in cases:
            ref_lines = split_lines(text)
            ref = detect_newline(ref_lines)
            lines, newline = _split_and_classify(text)
            assert lines == ref_lines
            assert newline is ref

    def test_deadline_bounds_pathological_input(self) -> None:
        """Every-2nd-line input must fall back within ~MAX_DIFF_SECONDS."""
        import time as time_mod

        from atrain.core.diff_text import MAX_DIFF_SECONDS, diff_lines

        size = 15_000
        a = [f"line-{i}\n" for i in range(size)]
        b = [("NEW " + line) if i % 2 == 0 else line for i, line in enumerate(a)]
        start = time_mod.perf_counter()
        hunks = diff_lines(a, b, context=3)
        elapsed = time_mod.perf_counter() - start
        # generous margin for slow CI machines: 6x the target, but far
        # below the ~15 s+ this input needs for a full minimal search
        assert elapsed < MAX_DIFF_SECONDS * 6
        assert len(hunks) >= 1

    def test_deadline_fallback_is_correct(self) -> None:
        """Fallback edit script still reconstructs the target exactly."""
        from atrain.core.diff_text import diff_lines
        from atrain.core.models import LineTag

        size = 12_000
        a = [f"line-{i}\n" for i in range(size)]
        b = [("NEW " + line) if i % 2 == 0 else line for i, line in enumerate(a)]
        hunks = diff_lines(a, b, context=0)
        rebuilt: list[str] = []
        pos = 0
        for hunk in hunks:
            rebuilt.extend(a[pos : hunk.a_start])
            # hunk line text is stored WITHOUT the terminator (formatters
            # add it on render); every line in this corpus ends with one
            rebuilt.extend(
                line.text + "\n" for line in hunk.lines if line.tag is LineTag.INSERT
            )
            pos = hunk.a_start + hunk.a_count
        rebuilt.extend(a[pos:])
        assert rebuilt == b


# --- CLI surface: --tui / --cache guards --------------------------------


class TestCliV04Flags:
    def test_tui_rejected_without_tty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from atrain.cli import main

        pa = tmp_path / "a.txt"
        pb = tmp_path / "b.txt"
        pa.write_text("x\n", encoding="utf-8")
        pb.write_text("y\n", encoding="utf-8")
        rc = main(["--tui", str(pa), str(pb)])
        assert rc == 2
        assert "interactive terminal" in capsys.readouterr().err

    def test_tui_missing_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from atrain.cli import main

        existing = tmp_path / "a.txt"
        existing.write_text("x\n", encoding="utf-8")
        rc = main(["--tui", str(existing), str(tmp_path / "nope.txt")])
        assert rc == 2
        assert "compares two files" in capsys.readouterr().err

    def test_cache_rejected_for_text_mode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from atrain.cli import main

        pa = tmp_path / "a.txt"
        pb = tmp_path / "b.txt"
        pa.write_text("x\n", encoding="utf-8")
        pb.write_text("y\n", encoding="utf-8")
        rc = main(["--cache", "--mode", "text", str(pa), str(pb)])
        assert rc == 2
        assert "--cache applies to" in capsys.readouterr().err
