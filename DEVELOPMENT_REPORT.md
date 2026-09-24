# A-Train Development Report

Living record of the v2 implementation programme (per prompt §20/§32).
Most recent milestones at the top. Facts only — nothing here is claimed
without a corresponding run recorded in `test/TEST_REPORT.md`.

---

## Milestone v0.4 — Interactive UI and Optimization (2026-09-18)

### 1. What was implemented

- **`atrain/tui/`** (new package): Textual-based interactive diff viewer
  (`DiffTui`) — single synchronized color-coded stream, hunk navigation
  (n/p), scrolling (j/k/g/G), live reload (r). Textual is imported
  lazily; the CLI fails with an installation hint instead of a traceback.
  Tested headless via Textual's `run_test()` pilot.
- **`core/cache.py`** (new): JSON digest cache keyed by
  `(path, size, mtime_ns)`, sorted-key atomic writes, corrupt-cache
  discard, `MAX_ENTRIES` pruning. Wired into `diff_tree` via
  `TreeOptions(use_cache, cache_path)` — hit entries skip hashing
  entirely (verified: a second run performs zero digest calls).
- **CLI**: `--tui` (files only, refuses non-TTY stdin/stdout with a clear
  error instead of hanging), `--cache` (dir mode only).
- **Wall-clock guard** (`diff_text.MAX_DIFF_SECONDS`, default 2 s):
  `_Budget` now also checks `time.monotonic()` every 65 536 work units.
  Pathological inputs fall back to the coarse-but-exact edit script
  instead of burning the full operation budget. Fallback correctness is
  regression-tested (target reconstruction).
- **py-spy-guided micro-optimisations** (evidence:
  `test/16_performance/pyspy_smallchange_30mb.txt`): fused
  split+newline-classification in `reader._split_and_classify` (removes
  a measured 12% phase), `setdefault`-based interning (~7% of intern
  phase), pop-based `split_lines` (~8%).
- **README rewritten** with `Img/` hero asset, real usage for every
  mode/format/flag, and measured performance figures.
- **Benchmarks re-run** after the changes (see RESULTS.md delta table):
  `alternating_5mb` 49.404 s → **2.665 s**.

### 2. Issues encountered and fixed

| # | Symptom | Root cause | Fix | Regression test |
|---|---|---|---|---|
| 1 | `--tui` hung forever in a non-interactive shell (sandbox timeout) | Textual waited for a terminal that never came | `_run_tui` refuses without a TTY (`exit 2`, clear message) | `tests/test_tui_cache.py::TestCliV04Flags::test_tui_rejected_without_tty` |
| 2 | `NameError: time` at first deadline check | the `import time` edit landed outside the applied replacement | import added properly | covered by the deadline tests |
| 3 | `IndexError` risk on 1-char `"
"` lines in the fused classifier | `line[-2]` on a bare-newline line | suffix-based `endswith` checks + 8-case equivalence test vs `split_lines`/`detect_newline` | `test_split_and_classify_equivalence` |
| 4 | 30 MB profile showed a second, spurious tail difference in the *profiler's own* corpus | shorter replacement line shifted the generator's byte accounting (same generator bug as §v0.3.4) | profiler builds the full line list first, mutates a copy | documented in the profiler header; generator fix pattern shared with benchmarks |

### 3. Environment note (honesty)

`~/.local` and `~/.cache` are not persisted in this workspace between
sessions; the toolchain (pytest, mypy, ruff, hypothesis, textual, py-spy)
and the digest cache were reinstalled/recreated during the session. The
`--cache` correctness tests use explicit cache paths inside `tmp_path`
and are unaffected.

---

## Milestone v0.3 — Advanced Modes (2026-09-18)

### 1. What was implemented

- **`core/diff_binary.py`**: hash-based early exit, block-wise common
  prefix/suffix trimming with byte refinement, then a block walk over the
  differing interior with **Rabin–Karp-style rolling-hash resync** —
  candidate needle starts `b[pb+c]` for `c = 0..64` are matched against a
  single rolling scan (hash matches verified byte-wise, so collisions can
  never corrupt results).  Unresyncable interiors degrade to one coarse
  region.  A `hexdump` renderer (`output/hex.py`) backs CLI/HTML output.
