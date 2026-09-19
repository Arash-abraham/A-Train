# Improvement Suggestions

Recommendations discovered during development. **None of these are
implemented** — per the project rules, out-of-scope ideas are documented
here and deliberately left alone (prompt §21–23).

---

## 1. Time-based complexity guard instead of pure operation budget

### Current behavior
`diff_text.MAX_EDIT_COST` (50M inner iterations) bounds the Myers search.
On adversarial inputs (two large files with almost nothing in common) the
engine burns the whole budget — tens of seconds of pure Python — before
falling back to the coarse replacement.

### Suggested improvement
Also poll `time.monotonic()` every N steps and abort after e.g. 2 s, or
scale the budget by input size (as Git's `diffcore` heuristics do).

### Expected benefit
Bounded wall-clock latency on pathological inputs.

### Measured evidence (2026-09-18, benchmarks/RESULTS.md)
`alternating_5mb` (every 2nd line of a ~5 MiB file changed) burns the
full 50M-iteration budget: **49.4 s** in A-Train vs **0.032 s** GNU diff.
A time-based cutoff of ~1-2 s would cut this by an order of magnitude
while keeping the fallback correct.

### Potential downside
Results become machine-dependent (a slow machine may coarsen a diff the
fast machine computes minimally) — worse determinism.

### Priority
**High** (upgraded from Medium after the v0.3 measurements).

### Status update (2026-09-18, v0.4)
**Implemented** — `diff_text.MAX_DIFF_SECONDS` (default 2 s, checked
every 65 536 work units) aborts the search and falls back to the coarse
interior REPLACE. Measured: `alternating_5mb` 49.4 s → 2.665 s
(benchmarks/RESULTS.md); fallback correctness verified by
`tests/test_tui_cache.py::TestV04Optimizations`. Moved out of this file's
"not implemented" scope accordingly; the machine-dependence downside is
accepted and documented in the module docstring.

---

## 2. Histogram heuristic for readable hunks (ROADMAP §3.3)

### Current behavior
Plain Myers produces minimal diffs; on code with repeated lines
(e.g. `}` or blank lines) the chosen match points can be less
human-friendly than GNU/Git output.

### Suggested improvement
Git's histogram heuristic (or the simpler xdiff heuristics) to shift
match points toward low-frequency lines after the minimal script is
found.

### Expected benefit
More "natural" hunk boundaries, closer to `git diff` output.

### Potential downside
Post-processing pass costs time; output is no longer guaranteed minimal.

### Priority
Low (cosmetic).

### Why it is not implemented
ROADMAP lists it as optional ("در صورت نیاز"); correctness and minimality
were the v0.1 goals.

---

## 3. `atrain.toml` per-project configuration (ROADMAP §6, Phase 2)

### Current behavior
All options are CLI flags.

### Suggested improvement
Read per-project defaults from `atrain.toml` (context, ignore options,
format) when present; CLI flags override.

### Expected benefit
Teams get consistent diffs without retyping flags.

### Potential downside
Configuration precedence and file discovery need careful specification
and tests.

### Priority
Low.

### Why it is not implemented
Listed under "User Interfaces, Phase 2" in the roadmap but absent from the
§8 milestone checklist; not required to complete any milestone.

---

## 4. Automatic mode detection from content (ROADMAP §4 "cross-cutting")

### Current behavior
`--mode` must be given (currently only `text` exists; default `text`).

### Suggested improvement
Sniff JSON/CSV/binary magic and pick the dedicated engine when `--mode`
is omitted.

### Expected benefit
`python -m atrain a.json b.json` "just works".

### Potential downside
Ambiguous inputs (JSON-looking CSV); surprising mode switches in CI.

### Priority
Low.

### Why it is not implemented
Not in the §8 milestone checklist; explicit `--mode` is more predictable.

---

## 5. ProcessPool vs ThreadPool for directory mode

### Current behavior
(v0.3 planning note) ROADMAP §3.6 prescribes `ProcessPoolExecutor`.

### Suggested improvement
Benchmark both: hashing releases the GIL (threads win on large files and
avoid pickling `DiffResult`s), while per-file *text diffs* are
pure-Python (processes win on many-core machines).

### Expected benefit
Possibly simpler + faster on the common case.

### Potential downside
Divergence from the roadmap's literal wording if threads win.

### Priority
Medium (decide during v0.3).

### Why it is not implemented
v0.3 milestone work has not started yet.

---

## 6. Array matching for JSON diffs (similarity-based, not index-based)

### Current behavior
JSON arrays are compared index-wise: inserting an element at the front of
a 1000-element array reports 1000 changes.

### Suggested improvement
Match array elements by similarity or by key field (like CSV key columns)
before reporting, so a single insertion is reported as one insertion.

### Expected benefit
Dramatically smaller change lists for list-heavy documents.

### Potential downside
Heuristics can mis-pair elements; matching cost is super-linear.

### Priority
Medium.

### Why it is not implemented
Index-wise comparison is deterministic and predictable; ROADMAP only
requires "semantic comparison independent of key order" (objects), which
is implemented.

---

## 7. C-level text pipeline for the 100 MB target on *changed* inputs

### Current behavior
`small_change_100mb` runs in 3.6 s. Phase profile: decode+split 1.9 s,
interning 1.4 s, Myers 0.19 s. The algorithm is fast; pure-Python
per-line text processing is the bottleneck. (identical_100mb already
meets the <1 s target via the hash early exit: 0.34 s.)

### Suggested improvement
Index line offsets over the mmap buffer without materialising decoded
strings; hash lines with BLAKE2b over byte slices; decode only the lines
inside hunks. Alternatively accept a compiled helper (setuptools C
module) — trading the "zero hard dependencies" principle.

### Expected benefit
Likely brings 100 MB small-change under ~1.5 s; possibly under 1 s.

### Potential downside
Significant complexity in `reader`/`diff_text`; lazy decoding changes the
invariant that formatters receive decoded text eagerly.

### Priority
High (this is the roadmap's headline target).

### Why it is not implemented
The current milestone plan (§8) does not include a compiled pipeline;
re-architecting the reader exceeds the "improvement" boundary defined for
this programme and is therefore documented, not implemented.
