# A-Train Development Report

Living record of the v2 implementation programme (per prompt §20/§32).
Most recent milestones at the top. Facts only — nothing here is claimed
without a corresponding run recorded in `test/TEST_REPORT.md`.

---

## Milestone v0.2 — Presentation (2026-09-18)

### 1. What was implemented

- **Ignore options** (`core/diff_text.TextOptions`): `--ignore-space`
  (all whitespace), `--ignore-case`, `--ignore-matching REGEX` (drops
  hunks whose changed lines all match — GNU `-I` semantics),
  `--strip-trailing-cr` (CRLF/LF equality).  Normalisation affects
  *comparison keys only*; rendered lines keep the original text.
- **Encoding detection** (`core/reader.decode_text`): BOM sniff
  (UTF-8-sig / UTF-16 LE+BE / UTF-32 LE+BE) → strict UTF-8 →
  UTF-16-without-BOM byte-pattern heuristic → latin-1 fallback.
  Forced `--encoding` overrides everything and is strict.
- **Binary-vs-text decision** (`core/reader.is_textual`): a BOM wins over
  the NUL sniff; a UTF-16 byte pattern wins over the NUL sniff.
- **Two-phase intra-line refinement** (ROADMAP §3.5): inside every
  REPLACE block the first min(#del, #ins) line pairs get an
  `InlineRef(prefix_len, suffix_len)` (common char runs), capped at
  300 chars per line.  Formatters highlight only the changed middle.
- **`output/color.py`**: ANSI output with line numbers on both sides,
  bold changed-middle highlighting, `--color auto/always/never`
  (auto = TTY and not writing to a file).
- **`output/side_by_side.py`**: sdiff-style two-column view with
  `|`/`<`/`>` marks, `--width` (default: terminal width), truncation.
- **`output/html_report.py`**: standalone, self-contained HTML report
  (embedded CSS, no JS/external refs), metadata table, `<mark>` inline
  highlighting, HTML-escaped content.
- **`output/json_out.py`**: stable, deterministic JSON document (mode,
  identical, stats, per-file metadata incl. digest/encoding/newline,
  full hunk model).  For CI pipelines.
- **CLI**: `--format` now {unified, color, side, html, json}; identical
  inputs stay silent for terminal formats but html/json still emit a
  document (exit 0).  Package version bumped to 0.2.0.
- **Tests:** 52 new tests (options, encoding, inline refinement, four
  formatters, CLI v0.2 surface) — 171 total, all passing.

### 2. Bugs encountered and fixed (all real, all reproduced by a test)

| # | Symptom | Root cause | Fix | Regression test |
|---|---|---|---|---|
| 1 | UTF-16 (BOM) files reported "Binary files differ" | NUL sniff classified BOM-bearing UTF-16 as binary before decoding | `reader.is_textual`: BOM ⇒ text, UTF-16 pattern ⇒ text | `tests/test_encoding.py` + `test_cli_v02.py::test_encoding_flag_end_to_end` |
| 2 | BOM-less UTF-16 decoded as UTF-8 mojibake | NUL is *valid* UTF-8, so the strict UTF-8 attempt succeeded and short-circuited | skip the UTF-8 attempt when NUL sniff fires; try UTF-16 heuristic first | `test_encoding.py::test_utf16_without_bom_detected_by_heuristic` |
| 3 | side-by-side rows overflowed the requested width | column formula `(width-3)//2` ignored the 14 chars of per-row chrome | `_ROW_OVERHEAD = 14` factored into the formula | `test_formatters.py::test_side_layout_and_marks`, `test_cli_v02.py::test_side_width_option` |
| 4 | dangling ANSI sequences (`ESC[31mESC[0m`) around empty highlight segments | `_paint_inline` emitted codes for empty prefix/suffix parts | empty segments emit nothing | `test_cli_v02.py::test_color_always_vs_never` |
| 5 | (test-design) early inline expectations assumed wrong prefix/suffix splits (e.g. `"foo = 1"` vs `"foo = 2"` has *no* common suffix) | authoring error, not engine error | expectations corrected against the documented definition | `tests/test_inline.py` |

### 3. Design notes

- `--ignore-matching` drops whole hunks (all *changed* lines must match),
  matching GNU `--ignore-matching-lines`; when every hunk is dropped the
  result is "identical" and the exit code is 0.
- With `--ignore-space`, comparison keys lose the trailing newline too
  (whitespace removal eats it); harmless because terminators are uniform
  within a split.
- Forced `--encoding` on a genuinely binary file decodes anyway
  (`diff --text` behaviour) and `is_binary` stays accurate in metadata.

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
