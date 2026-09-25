"""Watch Mode: real-time file change detection and alerting.

Monitors two files simultaneously and raises alerts when changes are
detected, based on the selected watch mode:

- **both**: Alert when *either* file changes relative to the other.
- **source**: Alert when the *source* (first) file changes relative to target.
- **target**: Alert when the *target* (second) file changes relative to source.

Uses lightweight polling via ``os.stat`` (size + mtime) so no extra
dependencies are required.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from atrain.core import diff_text
from atrain.core.diff_text import TextOptions
from atrain.core.models import DiffResult


class WatchMode(Enum):
    """Which direction(s) to monitor for changes."""

    BOTH = "both"
    """Alert when either file changes relative to the other."""

    SOURCE = "source"
    """Alert when the source (first) file changes relative to target."""

    TARGET = "target"
    """Alert when the target (second) file changes relative to source."""


@dataclass(slots=True)
class _FileState:
    """Cached ``stat`` snapshot for one file."""

    size: int
    mtime: float

    @classmethod
    def from_path(cls, path: Path) -> _FileState:
        st = path.stat()
        return cls(size=st.st_size, mtime=st.st_mtime)

    def changed(self, path: Path) -> bool:
        """Return ``True`` if *path* has been modified since last snapshot."""
        try:
            st = path.stat()
        except OSError:
            return False
        return st.st_size != self.size or st.st_mtime != self.mtime


@dataclass(slots=True)
class WatchConfig:
    """Configuration for a watch session.

    Attributes:
        source: Path to the first (source) file.
        target: Path to the second (target) file.
        mode: Which direction(s) to monitor.
        interval: Polling interval in seconds (default 0.5).
        text_options: Options forwarded to the text diff engine.
        on_alert: Callback invoked with ``(mode_label, DiffResult)`` on
            every detected change.  If ``None``, a default printer is used.
    """

    source: Path
    target: Path
    mode: WatchMode = WatchMode.BOTH
    interval: float = 0.5
    text_options: TextOptions | None = None
    on_alert: Callable[[str, DiffResult], None] | None = None


def _default_alert(label: str, result: DiffResult) -> None:
    """Print a coloured alert banner to stderr, then the diff to stdout."""
    RED = "\x1b[31m"
    YELLOW = "\x1b[33m"
    BOLD = "\x1b[1m"
    RESET = "\x1b[0m"

    ts = time.strftime("%H:%M:%S")
    src_stats = f"+{result.stats.added} -{result.stats.removed}"
    side = {"source": "SOURCE", "target": "TARGET", "both": "BOTH"}.get(label, label.upper())
    colour = RED if side == "BOTH" else YELLOW
    header = (
        f"{colour}{BOLD}"
        f"[{ts}] WATCH [{side}] — change detected "
        f"({src_stats}, {result.stats.hunks} hunk(s))"
        f"{RESET}"
    )
    print(header, file=sys.stderr, flush=True)

    from atrain.output import unified

    diff_text_out = unified.render(result, str(result.source.path), str(result.target.path))
    if diff_text_out:
        sys.stdout.write(diff_text_out)
        sys.stdout.flush()


def _diff(cfg: WatchConfig) -> DiffResult:
    """Run a full text comparison between source and target."""
    return diff_text.compare_files(cfg.source, cfg.target, cfg.text_options)


# ── public API ──────────────────────────────────────────────────────────────


def watch(cfg: WatchConfig) -> int:
    """Start a watch session; runs until interrupted (KeyboardInterrupt).

    Returns:
        ``0`` on clean exit, ``2`` on error (missing file, etc.).

    The function polls both files at ``cfg.interval`` seconds.  Depending on
    ``cfg.mode`` it decides which side's change triggers an alert:

    * ``BOTH`` — either file changed ⇒ alert.
    * ``SOURCE`` — only source file changed ⇒ alert.
    * ``TARGET`` — only target file changed ⇒ alert.

    An initial diff is always printed so the user knows the starting state.
    """
    for label, path in (("source", cfg.source), ("target", cfg.target)):
        if not path.is_file():
            print(f"atrain: watch: {label}: {path}: No such file", file=sys.stderr)
            return 2

    alert = cfg.on_alert or _default_alert

    # Initial state snapshot.
    try:
        state_src = _FileState.from_path(cfg.source)
        state_tgt = _FileState.from_path(cfg.target)
    except OSError as exc:
        print(f"atrain: watch: {exc}", file=sys.stderr)
        return 2

    # Show the initial diff once so the user has a baseline.
    initial = _diff(cfg)
    if not initial.identical:
        alert(cfg.mode.value, initial)
    else:
        ts = time.strftime("%H:%M:%S")
        print(f"\x1b[2m[{ts}] WATCH — files are identical\x1b[0m", file=sys.stderr, flush=True)

    # Polling loop.
    try:
        while True:
            time.sleep(cfg.interval)

            src_changed = state_src.changed(cfg.source)
            tgt_changed = state_tgt.changed(cfg.target)

            # Always refresh snapshots so we don't re-trigger on the same write.
            state_src = _FileState.from_path(cfg.source)
            state_tgt = _FileState.from_path(cfg.target)

            should_alert = False
            label = cfg.mode.value

            if cfg.mode is WatchMode.BOTH:
                if src_changed or tgt_changed:
                    should_alert = True
                    label = "both"
            elif cfg.mode is WatchMode.SOURCE:
                if src_changed:
                    should_alert = True
                    label = "source"
            elif cfg.mode is WatchMode.TARGET:
                if tgt_changed:
                    should_alert = True
                    label = "target"

            if not should_alert:
                continue

            result = _diff(cfg)
            if result.identical:
                # A stat change that didn't alter content (e.g. touch).
                continue

            alert(label, result)

    except KeyboardInterrupt:
        print("\n\x1b[2m[watch stopped]\x1b[0m", file=sys.stderr, flush=True)
        return 0