"""Tests for the watch mode feature (atrain.core.watch)."""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import pytest

from atrain.core.diff_text import TextOptions
from atrain.core.watch import WatchConfig, WatchMode, _FileState, watch


# ── helpers ──────────────────────────────────────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


# ── _FileState unit tests ────────────────────────────────────────────────────


class TestFileState:
    def test_from_path(self, tmp_path: Path) -> None:
        p = tmp_path / "f.txt"
        _write(p, "hello")
        st = _FileState.from_path(p)
        assert st.size == 5
        assert st.mtime > 0

    def test_changed_returns_false_when_unchanged(self, tmp_path: Path) -> None:
        p = tmp_path / "f.txt"
        _write(p, "hello")
        st = _FileState.from_path(p)
        assert st.changed(p) is False

    def test_changed_returns_true_when_content_modified(self, tmp_path: Path) -> None:
        p = tmp_path / "f.txt"
        _write(p, "hello")
        st = _FileState.from_path(p)
        time.sleep(0.05)
        _write(p, "world")
        assert st.changed(p) is True

    def test_changed_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        p = tmp_path / "f.txt"
        _write(p, "hello")
        st = _FileState.from_path(p)
        p.unlink()
        # Missing file should not raise, just return False.
        assert st.changed(p) is False


# ── WatchMode enum ───────────────────────────────────────────────────────────


class TestWatchMode:
    def test_values(self) -> None:
        assert WatchMode.BOTH.value == "both"
        assert WatchMode.SOURCE.value == "source"
        assert WatchMode.TARGET.value == "target"


# ── WatchConfig defaults ────────────────────────────────────────────────────


class TestWatchConfig:
    def test_defaults(self, tmp_path: Path) -> None:
        cfg = WatchConfig(source=tmp_path / "a", target=tmp_path / "b")
        assert cfg.mode is WatchMode.BOTH
        assert cfg.interval == 0.5
        assert cfg.text_options is None
        assert cfg.on_alert is None


# ── watch() integration tests ────────────────────────────────────────────────


