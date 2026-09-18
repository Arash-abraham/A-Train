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

### Potential downside
Results become machine-dependent (a slow machine may coarsen a diff the
fast machine computes minimally) — worse determinism.

### Priority
Medium.

### Why it is not implemented
Not required by the v0.1 milestone; the current budget already guarantees
correctness. Deferred as a v0.4-optimization candidate.

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
