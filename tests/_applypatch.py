"""Shared helper: apply a unified diff to source text (test-only reference).

Handles the GNU ``\\ No newline at end of file`` marker so it can apply
both A-Train's and GNU diff's output.  Deliberately strict: raises
``ValueError`` on any malformed or non-matching patch instead of guessing.
"""

from __future__ import annotations

import re

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_unified(source: str, patch: str) -> str:
    """Apply *patch* (unified format) to *source* and return the result."""
    source_lines = source.splitlines(keepends=True)
    out: list[str] = []
    pos = 0  # index of the next unclaimed source line
    last_tag = ""  # tag of the previous diff line, for "\ No newline" handling

    patch_lines = patch.splitlines(keepends=True)
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        i += 1
        if line.startswith("---") or line.startswith("+++"):
            continue
        match = _HUNK_RE.match(line.rstrip("\n"))
        if match is not None:
            start = int(match.group(1))
            if start > 0:  # a start of 0 means "attach before the first line"
                out.extend(source_lines[pos : start - 1])
                pos = start - 1
            continue
        if line.startswith("\\"):
            # "\ No newline at end of file": strips the newline of a '+'
            # line we just emitted.  After ' ' or '-' it is informational —
            # the source line involved already lacks the newline.
            if last_tag == "+" and out and out[-1].endswith("\n"):
                out[-1] = out[-1][:-1]
            continue
        if not line:
            continue  # tolerate a trailing newline at end of patch
        tag = line[0]
        last_tag = tag
        body = line[1:]
        if not body.endswith("\n"):
            # Patch itself lacked a final newline; only meaningful for the
            # very last line — treat as if it had one unless marked.
            body += "\n"
        if tag == " ":
            if pos >= len(source_lines):
                raise ValueError(f"context line beyond end of source: {body!r}")
            expected = source_lines[pos]
            if expected.rstrip("\n") != body.rstrip("\n"):
                raise ValueError(f"context mismatch: {expected!r} != {body!r}")
            out.append(expected)
            pos += 1
        elif tag == "-":
            if pos >= len(source_lines):
                raise ValueError(f"delete line beyond end of source: {body!r}")
            if source_lines[pos].rstrip("\n") != body.rstrip("\n"):
                raise ValueError(f"delete mismatch: {source_lines[pos]!r} != {body!r}")
            pos += 1
        elif tag == "+":
            out.append(body)
        else:
            raise ValueError(f"unknown patch line: {line!r}")

    out.extend(source_lines[pos:])
    return "".join(out)
