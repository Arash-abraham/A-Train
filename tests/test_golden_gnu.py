"""Golden tests against GNU diffutils and patch(1).

Semantic validation, not byte equality: hunk *boundaries* may legitimately
differ between implementations, so every patch is validated by applying it
and comparing the outcome (ROADMAP.md, §7 "golden tests"; the prompt's
§16 note that byte-for-byte equality is not required).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from atrain.core.diff_text import compare_files
from atrain.output.unified import render
from tests._applypatch import apply_unified

pytestmark = [
    pytest.mark.skipif(shutil.which("diff") is None, reason="GNU diff not available"),
    pytest.mark.skipif(shutil.which("patch") is None, reason="patch not available"),
]

CASES = [
    ("change one line", "alpha\nbeta\ngamma\n", "alpha\nbeta\ndelta\n"),
    ("insert in middle", "a\nc\n", "a\nc\nb\n"),
    ("delete line", "a\nb\nc\n", "a\nc\n"),
    ("empty to content", "", "a\nb\n"),
    ("content to empty", "a\nb\n", ""),
    ("no trailing newline both", "x\ny", "x\nz"),
    ("no trailing newline added", "x\ny", "x\ny\nz"),
    ("unicode persian", "سلام\nدنیا\n", "سلام\nجهان\n"),
    ("emoji", "hi 👋\n", "bye 🚂\n"),
    ("many scattered changes", "\n".join(f"l{i}" for i in range(40)) + "\n",
     "\n".join(f"l{i}" if i % 7 else f"X{i}" for i in range(40)) + "\n"),
    ("reordered blocks", "a\nb\nc\nd\n", "c\nd\na\nb\n"),
    ("whitespace change", "a \nb\n", "a\nb \n"),
]


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


def _gnu_diff(a: Path, b: Path) -> str:
    proc = subprocess.run(
        ["diff", "-u", str(a), str(b)], capture_output=True, text=True, check=False
    )
    assert proc.returncode in (0, 1), proc.stderr
    return proc.stdout


def _apply_with_patch(patch_text: str, source: Path, out: Path) -> None:
    proc = subprocess.run(
        ["patch", "-s", "-o", str(out), str(source)],
        input=patch_text,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"patch failed: {proc.stderr}\npatch:\n{patch_text}"


@pytest.mark.parametrize(("name", "a_text", "b_text"), CASES, ids=[c[0] for c in CASES])
def test_our_patch_applies_via_gnu_patch(
    name: str, a_text: str, b_text: str, tmp_path: Path
) -> None:
    a = _write(tmp_path, "a.txt", a_text)
    b = _write(tmp_path, "b.txt", b_text)
    result = compare_files(a, b)
    patch_text = render(result, str(a), str(b))
    if result.identical:
        assert patch_text == ""
        pytest.skip("identical inputs")
    out = tmp_path / "out.txt"
    _apply_with_patch(patch_text, a, out)
    assert out.read_bytes() == b.read_bytes()


@pytest.mark.parametrize(("name", "a_text", "b_text"), CASES, ids=[c[0] for c in CASES])
def test_gnu_patch_applies_via_our_applier(
    name: str, a_text: str, b_text: str, tmp_path: Path
) -> None:
    """Our reference applier must understand GNU diff's output too."""
    a = _write(tmp_path, "a.txt", a_text)
    b = _write(tmp_path, "b.txt", b_text)
    gnu_patch = _gnu_diff(a, b)
    if not gnu_patch:
        pytest.skip("identical inputs")
    assert apply_unified(a_text, gnu_patch) == b_text


@pytest.mark.parametrize(("name", "a_text", "b_text"), CASES, ids=[c[0] for c in CASES])
def test_exit_codes_match_gnu(
    name: str, a_text: str, b_text: str, tmp_path: Path
) -> None:
    a = _write(tmp_path, "a.txt", a_text)
    b = _write(tmp_path, "b.txt", b_text)
    gnu_rc = subprocess.run(
        ["diff", "-q", str(a), str(b)], capture_output=True, check=False
    ).returncode
    ours = compare_files(a, b)
    assert (0 if ours.identical else 1) == gnu_rc


def test_zero_false_diffs_on_identical_large_files(tmp_path: Path) -> None:
    """ROADMAP DoD #2: zero false diffs on identical inputs (early exit path)."""
    payload = "".join(f"line {i}: some content\n" for i in range(50_000))
    a = _write(tmp_path, "big_a.txt", payload)
    b = _write(tmp_path, "big_b.txt", payload)
    result = compare_files(a, b)
    assert result.identical
    assert result.hunks == []
