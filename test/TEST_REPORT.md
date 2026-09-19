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

---

## Test Run — v0.2 Presentation (final validation)

- **Date:** 2026-09-18
- **Phase:** v0.2 — Presentation
- **Command:** `python3 -m pytest tests/ -q` · `python3 -m ruff check .` · `python3 -m mypy`
- **Environment:** Python 3.11.2, Linux 6.1.158+ (x86_64), 2 CPUs,
  pytest 9.1.1, hypothesis 6.168.0, ruff 0.16.8, mypy 2.3.1,
  GNU diffutils 3.8, GNU patch
- **Result:** 171 passed / 0 failed; ruff clean; mypy --strict clean
  (14 source files)

### History (development-time runs, chronological)

| # | Run | Result | Notes |
|---|---|---|---|
| 1 | `pytest` after new v0.2 suites | 10 failed / 161 passed | 5 test-authoring errors (wrong expected splits/marks/tags), UTF-16-BOM binary misclassification (bug #1), UTF-8-on-NUL mojibake (bug #2), side width overflow (bug #3) — see DEVELOPMENT_REPORT §v0.2.2 |
| 2 | `pytest` after fixes | 171 passed / 0 failed | |
| 3 | `ruff check .` | 13 findings (E501/E741) | fixed; clean |
| 4 | `mypy` (strict) | clean, 14 files | |


---

## Test Run — v0.3 Advanced Modes (final validation)

- **Date:** 2026-09-18
- **Phase:** v0.3 — binary / json / csv / dir modes, benchmarks
- **Command:** `python3 -m pytest tests/ -q` · `python3 -m ruff check .` ·
  `python3 -m mypy` · `python3 benchmarks/run_benchmarks.py`
- **Environment:** Python 3.11.2, Linux 6.1.158+ (x86_64), 2 vCPUs,
  pytest 9.1.1, hypothesis 6.168.0, ruff 0.16.8, mypy 2.3.1,
  GNU diffutils 3.8, GNU patch
- **Result:** 223 passed / 0 failed; ruff clean; mypy --strict clean
  (18 source files); full benchmark run completed (benchmarks/RESULTS.md)

### History (development-time runs, chronological)

| # | Run | Result | Notes |
|---|---|---|---|
| 1 | `pytest` with new v0.3 suites | 13 failed / 210 passed | 2 real engine bugs in `diff_binary` (suffix scan direction; resync needle corruption) + test-authoring errors — all listed in DEVELOPMENT_REPORT §v0.3.3 |
| 2 | `pytest` after fixes | 223 passed / 0 failed | |
| 3 | `benchmarks/run_benchmarks.py` (full) | completed in ~6 min | first full run had hit the 25-min tooling timeout: difflib ran unbounded on `alternating_5mb`; SIGALRM budget added, then rerun completed |
| 4 | `ruff` / `mypy` | clean | |


---

## Test Run — v0.4 Interactive UI and Optimization (final validation)

- **Date:** 2026-09-18
- **Phase:** v0.4 — TUI, digest cache, wall-clock guard, micro-optimisations, README
- **Command:** `python3 -m pytest tests/ -q` · `python3 -m ruff check .` ·
  `python3 -m mypy` · `python3 benchmarks/run_benchmarks.py` ·
  `py-spy record --format raw` (30 MB profile) ·
  `python3 test/01_project_structure/verify_structure.py`
- **Environment:** Python 3.11.2, Linux 6.1.158+ (x86_64), 2 vCPUs,
  pytest 9.x, hypothesis 6.x, ruff 0.16.x, mypy 2.3.x, textual 8.2.8,
  py-spy 0.4.x
- **Result:** 241 passed / 0 failed (18 modules); ruff clean;
  mypy --strict clean (21 source files); structure OK; full benchmark
  re-run completed (RESULTS.md v0.4 table + v0.3→v0.4 delta)

### Notable development-time findings

| Finding | Outcome |
|---|---|
| `--tui` hang in headless shell | CLI guard added (exit 2, no hang); regression test added |
| fused classifier `line[-2]` on bare `"
"` line | IndexError risk; fixed with endswith + equivalence test |
| profiler corpus had spurious tail difference | generator bug (same class as §v0.3.4); profiler fixed, engine unaffected |
| text stored without terminators in hunks | test-side reconstruction needed `+ "\n"`; engine contract unchanged (formatters add terminators) |