- **`core/diff_structured.py`**: semantic JSON (order-insensitive objects,
  JSONPath-style change locations, JSON number semantics with strict
  bool≠int, truncated value previews) and CSV (positional or **key-column**
  matching by header name or 1-based index, field-level modified rows,
  first-occurrence duplicate policy, deterministic sorted output).
  Malformed input raises `ValueError` → CLI exit 2.
- **`core/diff_tree.py`** (architecture addition, documented below):
  sorted deterministic walks, file/dir classification
  (added/removed/modified/unchanged/error), **ProcessPoolExecutor**
  parallelism for both digesting and per-file diffs, sequential fallback,
  per-file errors captured instead of fatal, binary modified files get
  region-based child diffs, empty dirs on one side reported as dir
  entries.
- **Formatters**: `unified`/`color`/`html`/`json` extended to all modes
  (`side` remains text-only and is rejected with a clear message
  otherwise); dir reports embed per-file diffs; JSON documents nest child
  results.
- **CLI**: `--mode {text,binary,json,csv,dir}`, `--key-col`, `--workers`.
- **`benchmarks/run_benchmarks.py` + `benchmarks/RESULTS.md`**: formal
  benchmarks vs difflib and GNU diff (see the results page for the full
  honest reading; highlights below).

### 2. Architecture additions (documented per the project rules)

- `core/diff_tree.py` is new: the ROADMAP §2 tree lists no tree-compare
  module; neither `diff_text` nor `diff_structured` owns walking.
- `output/hex.py` is new: hexdump rendering shared by unified/HTML output.

### 3. Bugs encountered and fixed (all real, all reproduced by a test)

| # | Symptom | Root cause | Fix | Regression test |
|---|---|---|---|---|
| 1 | `_common_suffix` returned a too-long suffix (golden trim test failed) | the mismatch scan walked the block from its *left* edge instead of the right | scan `k = 1..step` from the block's right edge | `tests/test_binary.py::test_trim_common_ends_exactness` |
| 2 | Three isolated 3-byte changes in 60 KiB collapsed into ONE coarse region | resync needle started at the corrupted bytes, so it matched nowhere and the engine gave up for the whole interior | **skip-resync**: candidate needles `b[pb+c]`, c ≤ 64, matched against one rolling scan | `tests/test_binary.py::test_multiple_separated_regions` + the region-reconstruction invariant |
| 3 | Dir mode produced empty textual children for modified *binary* files | `compare_files` refuses to decode binaries and returned no hunks | the tree worker switches to `compare_binary` for binary payloads | `tests/test_tree.py::test_binary_files_in_tree` |
| 4 | Benchmark "small change" corpora contained a *second, spurious* difference at the file tail (found while validating RESULTS numbers; also affected the exploratory phase-profiler) | replacing a line with a shorter string shifted the writer's byte accounting, so the generator appended extra lines to one file | corpora are built as full line lists first; mutation applies afterwards (byte accounting unaffected) | generator fix visible in `benchmarks/run_benchmarks.py::_make`; the 100 MB phase profiler (`test/16_performance/`) documents the same pitfall |

### 4. Performance facts (full data and discussion in benchmarks/RESULTS.md)

- `identical_100mb`: **0.338 s** — the ROADMAP "100 MB < 1 s" target is
  met for identical inputs (hash-based early exit).
- `small_change_100mb`: 3.644 s — target missed; the phase profiler
  shows the algorithm itself costs 0.19 s while pure-Python decode/split
  (1.9 s) and interning (1.4 s) dominate. Evidence recorded;
  remediation documented as IMPROVEMENT_SUGGESTIONS #7, **not
  implemented**.
- `alternating_5mb`: 49.4 s (complexity-guard budget burn) vs GNU 0.032 s
  — documented weakness; time-based cutoff suggestion upgraded to High.
- vs difflib (measured inputs): 4.6× (identical_5mb) to 19× (scattered)
  faster; difflib times out at 60 s on alternating_5mb and is capped
  above ~6 MiB.

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
