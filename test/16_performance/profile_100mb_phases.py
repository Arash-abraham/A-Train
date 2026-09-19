#!/usr/bin/env python3
"""Phase breakdown of a 100 MB small-change comparison.

Purpose:
    The roadmap targets "two 100 MB text files in under one second". The
    benchmark shows identical_100mb at 0.34 s (target met) but
    small_change_100mb at ~3.6 s. This script measures each engine phase
    separately so the RESULTS.md discussion can cite evidence instead of
    guesses.
How to run:
    python3 test/16_performance/profile_100mb_phases.py [--mb 100]
Expected result:
    Per-phase timings (I/O+digest, decode, split, intern, myers, hunks).
    No pass/fail — diagnostic only.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402

from atrain.core.diff_text import (  # noqa: E402
    build_hunks,
)
from atrain.core.hasher import digest_bytes  # noqa: E402
from atrain.core.reader import load_bytes, load_text  # noqa: E402

_LINE = "The quick brown fox jumps over the lazy developer. Line {i}.\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mb", type=int, default=100)
    args = parser.parse_args()
    target = args.mb << 20

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        pa, pb = tmp / "a.txt", tmp / "b.txt"
        # Build the line list once, then mutate a copy — so the two files
        # differ in exactly ONE line (a buggy earlier version let the
        # shorter replacement shift the loop's byte accounting and add a
        # second, spurious difference at the tail).
        lines: list[str] = []
        written = 0
        index = 0
        while written < target:
            line = _LINE.format(i=index)
            lines.append(line)
            written += len(line)
            index += 1
        b_lines = list(lines)
        b_lines[len(b_lines) // 2] = "CHANGED\n"
        pa.write_text("".join(lines), encoding="utf-8")
        pb.write_text("".join(b_lines), encoding="utf-8")
        size = pa.stat().st_size

        start = time.perf_counter()
        with load_bytes(pa) as ra, load_bytes(pb) as rb:
            digest_bytes(ra.data)
            digest_bytes(rb.data)
        io_digest = time.perf_counter() - start

        start = time.perf_counter()
        lines_a, _ = load_text(pa)
        lines_b, _ = load_text(pb)
        decode_split = time.perf_counter() - start

        start = time.perf_counter()
        from atrain.core.diff_text import intern_line_pairs, myers_opcodes

        ids_a, ids_b = intern_line_pairs(lines_a, lines_b)
        intern_t = time.perf_counter() - start

        start = time.perf_counter()
        ops = myers_opcodes(ids_a, ids_b)
        myers_t = time.perf_counter() - start

        start = time.perf_counter()
        hunks = build_hunks(ops, lines_a, lines_b, context=3)
        hunks_t = time.perf_counter() - start

        total = io_digest + decode_split + intern_t + myers_t + hunks_t
        print(f"input: {size / (1 << 20):.1f} MiB, {len(lines_a):,} lines, 1 changed line")
        print(f"  I/O + BLAKE2b digest : {io_digest:6.3f} s")
        print(f"  decode + split lines : {decode_split:6.3f} s")
        print(f"  line interning       : {intern_t:6.3f} s")
        print(f"  Myers search         : {myers_t:6.3f} s")
        print(f"  hunk building        : {hunks_t:6.3f} s  ({len(hunks)} hunk(s))")
        print(f"  total (sequential)   : {total:6.3f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
