#!/usr/bin/env python3
"""Formal benchmark harness: A-Train vs difflib vs GNU diff.

Purpose:
    Repeatable performance measurements on generated corpora (ROADMAP §3.8,
    §8 v0.3).  Results are printed as a Markdown table; they are transcribed
    — with environment facts — into benchmarks/RESULTS.md.  No number is
    ever published without a real run of this script.

Methodology:
    - Deterministic, seeded corpora generated into a temporary directory.
    - Each competitor is warmed once (OS page cache), then timed over 3
      runs; the minimum is reported (standard practice, documented).
    - ``difflib`` participates only in scenarios up to 5 MiB: its worst-case
      quadratic behaviour makes larger runs unbounded (noted per-scenario).
    - A-Train figures measure the *engine* (compare_files, in-process,
      rendering excluded) plus, for one spot-check scenario, the full CLI
      (subprocess, includes interpreter startup ~50 ms).

How to run:
    python3 benchmarks/run_benchmarks.py [--quick] [--keep]
Expected result:
    A Markdown results table; exit 0.  --quick shrinks corpus sizes for
    development iteration.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402 — direct script execution

from atrain.core.diff_text import TextOptions, compare_files  # noqa: E402

RUNS = 3
GNU_TIMEOUT = 120
DIFLIB_TIMEOUT = 60  # per timed run; difflib is quadratic on adversarial input
DIFLIB_MAX_BYTES = 6 << 20  # difflib is capped at ~6 MiB inputs
MB = 1 << 20


class _RunTimeout(Exception):
    pass


def _alarm_handler(signum: int, frame: object) -> None:
    raise _RunTimeout


def _with_timeout(seconds: int, fn: Callable[[], float]) -> float:
    """Run *fn* under SIGALRM; raise :class:`_RunTimeout` when it expires."""
    old = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)

_LINE = "The quick brown fox jumps over the lazy developer. Line {i} of {{total}}.\n"


def _corpus_line(i: int) -> str:
    return _LINE.format(i=i)


def _make(path: Path, total_bytes: int, mutate=None) -> None:
    """Write a text file of ~total_bytes; mutate(line, index) rewrites lines.

    Mutation happens *after* the byte accounting: a shorter replacement
    must not shift the loop's target, or the two files would diverge at
    the tail as well (a bug an earlier revision had — it made the
    "small change" scenarios contain a second, spurious difference).
    """
    lines: list[str] = []
    written = 0
    index = 0
    while written < total_bytes:
        lines.append(_corpus_line(index))
        written += len(lines[-1])
        index += 1
    if mutate is not None:
        lines = [mutate(line, i) for i, line in enumerate(lines)]
    path.write_text("".join(lines), encoding="utf-8")


def _scenarios(quick: bool) -> list[dict]:
    scale = 4 if quick else 1
    mb = lambda n: max(64_000, n // scale)  # noqa: E731
    return [
        {"name": "identical_5mb", "size": mb(5 * MB)},
        {"name": "identical_20mb", "size": mb(20 * MB), "difflib": False},
        {"name": "small_change_5mb", "size": mb(5 * MB),
         "mutate": lambda line, i: "CHANGED\n" if i == 1000 else line},
        {"name": "small_change_20mb", "size": mb(20 * MB),
         "mutate": lambda line, i: "CHANGED\n" if i == 5000 else line,
         "difflib": False, "cli_spot_check": True},
        {"name": "scattered_5mb", "size": mb(5 * MB),
         "mutate": lambda line, i: line.replace("fox", "wolf") if i % 100 == 0 else line},
        {"name": "alternating_5mb", "size": mb(5 * MB),
         "mutate": lambda line, i: ("NEW " + line) if i % 2 == 0 else line},
        {"name": "identical_100mb", "size": mb(100 * MB), "difflib": False,
         "only": ["atrain", "gnu"]},
        {"name": "small_change_100mb", "size": mb(100 * MB),
         "mutate": lambda line, i: "CHANGED\n" if i == 100_000 else line,
         "difflib": False, "only": ["atrain", "gnu"]},
        {"name": "worst_case_disjoint", "lines": 2_000, "only": ["atrain", "difflib", "gnu"]},
    ]


def _gen_worst_case(tmp: Path, lines: int) -> tuple[Path, Path]:
    a = tmp / "wc_a.txt"
    b = tmp / "wc_b.txt"
    with open(a, "w", encoding="utf-8") as fa, open(b, "w", encoding="utf-8") as fb:
        for i in range(lines):
            fa.write(f"alpha-{i:05d}-{'x' * (i % 40)}\n")
            fb.write(f"beta-{i:05d}-{'y' * (i % 40)}\n")
    return a, b


def _time(fn, runs: int = RUNS) -> float:
    fn()  # warm-up (page cache, imports)
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def _run_atrain_engine(pa: Path, pb: Path) -> float:
    return _time(lambda: compare_files(pa, pb, TextOptions(context=3)))


def _run_atrain_cli(pa: Path, pb: Path) -> float:
    def once() -> None:
        subprocess.run(
            [sys.executable, "-m", "atrain", str(pa), str(pb)],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            check=False,
        )

    return _time(once)


def _run_difflib(pa: Path, pb: Path) -> float:
    import difflib

    a_lines = pa.read_text(encoding="utf-8").splitlines(keepends=True)
    b_lines = pb.read_text(encoding="utf-8").splitlines(keepends=True)

    def once() -> None:
        diff = difflib.unified_diff(a_lines, b_lines, lineterm="\n")
        for _ in diff:
            pass

    def timed() -> float:
        return _with_timeout(DIFLIB_TIMEOUT, lambda: _time(once, runs=RUNS))

    try:
        return timed()
    except _RunTimeout:
        raise TimeoutError("difflib exceeded its budget") from None


def _run_gnu(pa: Path, pb: Path) -> float:
    def once() -> None:
        subprocess.run(
            ["diff", "-u", str(pa), str(pb)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=GNU_TIMEOUT,
        )

    return _time(once)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    tool_impl = {
        "atrain": _run_atrain_engine,
        "difflib": _run_difflib,
        "gnu": _run_gnu,
    }

    print("| scenario | input | atrain (s) | difflib (s) | GNU diff (s) |")
    print("|---|---|---|---|---|")

    with tempfile.TemporaryDirectory(prefix="atrain-bench-") as tmp_str:
        tmp = Path(tmp_str)
        for spec in _scenarios(args.quick):
            name = spec["name"]
            if "lines" in spec:
                pa, pb = _gen_worst_case(tmp, spec["lines"])
                size_label = f"{spec['lines']} disjoint lines"
            else:
                pa = tmp / f"{name}_a.txt"
                pb = tmp / f"{name}_b.txt"
                _make(pa, spec["size"])
                _make(pb, spec["size"], mutate=spec.get("mutate"))
                size_label = (
                    f"~{spec['size'] // MB} MiB"
                    if spec["size"] >= MB
                    else f"{spec['size'] >> 10} KiB"
                )

            allowed = spec.get("only", ["atrain", "difflib", "gnu"])
            timings: dict[str, str] = {}
            for tool in ("atrain", "difflib", "gnu"):
                if tool not in allowed or (tool == "difflib" and spec.get("difflib") is False):
                    timings[tool] = "—"
                    continue
                if tool == "difflib" and pa.stat().st_size > DIFLIB_MAX_BYTES:
                    timings[tool] = "capped"
                    continue
                try:
                    seconds = tool_impl[tool](pa, pb)
                    timings[tool] = f"{seconds:.3f}"
                except TimeoutError:
                    budget = DIFLIB_TIMEOUT if tool == "difflib" else GNU_TIMEOUT
                    timings[tool] = f"timeout({budget}s)"

            if spec.get("cli_spot_check"):
                timings["atrain_cli"] = f"{_run_atrain_cli(pa, pb):.3f}"
            else:
                timings["atrain_cli"] = ""

            cli_note = f" (CLI e2e: {timings['atrain_cli']} s)" if timings["atrain_cli"] else ""
            print(
                f"| {name} | {size_label} | {timings['atrain']}{cli_note} "
                f"| {timings['difflib']} | {timings['gnu']} |"
            )
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
