#!/usr/bin/env python3
"""Repository structure verification against ROADMAP.md §2.

Purpose:
    Check that the package tree matches the architecture promised by the
    roadmap for the milestones completed so far. Extended as v0.2–v0.4 add
    the remaining modules.
How to run:
    python3 test/01_project_structure/verify_structure.py
Expected result:
    "structure OK" and exit 0; otherwise the missing paths are listed and
    the exit code is 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Paths required by completed milestones.
REQUIRED_V01 = [
    "pyproject.toml",
    "atrain/__init__.py",
    "atrain/__main__.py",
    "atrain/cli.py",
    "atrain/core/__init__.py",
    "atrain/core/models.py",
    "atrain/core/reader.py",
    "atrain/core/hasher.py",
    "atrain/core/diff_text.py",
    "atrain/output/__init__.py",
    "atrain/output/unified.py",
    "tests/",
    "benchmarks/",
]

REQUIRED_V02 = [
    "atrain/output/color.py",
    "atrain/output/side_by_side.py",
    "atrain/output/html_report.py",
    "atrain/output/json_out.py",
]

REQUIRED_V03 = [
    "atrain/core/diff_binary.py",
    "atrain/core/diff_structured.py",
    "atrain/core/diff_tree.py",
    "benchmarks/run_benchmarks.py",
    "benchmarks/RESULTS.md",
]

REQUIRED_V04 = [
    "atrain/core/cache.py",
    "atrain/tui/__init__.py",
    "atrain/tui/app.py",
]

# Paths promised by later milestones; absence is informational right now.
PLANNED = [
    "atrain/core/diff_binary.py",
    "atrain/core/diff_structured.py",
    "atrain/tui/",
]


def main() -> int:
    missing = [
        rel
        for rel in REQUIRED_V01 + REQUIRED_V02 + REQUIRED_V03 + REQUIRED_V04
        if not (REPO_ROOT / rel).exists()
    ]
    for rel in missing:
        print(f"MISSING (required): {rel}")
    pending = [rel for rel in PLANNED if not (REPO_ROOT / rel).exists()]
    if pending:
        print(f"note: {len(pending)} planned paths not present yet (later milestones)")
    if missing:
        print("structure INCOMPLETE")
        return 1
    print("structure OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
