"""Unified diff formatter — output compatible with ``patch`` and ``git apply``.

Header/hunk-numbering conventions follow GNU diff:
- ``@@ -l,s +l,s @@`` with ``l`` 1-based; the count is omitted when it is 1;
  when the count is 0 the line number is the 0-based position the hunk
  attaches to (i.e. the line *before* which content is inserted).
- A line without a trailing newline is followed by
  ``\\ No newline at end of file``.
"""

from __future__ import annotations

from atrain.core.models import DiffResult, Hunk


def _range(start: int, count: int) -> str:
    """Format one ``l,s`` half of a hunk header (start is 0-based)."""
    if count == 1:
        return str(start + 1)
    if count == 0:
        return f"{start},0"
    return f"{start + 1},{count}"


def hunk_header(hunk: Hunk) -> str:
    """Render the ``@@`` header line for *hunk*."""
    return f"@@ -{_range(hunk.a_start, hunk.a_count)} +{_range(hunk.b_start, hunk.b_count)} @@"


def render(result: DiffResult, a_label: str, b_label: str) -> str:
    """Render *result* as a unified diff string (empty when identical)."""
    if result.identical or not result.hunks:
        return ""
    out: list[str] = [f"--- {a_label}\n", f"+++ {b_label}\n"]
    for hunk in result.hunks:
        out.append(hunk_header(hunk))
        out.append("\n")
        for line in hunk.lines:
            out.append(line.tag.value)
            out.append(line.text)
            if line.newline:
                out.append("\n")
            else:
                out.append("\n\\ No newline at end of file\n")
    return "".join(out)
