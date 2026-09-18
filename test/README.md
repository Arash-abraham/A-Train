# test/ — Development & Exploration Tests (0 تا 100)

This directory holds **development-side** test artifacts: exploratory
checks, debugging scripts, reproduction cases, profiling runs and
experiments. It is distinct from:

- `tests/` — the **official, CI-run pytest suite** for the project.
- `benchmarks/` — repeatable performance benchmarks (not debugging).

## Policy

Every script here starts with a header block:

```text
Purpose:              what it checks/explores
What it reproduces:   (for regression scripts) the original failure
How to run:           exact command
Expected result:      what "good" looks like
```

Nothing in this directory is executed by CI. Temporary debugging scripts
are **kept**, not deleted, and filed under the matching numbered group so
the development history stays auditable (prompt §17–18).

## Layout

| Group | Contents |
|---|---|
| `00_environment/` | Environment inventory used to annotate TEST_REPORT entries |
| `01_project_structure/` | Repository layout checks against ROADMAP.md §2 |
| `05_text_diff/` | Profiling / experiments for the Myers text engine |

Groups are added as the corresponding milestone work happens; the planned
full map (02 models, 03 reader, 04 hasher, 06 binary, 07 json, 08 csv,
09 directory, 10 output, 11 cli, 12 encoding, 13 edge cases, 14 error
handling, 15 large files, 16 performance, 17 regression, 18 property,
19 integration, 20 end-to-end) fills in over v0.2–v0.4. Formal coverage
lives in `tests/` regardless — this tree is for *development* artifacts.

## Test report

`TEST_REPORT.md` (this directory) logs every formal test run with
command, environment, result and root causes of failures.
