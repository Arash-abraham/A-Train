"""Colored terminal output with line numbers (ROADMAP.md, §5).

ANSI-only (no external dependency).  Colours are applied when the caller
decides (``--color auto`` resolves to a TTY check in the CLI); the
formatter itself is pure model → string.
"""

from __future__ import annotations

from atrain.core.models import DiffLine, DiffResult, LineTag

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"

_WIDTH = 4  # line-number field width


def _paint_inline(text: str, color: str, inline: tuple[int, int] | None) -> str:
    """Colour *text* entirely, bolding the changed middle of a pair.

    Empty segments emit nothing (no dangling escape sequences).
    """
    if inline is None:
        return f"{color}{text}{RESET}" if text else ""
    prefix, suffix = inline
    middle_start, middle_end = prefix, len(text) - suffix
    if middle_end <= middle_start:
        return f"{color}{text}{RESET}" if text else ""
    parts = [
        f"{color}{text[:middle_start]}{RESET}" if middle_start else "",
        f"{BOLD}{color}{text[middle_start:middle_end]}{RESET}",
        f"{color}{text[middle_end:]}{RESET}" if middle_end < len(text) else "",
    ]
    return "".join(parts)


def _colorize_lines(text: str) -> str:
    """Paint pre-rendered plain lines by their leading marker."""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if stripped.startswith(("---", "+++")) or stripped.startswith("@@"):
            out.append(f"{BOLD}{CYAN}{stripped}{RESET}\n")
            continue
        if stripped.startswith("errors:"):
            out.append(f"{BOLD}{RED}{stripped}{RESET}\n")
            continue
        head = stripped[:1]
        if head in ("+", "-", "~", "!"):
            paint = {"+": GREEN, "-": RED, "~": YELLOW, "!": RED}[head]
            out.append(f"{paint}{stripped}{RESET}\n")
        elif stripped.startswith("Binary files"):
            out.append(f"{BOLD}{stripped}{RESET}\n")
        else:
            out.append(line)
    return "".join(out)


def _line(
    line: DiffLine, a_no: int | None, b_no: int | None, color: bool
) -> str:
    """One numbered, coloured output row (text carries no newline)."""
    a_field = f"{a_no:>{_WIDTH}}" if a_no is not None else " " * _WIDTH
    b_field = f"{b_no:>{_WIDTH}}" if b_no is not None else " " * _WIDTH
    if not color:
        if line.tag is LineTag.CONTEXT:
            return f"{a_field} {b_field}   {line.text}"
        mark = "-" if line.tag is LineTag.DELETE else "+"
        side = a_field if line.tag is LineTag.DELETE else f"      {b_field}"
        return f"{side} {mark} {line.text}"

    dim = DIM if color else ""
    if line.tag is LineTag.CONTEXT:
        return f"{dim}{a_field} {b_field}{RESET}   {line.text}"
    base = RED if line.tag is LineTag.DELETE else GREEN
    mark = line.tag.value
    side = (
        f"{dim}{a_field}{RESET}" + " " * (_WIDTH + 1)
        if line.tag is LineTag.DELETE
        else " " * (_WIDTH + 1) + f"{dim}{b_field}{RESET}"
    )
    inline = (
        (line.inline.prefix_len, line.inline.suffix_len)
        if line.inline is not None
        else None
    )
    return f"{side} {base}{mark}{RESET} {_paint_inline(line.text, base, inline)}"


def render(result: DiffResult, a_label: str, b_label: str, color: bool = True) -> str:
    """Render *result* with ANSI colours and line numbers (empty if identical).

    Non-text modes reuse the plain-text renderers and paint lines by their
    leading marker (``+``/``-``/``~``/``!``/headers).
    """
    if result.identical:
        return ""
    if result.mode != "text":
        from atrain.output import unified

        text = unified.render(result, a_label, b_label)
        return _colorize_lines(text) if color else text
    has_binary = result.source.is_binary or result.target.is_binary
    if not result.hunks and not has_binary:
        return ""
    out: list[str] = []
    if color:
        out.append(f"{BOLD}{CYAN}--- {a_label}{RESET}\n")
        out.append(f"{BOLD}{CYAN}+++ {b_label}{RESET}\n")
    else:
        out.append(f"--- {a_label}\n")
        out.append(f"+++ {b_label}\n")
    if not result.hunks:
        out.append("Binary files differ\n")
        return "".join(out)
    for hunk in result.hunks:
        header = (
            f"@@ -{hunk.a_start + 1},{hunk.a_count} +{hunk.b_start + 1},{hunk.b_count} @@"
        )
        out.append(f"{BOLD}{CYAN}{header}{RESET}\n" if color else f"{header}\n")
        a_no = hunk.a_start + 1
        b_no = hunk.b_start + 1
        for line in hunk.lines:
            if line.tag is LineTag.CONTEXT:
                out.append(_line(line, a_no, b_no, color))
                a_no += 1
                b_no += 1
            elif line.tag is LineTag.DELETE:
                out.append(_line(line, a_no, None, color))
                a_no += 1
            else:
                out.append(_line(line, None, b_no, color))
                b_no += 1
            out.append("\n")
    return "".join(out)
