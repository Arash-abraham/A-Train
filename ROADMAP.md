# A-Train — Development Roadmap (v2)

> **Authoritative planning document** for the redevelopment of A-Train, a high-performance
> file comparison tool. This document is the single source of truth for the v2 development
> programme; each phase is tracked and checked off here as it is completed.

---

## 0. Current Repository State

At the outset of the v2 programme, the repository contained no Python source code: its full
Git history consisted of a single commit (`292d4e8`) introducing two branding images and a
one-line JavaScript placeholder. That placeholder was unrelated to the Python project and has
been **removed** by decision of the repository owner (2026-09-11). The repository now contains:

| Path | Current Content |
|---|---|
| `README.md` | Project overview |
| `ROADMAP.md` | This document |
| `Img/The-Boys-A-Train-Music-Video-Amazon.avif` | Branding asset (A-Train character) |
| `Img/a_train_hd_the_boys-1920x1080.jpg` | Branding asset (A-Train character) |

- **No Python source code exists in this repository at present.** Inspection of stashes and
  unreachable objects (`git fsck --lost-found`) recovered no prior implementation either.
- Practical consequence: the previous Python implementation was either never pushed to this
  repository or resides elsewhere. There are two paths forward:
  1. Import the previous implementation into this repository and continue development on top of it; or
  2. Build v2 from scratch in strict accordance with this document.
- In either case, the roadmap below remains valid.

---

## 1. Vision

A-Train is a two-file comparison tool defined by four properties:

1. **Fast** — identical or large inputs are resolved in a fraction of a second.
2. **Accurate** — diffs are correct, minimal, and human-readable.
3. **Purposeful** — each input class (text, binary, JSON, CSV, directory trees) is served by a
   dedicated comparison mode; no single general-purpose algorithm is forced upon all inputs.
4. **Integrable** — patch-compatible output, scriptable, and CI-ready.

---

## 2. Proposed Architecture

```
A-Train/
├── atrain/
│   ├── __init__.py            # Package version and public API
│   ├── __main__.py            # Entry point: python -m atrain
│   ├── cli.py                 # Command-line interface and argument parsing
│   ├── core/
│   │   ├── reader.py          # Memory-mapped, chunked I/O; encoding detection
│   │   ├── hasher.py          # Line/chunk hashing (BLAKE2)
│   │   ├── diff_text.py       # Myers + histogram heuristics; two-phase refinement
│   │   ├── diff_binary.py     # Chunked comparison; rolling-hash region detection
│   │   ├── diff_structured.py # Semantic comparison for JSON/CSV
│   │   └── models.py          # Data classes: Hunk, DiffResult, FileMeta
│   ├── output/
│   │   ├── unified.py         # Patch-compatible unified diff
│   │   ├── side_by_side.py    # Two-column terminal view
│   │   ├── color.py           # Colored terminal output
│   │   ├── html_report.py     # Standalone HTML report
│   │   └── json_out.py        # Machine-readable output
│   └── tui/                   # (Phase 4) Interactive terminal UI (Textual)
├── tests/
├── benchmarks/
├── Img/                       # Branding assets (existing)
├── README.md
├── ROADMAP.md                 # This document
└── pyproject.toml
```

Guiding principles:

- **A pure, dependency-free core.** `core/` uses only the Python standard library;
  presentational dependencies (e.g., Rich) are confined to the output layer and remain optional.
- **Separation of logic and presentation.** The diff engine has no knowledge of terminals or
  HTML; formatters consume an explicit result model.
- **Explicit data models.** Comparison results are plain data classes (`Hunk`, `DiffResult`,
  `FileMeta`) consumed uniformly by every output formatter.

---

## 3. Performance Engine

Techniques ordered by expected impact:

1. **Hash-based early exit.** Before any diffing: size comparison plus a BLAKE2 digest of the
   full input. Identical files are resolved definitively without a single line comparison.
2. **Pre-hashed lines.** Lines are never fed to the diff algorithm as strings; each line is
   first mapped to a 64-bit integer hash, and the Myers algorithm operates on an integer
   array — orders of magnitude faster than string comparison.
3. **The correct algorithm instead of `difflib`.** `difflib.SequenceMatcher` exhibits O(n²)
   worst-case behaviour and is designed for fuzzy matching, not diffing. Implementation plan:
   **Myers O(ND)** with linear-space refinement (Hirschberg) plus the **histogram heuristic**
   (as used by Git) for readable output.
