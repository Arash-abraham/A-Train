# 16_performance — Performance laboratories

## What / Why

Diagnostic scripts and profiler captures backing the performance claims
and improvement discussions in `benchmarks/RESULTS.md` and
`IMPROVEMENT_SUGGESTIONS.md`. Nothing here is part of the official test
suite (`tests/`); these are repeatable measurement tools.

## Contents

| File | Purpose |
|---|---|
| `profile_100mb_phases.py` | Phase-by-phase timing (I/O+digest, decode+split, interning, Myers, hunks) of a large small-change comparison — evidence for why `small_change_100mb` misses the <1 s target. `python3 test/16_performance/profile_100mb_phases.py [--mb 100]` |
| `pyspy_smallchange_30mb.txt` | Raw py-spy sampling output (`--format raw --rate 200`) of a 30 MB CLI comparison (2026-09-18). Motivated the v0.4 micro-optimisations: interning 21%, digest 20%, split 18%, newline classification 12%. |

## Expected results

- The profiler prints per-phase seconds and always exactly **1 hunk**
  for its single-changed-line corpus (a bug where the generator produced
  a second, spurious tail difference is documented in the script header
  and DEVELOPMENT_REPORT §v0.3.4 / §v0.4.2).
- The py-spy capture is a frozen artefact — regenerate with:
  `py-spy record --format raw --rate 200 -- python3 -m atrain A B`

## Failure meaning

- Profiler totals far above ~4 s for 100 MB → machine or regression
  issue; cross-check `benchmarks/RESULTS.md` environment.
- More than one hunk in the profiler output → corpus generator or engine
  regression; compare against the §v0.4.2 notes.
