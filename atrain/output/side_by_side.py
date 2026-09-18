"""Side-by-side two-column terminal view (ROADMAP.md, §5, format ``side``).

sdiff-style layout with line numbers on both sides:

.. code-block:: text

    --- a.txt          +++ b.txt
    @@ -1,3 +1,3 @@
       1  keep         |  1  keep
       2  old          |  2  new
       3  only-a       <
                          4  only-b >

Marks: `` `` equal, ``|`` changed pair, ``<`` removed, ``>`` added.
Lines longer than a column are truncated (deterministic output; wrapping
would need terminal-width negotiation at render time).
"""

from __future__ import annotations

import shutil

from atrain.core.models import DiffResult, Hunk, LineTag

DEFAULT_WIDTH = 80
MIN_COLUMN = 20
# Fixed overhead of one data row: 5 (number+space) + 2 (gutter)
# + 1 (mark) + 1 (space) + 5 (number+space).
_ROW_OVERHEAD = 14


def _column_width(width: int | None) -> int:
    """Width of each text column so a full row fits within *width*."""
    if width is None:
        try:
            width = shutil.get_terminal_size().columns
        except (OSError, ValueError):  # pragma: no cover — defensive
            width = DEFAULT_WIDTH
    return max(MIN_COLUMN, (width - _ROW_OVERHEAD) // 2)


_Row = tuple[int | None, str, str, int | None, str]


def _rows(hunk: Hunk) -> list[_Row]:
    """Flatten a hunk into ``(a_no, a_text, mark, b_no, b_text)`` rows."""
    rows: list[_Row] = []
    a_no = hunk.a_start + 1
    b_no = hunk.b_start + 1
    pending_del: list[tuple[int, str]] = []
    pending_ins: list[tuple[int, str]] = []

    def flush() -> None:
        pairs = min(len(pending_del), len(pending_ins))
        for k in range(pairs):
            d_no, d_text = pending_del[k]
            i_no, i_text = pending_ins[k]
            rows.append((d_no, d_text, "|", i_no, i_text))
        for d_no, d_text in pending_del[pairs:]:
            rows.append((d_no, d_text, "<", None, ""))
        for i_no, i_text in pending_ins[pairs:]:
            rows.append((None, "", ">", i_no, i_text))
        pending_del.clear()
        pending_ins.clear()

    for line in hunk.lines:
        if line.tag is LineTag.CONTEXT:
            flush()
            rows.append((a_no, line.text, " ", b_no, line.text))
            a_no += 1
            b_no += 1
        elif line.tag is LineTag.DELETE:
            pending_del.append((a_no, line.text))
            a_no += 1
        else:
            pending_ins.append((b_no, line.text))
            b_no += 1
    flush()
    return rows


def _truncate(text: str, col: int) -> str:
    return text[:col]


def render(
    result: DiffResult, a_label: str, b_label: str, width: int | None = None
) -> str:
    """Render *result* as a two-column view (empty string when identical)."""
    if result.identical or not result.hunks:
        return ""
    col = _column_width(width)
    gutter = "  "
    out: list[str] = [
        "--- " + _truncate(a_label, max(1, col - 4)).ljust(col),
        gutter + "+++ " + _truncate(b_label, max(1, col - 4)) + "\n",
    ]
    for hunk in result.hunks:
        header = f"@@ -{hunk.a_start + 1},{hunk.a_count} +{hunk.b_start + 1},{hunk.b_count} @@"
        out.append(f"{header}\n")
        for a_no, a_text, mark, b_no, b_text in _rows(hunk):
            left_no = f"{a_no:>4} " if a_no is not None else "     "
            right_no = f"{b_no:>4} " if b_no is not None else "     "
            left = f"{left_no}{_truncate(a_text, col).ljust(col)}"
            right = _truncate(b_text, col)
            out.append(f"{left}{gutter}{mark} {right_no}{right}".rstrip() + "\n")
    return "".join(out)
