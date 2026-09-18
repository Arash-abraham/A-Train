# Test Report

Log of formal test runs (prompt §19). One entry per validation pass.
Environment facts come from `test/00_environment/check_env.py`.

---

## Test Run — v0.1 Core (final validation)

- **Date:** 2026-09-18
- **Phase:** v0.1 — Core
- **Command:** `python3 -m pytest tests/ -q`
- **Environment:** Python 3.11.2, Linux 6.1.158+ (x86_64), 2 CPUs,
  pytest 9.1.1, hypothesis 6.168.0, GNU diffutils 3.8, GNU patch;
  ruff 0.16.8, mypy 2.3.1
- **Result:** see the "v0.1 final validation" entry below (updated after
  lint/type checks); intermediate runs during development are recorded
  in the history section.

### History (development-time runs, chronological)

| # | Run | Result | Notes |
|---|---|---|---|
| 1 | CLI smoke: two differing files | FAIL — empty output, crash | `FrozenInstanceError` in `load_text` (bug #1, DEVELOPMENT_REPORT §3) |
| 2 | CLI smoke after fix #1 | FAIL — differing files reported identical | separate interning tables per file (bug #2) |
| 3 | CLI smoke after fix #2 | FAIL — exit code 0 on differences | `_compare_text` returned `_emit` status (bug #3) |
| 4 | CLI smoke | PASS — output byte-identical semantics to GNU | exit codes 0/1/2 verified |
| 5 | `pytest tests/ -q` (first full) | 11 failed / 108 passed | mmap `BufferError` (bug #4), newline classification (bug #5), applier marker (bug #6), reference-metric modelling (bug #7), empty-script contract |
| 6 | `pytest tests/ -q` | **119 passed / 0 failed** | after fixes; 700 hypothesis property cases included |

### Failure notes

- Every failure above has a root cause and regression test listed in
  DEVELOPMENT_REPORT.md §3. No environment issues were encountered.
- Two exploratory scripts (`verify_structure.py`, `profile_diff_text.py`)
  had path/import defects on first run; fixed and re-run (they are not
  part of the pytest suite).
