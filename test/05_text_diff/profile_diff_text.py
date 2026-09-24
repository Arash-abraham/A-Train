#!/usr/bin/env python3
"""Profile the Myers text engine on synthetic inputs.

Purpose:
    Find the hot spots of `atrain.core.diff_text` under realistic shapes:
    identical inputs (early exit), a small change in a large file, and a
    large replacement.
How to run:
    python3 test/05_text_diff/profile_diff_text.py [lines]
Expected result:
    Timing + cProfile top-15 per scenario; no assertion failures. Figures
    feed benchmarks/RESULTS.md context but the formal benchmark lives in
    benchmarks/.
"""

from __future__ import annotations

import cProfile
import io
import pstats
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402 — direct script execution

from atrain.core.diff_text import diff_lines  # noqa: E402


def _profile(name: str, a: list[str], b: list[str]) -> None:
    start = time.perf_counter()
    hunks = diff_lines(a, b)
    elapsed = time.perf_counter() - start
    print(f"[{name}] lines={len(a)}/{len(b)} hunks={len(hunks)} time={elapsed:.3f}s")

    profiler = cProfile.Profile()
    profiler.enable()
    diff_lines(a, b)
    profiler.disable()
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
    stats.print_stats(15)
    print(stream.getvalue())


def main() -> int:
    lines = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000
    rng = random.Random(7)
    base = [f"line {i}: {rng.random()}" for i in range(lines)]

    identical = list(base)
    _profile("identical", base, identical)

    small_change = list(base)
    small_change[lines // 2] = "CHANGED"
    _profile("small-change", base, small_change)

    large_change = ["NEW " + line for line in base[lines // 3 :]]
    _profile("large-replacement", base, large_change)
    return 0


if __name__ == "__main__":
    sys.exit(main())