class TestWatch:
    def test_missing_source_returns_2(self, tmp_path: Path) -> None:
        src = tmp_path / "nope.txt"
        tgt = tmp_path / "b.txt"
        _write(tgt, "hello")
        cfg = WatchConfig(source=src, target=tgt, interval=0.05)
        assert watch(cfg) == 2

    def test_missing_target_returns_2(self, tmp_path: Path) -> None:
        src = tmp_path / "a.txt"
        tgt = tmp_path / "nope.txt"
        _write(src, "hello")
        cfg = WatchConfig(source=src, target=tgt, interval=0.05)
        assert watch(cfg) == 2

    def test_identical_files_no_alert(self, tmp_path: Path) -> None:
        """When files are identical and nothing changes, no alert fires."""
        src = tmp_path / "a.txt"
        tgt = tmp_path / "b.txt"
        _write(src, "same content")
        _write(tgt, "same content")

        alerts: list[tuple[str, int]] = []

        def capture(label: str, result) -> None:  # type: ignore[no-untyped-def]
            alerts.append((label, result.stats.added + result.stats.removed))

        cfg = WatchConfig(
            source=src,
            target=tgt,
            mode=WatchMode.BOTH,
            interval=0.05,
            on_alert=capture,
        )

        # Run watch in a thread and stop after a short time.
        done: list[int] = []

        def run() -> None:
            done.append(watch(cfg))

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.3)
        # No changes should have been made, so no alerts.
        assert len(alerts) == 0

    def test_both_mode_alerts_on_source_change(self, tmp_path: Path) -> None:
        src = tmp_path / "a.txt"
        tgt = tmp_path / "b.txt"
        _write(src, "line1\n")
        _write(tgt, "line1\n")

        alerts: list[str] = []

        def capture(label: str, result) -> None:  # type: ignore[no-untyped-def]
            alerts.append(label)

        cfg = WatchConfig(
            source=src,
            target=tgt,
            mode=WatchMode.BOTH,
            interval=0.05,
            on_alert=capture,
        )

        def run() -> None:
            watch(cfg)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.15)
        _write(src, "line1\nchanged!\n")
        time.sleep(0.3)
        assert "both" in alerts

    def test_both_mode_alerts_on_target_change(self, tmp_path: Path) -> None:
        src = tmp_path / "a.txt"
        tgt = tmp_path / "b.txt"
        _write(src, "line1\n")
        _write(tgt, "line1\n")

        alerts: list[str] = []

        def capture(label: str, result) -> None:  # type: ignore[no-untyped-def]
            alerts.append(label)

        cfg = WatchConfig(
            source=src,
            target=tgt,
            mode=WatchMode.BOTH,
            interval=0.05,
            on_alert=capture,
        )

        def run() -> None:
            watch(cfg)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.15)
        _write(tgt, "line1\nnew line\n")
        time.sleep(0.3)
        assert "both" in alerts

    def test_source_mode_alerts_only_on_source_change(self, tmp_path: Path) -> None:
        src = tmp_path / "a.txt"
        tgt = tmp_path / "b.txt"
        _write(src, "line1\n")
        _write(tgt, "line1\n")

        alerts: list[str] = []

        def capture(label: str, result) -> None:  # type: ignore[no-untyped-def]
            alerts.append(label)

        cfg = WatchConfig(
            source=src,
            target=tgt,
            mode=WatchMode.SOURCE,
            interval=0.05,
            on_alert=capture,
        )

        def run() -> None:
            watch(cfg)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.15)
        # Changing target should NOT trigger an alert in SOURCE mode.
        _write(tgt, "line1\nnew line\n")
        time.sleep(0.3)
        assert len(alerts) == 0

        # Changing source SHOULD trigger an alert.
        _write(src, "line1\nsource changed\n")
        time.sleep(0.3)
        assert "source" in alerts

    def test_target_mode_alerts_only_on_target_change(self, tmp_path: Path) -> None:
        src = tmp_path / "a.txt"
        tgt = tmp_path / "b.txt"
        _write(src, "line1\n")
        _write(tgt, "line1\n")

        alerts: list[str] = []

        def capture(label: str, result) -> None:  # type: ignore[no-untyped-def]
            alerts.append(label)

        cfg = WatchConfig(
            source=src,
            target=tgt,
            mode=WatchMode.TARGET,
            interval=0.05,
            on_alert=capture,
        )

        def run() -> None:
            watch(cfg)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.15)
        # Changing source should NOT trigger an alert in TARGET mode.
        _write(src, "line1\nsource changed\n")
        time.sleep(0.3)
        assert len(alerts) == 0

        # Changing target SHOULD trigger an alert.
        _write(tgt, "line1\ntarget changed\n")
        time.sleep(0.3)
        assert "target" in alerts

    def test_initial_diff_printed_when_files_differ(self, tmp_path: Path) -> None:
        """The initial diff should be printed immediately when files differ."""
        src = tmp_path / "a.txt"
        tgt = tmp_path / "b.txt"
        _write(src, "aaa\n")
        _write(tgt, "bbb\n")

        alerts: list[str] = []

        def capture(label: str, result) -> None:  # type: ignore[no-untyped-def]
            alerts.append(label)

        cfg = WatchConfig(
            source=src,
            target=tgt,
            mode=WatchMode.BOTH,
            interval=0.05,
            on_alert=capture,
        )

        def run() -> None:
            watch(cfg)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.2)
        # The initial diff should have been printed already.
        assert len(alerts) >= 1
        assert alerts[0] == "both"

    def test_content_unchanged_touch_does_not_alert(self, tmp_path: Path) -> None:
        """A stat-only change (same content) should not trigger an alert."""
        src = tmp_path / "a.txt"
        tgt = tmp_path / "b.txt"
        _write(src, "same\n")
        _write(tgt, "same\n")

        alerts: list[str] = []

        def capture(label: str, result) -> None:  # type: ignore[no-untyped-def]
            alerts.append(label)

        cfg = WatchConfig(
            source=src,
            target=tgt,
            mode=WatchMode.BOTH,
            interval=0.05,
            on_alert=capture,
        )

        def run() -> None:
            watch(cfg)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.15)
        # Re-write the same content (mtime changes, content doesn't).
        _write(src, "same\n")
        _write(tgt, "same\n")
        time.sleep(0.3)
        # No alerts should fire because content is identical.
        assert len(alerts) == 0