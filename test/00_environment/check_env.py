#!/usr/bin/env python3
"""Environment inventory for A-Train development.

Purpose:
    Print the facts that TEST_REPORT.md entries need: Python and tooling
    versions, external diff tools, CPU count and platform.
How to run:
    python3 test/00_environment/check_env.py
Expected result:
    A table of environment facts; exit code 0. Missing optional tools are
    reported as "missing" (not an error).
"""

from __future__ import annotations

import multiprocessing
import platform
import shutil
import subprocess
import sys


def _version(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return "missing"
    if proc.returncode != 0 and not proc.stdout:
        return "missing"
    return proc.stdout.strip().splitlines()[0] if proc.stdout else "present (no version)"


def main() -> int:
    rows = [
        ("python", sys.version.split()[0]),
        ("platform", f"{platform.system()} {platform.release()} ({platform.machine()})"),
        ("cpus", str(multiprocessing.cpu_count())),
        ("pytest", _version([sys.executable, "-m", "pytest", "--version"])),
        ("ruff", _version([sys.executable, "-m", "ruff", "--version"])),
        ("mypy", _version([sys.executable, "-m", "mypy", "--version"])),
        (
            "hypothesis",
            _version([sys.executable, "-c", "import hypothesis as h; print(h.__version__)"]),
        ),
        ("textual", _version([sys.executable, "-c", "import textual; print(textual.__version__)"])),
        ("GNU diff", _version(["diff", "--version"])),
        ("GNU patch", shutil.which("patch") or "missing"),
        ("git", _version(["git", "--version"])),
    ]
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        print(f"{name:<{width}}  {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
