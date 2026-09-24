"""Baseline smoke tests for A-Train.

A-Train is currently in its bootstrap state (see ROADMAP.md, section 0), so
this suite validates the repository itself plus a standard-library reference
implementation of the project's core invariant:

    *applying the produced diff to the source file must reproduce the
    target file exactly.*  (ROADMAP.md, section 7)

The reference implementation uses only ``difflib`` — matching the project's
zero-hard-dependency philosophy — so this file runs under pytest *or* as a
plain script.  Once the real engine lands (v0.1 milestone: "Baseline test
suite"), these cases graduate into tests of the ``atrain`` package itself,
ideally as ``hypothesis`` property-based tests.

Run with either::

    python3 -m pytest tests/
    python3 tests/test_smoke.py
"""

from __future__ import annotations

import difflib
import random
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Repository structure (ROADMAP.md, section 0 — bootstrap state)
# ---------------------------------------------------------------------------

def test_repo_root_documents_exist() -> None:
    """README.md and ROADMAP.md must exist at the repository root."""
    for name in ("README.md", "ROADMAP.md"):
        path = REPO_ROOT / name
        assert path.is_file(), f"missing required document: {name}"


def test_documents_mention_project_name() -> None:
    """Both documents must agree on the project name (A-Train)."""
    for name in ("README.md", "ROADMAP.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "A-Train" in text, f"{name} does not mention the project name"


def test_roadmap_defines_core_invariant() -> None:
    """The ROADMAP must state the invariant this suite is designed around."""
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "reproduce the target file exactly" in roadmap, (
        "ROADMAP.md no longer states the core invariant; "
        "update this suite's docstring to match"
    )


# ---------------------------------------------------------------------------
# Reference validation of the core invariant (ROADMAP.md, section 7)
# ---------------------------------------------------------------------------

_HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _tokenize_patch(source: str, patch: str) -> list[str]:
    """Split *patch* into logical diff lines, undoing one difflib quirk.

    When both files end without a trailing newline *and* their final lines
    differ, ``difflib.unified_diff`` emits them merged onto one line —
    ``"-beta+gamma"`` — because it only separates diff lines by the newline
    the (missing) source line ends with.  Since the source text is known,
    the merge point is unambiguous and can be split deterministically.
    """
    lines = patch.splitlines(keepends=True)
    if source and not source.endswith("\n") and lines and lines[-1].startswith("-"):
        tail = source.splitlines(keepends=True)[-1]  # last line, without "\n"
        last = lines[-1]
        if last[1:].startswith(tail):
            rest = last[1 + len(tail):]
            if rest.startswith("+"):
                lines[-1:] = ["-" + tail, rest]
    return lines


def _apply_unified_diff(source: str, patch: str) -> str:
    """Apply a unified diff to *source* and return the patched text.

    A minimal, standard-library-only reimplementation of patch application.
    It handles exactly the well-formed unified output produced by
    ``difflib.unified_diff`` — enough to validate the invariant, not a
    general-purpose ``patch(1)``.
    """
    source_lines = source.splitlines(keepends=True)
    out: list[str] = []
    src_pos = 0  # index of the next unclaimed source line

    for line in _tokenize_patch(source, patch):
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            match = _HUNK_RE.match(line)
            assert match is not None, f"malformed hunk header: {line!r}"
            start = int(match.group(1))
            if start > 0:  # a start of 0 means "before the first line"
                out.extend(source_lines[src_pos:start - 1])
                src_pos = start - 1
            continue
        if line.startswith("-"):
            src_pos += 1
            continue
        if line.startswith("+"):
            out.append(line[1:])
            continue
        out.append(line[1:])
        src_pos += 1

    out.extend(source_lines[src_pos:])
    return "".join(out)


def _unified_patch(source: str, target: str) -> str:
    """Produce a unified diff between *source* and *target* (difflib)."""
    return "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            target.splitlines(keepends=True),
            fromfile="a",
            tofile="b",
        )
    )


_CASES: list[tuple[str, str, str]] = [
    ("identical files", "alpha\nbeta\n", "alpha\nbeta\n"),
    ("single-line change", "alpha\nbeta\ngamma\n", "alpha\nbeta\ndelta\n"),
    ("insertion at start", "beta\ngamma\n", "alpha\nbeta\ngamma\n"),
    ("insertion in middle", "alpha\ngamma\n", "alpha\nbeta\ngamma\n"),
    ("insertion at end", "alpha\n", "alpha\nbeta\n"),
    ("deletion", "alpha\nbeta\ngamma\n", "alpha\ngamma\n"),
    ("empty source", "", "alpha\nbeta\n"),
    ("empty target", "alpha\nbeta\n", ""),
    ("no trailing newline", "alpha\nbeta", "alpha\ngamma"),
    ("mixed shuffle", "a\nb\nc\nd\n", "d\nb\nx\nc\n"),
]


def test_core_invariant_fixed_cases() -> None:
    """apply(diff(a, b), a) == b for every fixed case."""
    for name, source, target in _CASES:
        patch = _unified_patch(source, target)
        result = _apply_unified_diff(source, patch)
        assert result == target, f"invariant broken for case {name!r}: {result!r} != {target!r}"


def test_core_invariant_empty_patch_is_identity() -> None:
    """Diffing a file against itself yields an empty patch that changes nothing."""
    source = "alpha\nbeta\ngamma\n"
    patch = _unified_patch(source, source)
    assert patch == "", "identical inputs must short-circuit to an empty diff"
    assert _apply_unified_diff(source, patch) == source


def test_core_invariant_seeded_random_cases() -> None:
    """Round-trip 100 deterministic pseudo-random case pairs (mini-hypothesis).

    Seeded for reproducibility; when ``hypothesis`` becomes available this
    test should be replaced by a true property-based test.
    """
    rng = random.Random(42)
    alphabet = ["alpha", "beta", "gamma", "delta", "epsilon", "\n"]
    for _ in range(100):
        source = "".join(rng.choice(alphabet) + "\n" for _ in range(rng.randint(0, 12)))
        target = "".join(rng.choice(alphabet) + "\n" for _ in range(rng.randint(0, 12)))
        patch = _unified_patch(source, target)
        assert _apply_unified_diff(source, patch) == target, (
            f"invariant broken for\n  source={source!r}\n  target={target!r}"
        )


# ---------------------------------------------------------------------------
# Plain-Python fallback runner (no pytest required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    failures = 0
    for name, obj in sorted(globals().items()):
        if name.startswith("test_") and callable(obj):
            try:
                obj()
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
            else:
                print(f"PASS  {name}")
    sys.exit(1 if failures else 0)
