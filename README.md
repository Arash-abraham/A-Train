# A-Train

**A high-performance file comparison tool for developers.**

> Named after the fastest member of The Seven — because a diff should arrive before you
> finish blinking.

A-Train is a Python-based tool for comparing two files or directory trees, with an emphasis
on speed, precision, and purpose-built comparison modes. The project is currently under
active redevelopment; this document describes the tool, and
[ROADMAP.md](./ROADMAP.md) is the authoritative development plan.

> **Project status:** v2 is in the planning and early-development stage. The repository is in
> a bootstrap state (see [ROADMAP.md, §0](./ROADMAP.md#0-current-repository-state)); the
> engine described below is the target architecture.

---

## Highlights

- **Fast by design** — hash-based early exit for identical inputs, Myers diff over
  pre-hashed lines, and memory-mapped I/O for large files. Target: two 100 MB text files
  compared in under one second on commodity hardware.
- **Purpose-built modes** — dedicated comparison engines for text, binary, JSON, CSV, and
  directory trees; no single general-purpose algorithm forced upon all inputs.
- **Developer-friendly output** — patch-compatible unified diffs, colored terminal output,
  side-by-side views, standalone HTML reports, and machine-readable JSON for CI pipelines.
- **Zero hard dependencies** — the core engine relies exclusively on the Python standard
  library; presentational extras are optional.

## Comparison Modes

| Mode | Purpose |
|---|---|
| `text` | Line-based diff with intra-line word-level refinement; whitespace, case, and regex ignore options |
| `binary` | Chunked comparison with rolling-hash change-region detection and hex display |
| `json` | Semantic comparison independent of key order, with path-based change reporting |
| `csv` | Key-column-aware row comparison: added, removed, and modified records |
| `dir` | Parallelized tree comparison with per-file diffs |

## Planned Usage

```bash
# Basic comparison
python -m atrain baseline.txt candidate.txt

# Colored terminal output, ignoring whitespace differences
atrain a.py b.py --mode text --format color --ignore-space

# Machine-readable output for CI pipelines
atrain old.json new.json --mode json --format json > report.json

# Directory-tree comparison
atrain ./release-1.0 ./release-2.0 --mode dir
```

## Architecture

```
atrain/
├── core/      # Dependency-free comparison engine: reader, hasher, diff algorithms, models
├── output/    # Unified, colored, side-by-side, HTML, and JSON formatters
├── tui/       # Interactive terminal UI (planned, v0.4)
└── cli.py     # Command-line interface
```

The comparison core is deliberately isolated from presentation concerns: results are plain
data classes consumed uniformly by any output formatter. Full design rationale, performance
techniques, and milestone planning are documented in [ROADMAP.md](./ROADMAP.md).

## Performance Goals

- Compare two 100 MB text files in under one second on commodity hardware.
- At least 2× faster than `difflib`, and on par with GNU `diff`, on inputs of 50 MB or larger.
- Benchmark figures against `git diff`, GNU `diff`, and `difflib` published in
  `benchmarks/RESULTS.md` for every release.

## Repository Contents

| Path | Description |
|---|---|
| `README.md` | This document |
| `ROADMAP.md` | Authoritative development plan for v2 |
| `Img/` | Branding assets |

## Branding

The project takes its name and identity from A-Train, the speedster of *The Boys*.
Branding assets are maintained in [`Img/`](./Img/).

## License

The license for this project will be specified upon its first public release.