4. **Memory-mapped I/O.** Large inputs are memory-mapped rather than copied into RAM; only
   line offsets are retained.
5. **Two-phase diffing.** A coarse line-level pass first; word/character-level refinement is
   applied **only within changed hunks**, never across the full input.
6. **Parallel directory comparison.** Tree comparison is distributed across a
   `ProcessPoolExecutor`; per-file work is independent.
7. **Optional hash cache.** A `.atrain-cache` artifact accelerates repeated comparisons in
   development loops.
8. **Continuous benchmarking.** A benchmark suite runs against `git diff`, GNU `diff`, and
   `difflib`; figures are published in `benchmarks/RESULTS.md` for every release.

**Quantitative target:** two 100 MB text files compared in under one second on commodity hardware.

---

## 4. Purpose-Built Comparison Modes

| Mode | Dedicated Behaviour |
|---|---|
| `text` | Line-based diff with intra-line word-level refinement; whitespace / case / regex ignore options |
| `binary` | Chunked (e.g., 64 KB) comparison; rolling-hash (Rabin–Karp) change-region detection; hex display |
| `json` | Semantic comparison independent of key order; path-based (JSONPath-style) change reporting |
| `csv` | Key-column-aware row comparison; added / removed / modified record reporting |
| `dir` | Tree diff: added / removed / modified files, followed by per-file diffs |

Cross-cutting behaviours:

- Automatic encoding detection (UTF-8 → UTF-16 → latin-1) and CRLF/LF normalization.
- Automatic mode detection from content (magic bytes / sniffing) when no mode is specified.

---

## 5. Output Formats

| Format | Description |
|---|---|
| `unified` | Compatible with `patch` and `git apply` |
| `color` | Colored terminal output with line numbers |
| `side` | Side-by-side two-column view |
| `html` | Standalone, shareable report |
| `json` | Machine-readable output for CI and downstream tooling |

---

## 6. User Interfaces

- **Phase 1 — CLI:** `atrain file_a file_b --mode text --format color --ignore-space`
- **Phase 2 — Configuration:** per-project defaults via `atrain.toml`.
- **Phase 4 — TUI:** interactive terminal interface built on Textual (synchronized scrolling,
  keyboard navigation).
- **Desktop GUI (optional, later):** PySide6 — only if a concrete need is demonstrated.

---

## 7. Quality Assurance and Continuous Integration

- `pytest` with `hypothesis` property-based testing, asserting the invariant:
  *applying the produced diff to the source file must reproduce the target file exactly.*
- Golden tests validated against GNU diffutils output.
- `ruff` linting and `mypy --strict` typing on `core/`.
- GitHub Actions workflow executing tests and benchmarks on every pull request.

---

## 8. Execution Milestones

### v0.1 — Core
- [ ] Project scaffolding and `pyproject.toml`
- [ ] `reader`, `hasher`, and hash-based early exit
- [ ] Myers over hashed lines with `unified` output
- [ ] Baseline CLI
- [ ] Baseline test suite

### v0.2 — Presentation
- [ ] `color` and `side` output formats
- [ ] Ignore options (whitespace / case / regex)
- [ ] Encoding detection and CRLF normalization
- [ ] `html` and `json` reports

### v0.3 — Advanced Modes
- [ ] `binary` mode
- [ ] Parallelized `dir` mode
- [ ] Semantic `json` / `csv` modes
- [ ] Formal benchmarks against GNU diff and `difflib`

### v0.4 — Interactive UI and Optimization
- [ ] Textual-based TUI
- [ ] Hash cache
- [ ] Profiling and optimization (py-spy)
- [ ] Final README with branding assets from `Img/`

---

## 9. Branding and Repository Hygiene

- The assets in `Img/` will serve as the project logo and hero imagery in the README and
  documentation; the speed metaphor is consistent with the character.
- **Repository hygiene:** the unrelated one-line JavaScript placeholder inherited from the
  bootstrap commit was removed on 2026-09-11 by decision of the repository owner. Should a
  web interface ever be planned, a properly named module will be introduced instead.

---

## 10. Definition of Done (v1)

1. On inputs of 50 MB or larger, at least 2× faster than `difflib` and on par with GNU `diff`
   in the published benchmark.
2. Zero false diffs across the test corpus (validated against GNU diff).
3. `python -m atrain a b` functions with the Python standard library alone; presentational
   dependencies remain optional.
4. A complete README with usage examples, sample output, and branding imagery.

---

*Last updated: 2026-09-11. This is a living document; each milestone is checked off here upon completion.*
