# A-Train Development Report

Living record of the v2 implementation programme (per prompt §20/§32).
Most recent milestones at the top. Facts only — nothing here is claimed
without a corresponding run recorded in `test/TEST_REPORT.md`.

---

## Milestone v0.1 — Core (2026-09-18)

### 1. What was implemented

- **Scaffolding:** `pyproject.toml` (setuptools backend, console script
  `atrain`, optional `dev` / `tui` extras, pytest/ruff/mypy
  configuration), package `atrain` with `core/` and `output/` subpackages.
- **`core/models.py`:** typed data models — `FileMeta`, `Newline`,
  `LineTag`, `Opcode`/`OpcodeTag`, `DiffLine`, `Hunk`, `DiffStats`,
  `DiffResult`, plus `compute_stats`. Engines produce these; formatters
  consume them; the core imports nothing but the standard library.
- **`core/hasher.py`:** BLAKE2b-128 digests (`digest_bytes`,
  `file_digest` with memory-mapped fast path and chunked fallback) and
  the hash-based early exit (`files_identical`).
- **`core/reader.py`:** `load_bytes` (mmap ≥ 1 MiB, plain read below),
  binary sniffing (NUL in leading 8 KiB), `decode_text` (forced encoding,
  else UTF-8 → latin-1 fallback), `split_lines` (splits on `\n` only —
  never the wider `str.splitlines` boundaries), `line_content`,
  `detect_newline`, `load_text`.
- **`core/diff_text.py`:** line interning to dense integer ids, Myers
  O(ND) with **linear-space middle-snake refinement**, two-sided
  prefix/suffix trimming at every recursion node, work-budget guard with
  GNU-style "one replacement" fallback, opcode merging, difflib-style
  hunk grouping with configurable context, `compare_files` with
  hash-based early exit and binary short-circuit.
- **`output/unified.py`:** patch-compatible unified rendering including
  GNU `@@ -l,s +l,s @@` numbering rules and
  `\ No newline at end of file` markers.
- **`cli.py` + `__main__.py`:** `python -m atrain A B` with `--mode`,
  `--format`, `-U/--context`, `--encoding`, `-o/--output`, `--version`;
  GNU-style exit codes (0 same / 1 differ / 2 error).
- **Tests:** 119 tests across `tests/` (models, hasher, reader, engine,
  unified, CLI, GNU golden tests) — all passing, including 700
  property-based cases (hypothesis) asserting *validity* (apply the edit
  script → target) and *optimality* (edit count equals an independent
  LCS-based reference).
- **Exploratory artifacts:** `test/00_environment/check_env.py`,
  `test/01_project_structure/verify_structure.py`,
  `test/05_text_diff/profile_diff_text.py`.

### 2. Architecture decisions (and deviations from ROADMAP.md)

- **Line "hashing" = interning.** ROADMAP §3.2 says lines are "mapped to
  a 64-bit integer hash". A-Train v0.1 instead interns each distinct line
  to a *dense integer id* through one shared table. Rationale: equality
  of ids is then exact by construction — a 64-bit hash can collide and
  would need a verification pass to stay correct; dense ids also beat
  arbitrary 64-bit ints in comparisons. The roadmap's *intent* (never
  feed strings to the algorithm; diff integer arrays) is fully realised.
- **Iterative recursion.** The middle-snake divide & conquer is expressed
  with an explicit stack of `("diff"|"emit", ...)` frames so inputs
  beyond Python's recursion limit cannot crash the engine.
- **Complexity guard.** `MAX_EDIT_COST = 50_000_000` inner iterations;
  exhaustion produces a correct-but-non-minimal single REPLACE over the
  differing interior (mirrors GNU diff's own give-up heuristics).
  Trade-off documented in IMPROVEMENT_SUGGESTIONS.md #2.
- **Forced encoding overrides the binary sniff.** With `--encoding`, a
  NUL-containing file is decoded anyway (user asserted "text", like
  `diff --text`); auto-detection still refuses to decode binaries.

### 3. Bugs encountered and fixed (all real, all reproduced by a test)

| # | Symptom | Root cause | Fix | Regression test |
|---|---|---|---|---|
| 1 | `FrozenInstanceError` on any real comparison | `load_text` mutated the frozen `FileMeta` | build the final `FileMeta` once, fully populated | `test_reader.py::test_load_text_metadata` |
| 2 | Files with different content reported identical | `intern_lines` built a *separate* table per file, so `gamma` and `delta` both got id 2 and the id sequences compared equal | `intern_line_pairs` interns both inputs into one shared table | property tests + every CLI test |
| 3 | Differing files exited 0 | `cli._compare_text` returned `_emit(...)`'s "OK" status | emit, then return `EXIT_DIFFERENCES` | `test_cli.py::test_differences_exit_one_and_print_patch` |
| 4 | `BufferError: cannot close exported pointers exist` on ≥ 1 MiB files | `close()` closed the `mmap` while its `memoryview` was still exported | `LoadedFile` now releases the view first, then closes the map | `test_reader.py::test_load_bytes_large_file_memory_mapped` |
| 5 | Pure-CRLF files classified `MIXED` | `has_lf` used `endswith("\n")`, true for `"\r\n"` too | LF probe excludes `"\r\n"` endings | `test_reader.py::test_detect_newline` |
| 6 | Golden test failures on files without trailing newline | test-only applier stripped the newline of the *context* line when the GNU marker followed a `-` line | marker handling now tracks the previous tag; only `+` lines are adjusted | `tests/test_golden_gnu.py` no-newline cases |
| 7 | "Optimality" failures in early engine tests | the *reference* metric was Levenshtein distance (substitutions allowed); Myers counts insert/delete only, so `D = N + M − 2·LCS` | reference DP replaced with LCS-based distance | `tests/test_diff_text.py` (500 + 200 property cases) |
| 8 | (previous session) difflib merges the final `-`/`+` lines when both inputs lack a trailing newline | quirk of `difflib.unified_diff` splitting | documented in `tests/test_smoke.py` (`_tokenize_patch`); A-Train's own renderer is unaffected | `tests/test_smoke.py` |

Items 1–6 were found by the v0.1 test suite and CLI smoke runs during
development; none remain open.

### 4. Performance notes (informal; formal benchmarks come with v0.3)

`test/05_text_diff/profile_diff_text.py`, 20 000-line inputs, 2-vCPU
container:

- identical inputs: **0.007 s** (dominated by interning; the Myers search
  short-circuits via common-prefix trim)
- one changed line: single-hunk result in well under 0.1 s
- adversarial full-replacement (~26 600 edit distance) hits the
  complexity guard after burning the full budget (tens of seconds in
  pure Python) and then returns the correct coarse diff — see
  IMPROVEMENT_SUGGESTIONS.md #2.

### 5. Not done in this milestone (by design)

- Formal benchmarks (v0.3), color/side/html/json output (v0.2), ignore
  options and encoding auto-detection refinements (v0.2), binary/json/
  csv/dir modes (v0.3), TUI and hash cache (v0.4). The pre-existing
  repository file `test.py` (a one-line user placeholder) was left
  untouched deliberately (prompt §28).
