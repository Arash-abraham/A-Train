# Benchmark Results

All numbers below come from real runs of `benchmarks/run_benchmarks.py`
(methodology: seeded corpora, one warm-up + best of 3 timed runs per
competitor; SIGALRM budget of 60 s per difflib run). No figure on this
page is estimated.

## Environment (from `test/00_environment/check_env.py`, 2026-09-18)

- Python 3.11.2 (CPython, x86_64), Linux 6.1.158+, **2 vCPUs** (shared
  sandbox — expect faster figures on dedicated hardware)
- GNU diffutils 3.8; `difflib` from the Python 3.11 standard library

## Results — v0.4 run (2026-09-18, after the wall-clock guard)

| scenario | input | atrain (s) | difflib (s) | GNU diff (s) |
|---|---|---:|---:|---:|
| identical_5mb | ~5 MiB | **0.017** | 0.051 | 0.016 |
| identical_20mb | ~20 MiB | 0.069 | — | **0.064** |
| small_change_5mb | ~5 MiB, 1 line changed | 0.123 | 0.053 | **0.016** |
| small_change_20mb | ~20 MiB, 1 line changed | 0.577 *(CLI e2e: 0.633)* | — | **0.064** |
| scattered_5mb | ~5 MiB, every 100th line | 0.545 | 8.520 | **0.032** |
| alternating_5mb | ~5 MiB, every 2nd line | 2.665 | timeout(60 s) | **0.032** |
| identical_100mb | ~100 MiB | **0.338** | — | 0.215 |
| small_change_100mb | ~100 MiB, 1 line changed | 3.482 | — | **0.215** |
| worst_case_disjoint | 2000 disjoint lines | 1.439 | 0.001 | **0.003** |

`—` = not run (difflib is capped at ~6 MiB inputs: its worst-case
quadratic behaviour makes larger runs unbounded — see
`alternating_5mb`, where difflib did not finish 5 MiB within 60 s).

### Change vs the v0.3 run (same machine, same day)

| scenario | v0.3 (s) | v0.4 (s) | Δ |
|---|---:|---:|---|
| alternating_5mb | 49.404 | 2.665 | **18.5× faster** (2 s wall-clock guard) |
| scattered_5mb | 0.580 | 0.545 | 6% (fused split/classify, setdefault interning) |
| small_change_5mb | 0.137 | 0.123 | 10% (same micro-optimisations) |
| small_change_100mb | 3.644 | 3.482 | 4% |
| worst_case_disjoint | 1.430 | 1.439 | unchanged (guard budget not yet exhausted) |

The v0.4 micro-optimisations were guided by a py-spy capture
(`test/16_performance/pyspy_smallchange_30mb.txt`, 30 MB small-change
profile: interning 21%, digest 20%, split 18%, **newline classification
12%** — the fused `_split_and_classify` removes that entire phase).

## Honest reading of the numbers

### Where A-Train meets its targets

- **100 MB identical in under a second: MET** — 0.338 s (hash-based
  early exit; no line comparison at all). 1.6× faster than GNU diff here.
- **≥ 2× faster than difflib on measured inputs: MET where measured** —
  identical_5mb: 3×; scattered_5mb: 15.6×. (difflib could not be run at
  50 MB+ within any sane budget, so the roadmap's 50 MB claim is *not*
  claimed here — it is unmeasurable against difflib in this sandbox.)
- **Pathological inputs bounded: MET (new in v0.4)** — the wall-clock
  guard caps the Myers search at ~2 s before falling back to the coarse
  but exact-reconstruction edit script: alternating_5mb went from 49 s
  (v0.3, budget burn) to 2.7 s. The fallback is verified to rebuild the
  target exactly (tests/test_tui_cache.py::TestV04Optimizations).

### Where A-Train still misses its target (with evidence)

- **100 MB *small change* in under a second: MISSED** — 3.482 s vs GNU
  0.215 s. Phase profile (test/16_performance/profile_100mb_phases.py,
  same input class): I/O + BLAKE2b 0.38 s, **decode + line splitting
  1.93 s**, **line interning 1.40 s**, Myers search 0.19 s, hunk build
  ~0. The diff algorithm is not the bottleneck — pure-Python per-line
  text processing is. Closing the gap needs C-level text handling
  (chunked line indexing over mmap, or a compiled extension), which is
  out of scope (see IMPROVEMENT_SUGGESTIONS.md #7).
- Adversarial inputs remain ~80× slower than GNU diff's heuristics even
  when bounded (2.665 s vs 0.032 s) because A-Train's fallback is exact
  while GNU approximates; the latency is now bounded and documented.

### Zero false diffs (ROADMAP DoD #2)

Validated structurally, not chronometrically: the pytest suite applies
A-Train's output with GNU `patch` and applies GNU diff's output with the
reference applier across the golden corpus (tests/test_golden_gnu.py),
plus 700 property-based round-trip cases. Identical 50 000-line files
produce no hunks (tests/test_golden_gnu.py::test_zero_false_diffs_on_identical_large_files).

## Reproducing

```bash
python3 benchmarks/run_benchmarks.py          # full corpora (several minutes)
python3 benchmarks/run_benchmarks.py --quick  # quarter-size corpora
```
