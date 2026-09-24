# benchmarks/

Repeatable performance benchmarks for A-Train (ROADMAP.md, §3.8 and §8
v0.3 milestone: "Formal benchmarks against GNU diff and `difflib`").

**Status:** the formal benchmark suite is scheduled with the v0.3
milestone. This directory exists from v0.1 so the repository structure
matches ROADMAP.md §2; results will be published in `RESULTS.md` there.

Planned contents:

- `run_benchmarks.py` — corpus generation + timing harness
  (A-Train vs `difflib` vs GNU `diff`; identical / small-change /
  large-change / worst-case inputs; wall time, peak memory where cheap).
- `RESULTS.md` — dated results with environment facts (never claims
  without a measured run; prompt §25).
