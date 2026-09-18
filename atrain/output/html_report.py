"""Standalone HTML report (ROADMAP.md, §5, format ``html``).

Self-contained: a single document with embedded CSS, no JavaScript, no
external resources — safe to open offline or attach to an e-mail.  All
file content is HTML-escaped; the changed middle of refined line pairs is
wrapped in ``<mark>``.
"""

from __future__ import annotations

from html import escape

from atrain.core.models import DiffLine, DiffResult, LineTag

_CSS = """\
body { font-family: "SF Mono", Consolas, "DejaVu Sans Mono", monospace;
       margin: 2rem auto; max-width: 75rem; color: #1f2328; background: #fff; }
h1 { font-size: 1.3rem; } h2 { font-size: 1.05rem; margin-top: 1.5rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { border: 1px solid #d0d7de; padding: 0.15rem 0.5rem; text-align: left; }
td.ln { text-align: right; color: #59636e; width: 3.5em; user-select: none; }
td.tag { width: 1em; text-align: center; }
tr.ctx { background: transparent; } tr.del { background: #ffebe9; }
tr.ins { background: #dafbe1; }
td.text { white-space: pre-wrap; word-break: break-all; }
mark { background: #ffd54f; border-radius: 2px; }
meta-table td { border: none; padding: 0.1rem 1rem 0.1rem 0; }
.notice { background: #fff8c5; border: 1px solid #d4a72c; padding: 0.5rem 1rem; }
"""


def _line_cell(line: DiffLine) -> str:
    text = escape(line.text)
    if line.inline is not None:
        prefix, suffix = line.inline.prefix_len, line.inline.suffix_len
        middle_end = len(line.text) - suffix
        if middle_end > prefix:
            # Escape each segment separately to keep offsets in text space.
            text = (
                escape(line.text[:prefix])
                + "<mark>"
                + escape(line.text[prefix:middle_end])
                + "</mark>"
                + escape(line.text[middle_end:])
            )
    return text


def _meta_rows(result: DiffResult) -> str:
    rows: list[str] = []
    for label, meta in (("source", result.source), ("target", result.target)):
        newline = meta.newline.name if meta.newline is not None else "—"
        digest = meta.digest or "—"
        encoding = meta.encoding or "—"
        rows.append(
            "<tr>"
            f"<td>{escape(label)}</td><td>{escape(meta.path)}</td>"
            f"<td>{meta.size}</td><td><code>{escape(digest)}</code></td>"
            f"<td>{escape(encoding)}</td><td>{newline}</td>"
            f"<td>{'yes' if meta.is_binary else 'no'}</td>"
            "</tr>"
        )
    return "".join(rows)


def render(result: DiffResult, a_label: str, b_label: str) -> str:
    """Render *result* as a standalone HTML document (always non-empty)."""
    parts: list[str] = [
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n",
        "<title>A-Train report</title>\n",
        f"<style>{_CSS}</style>\n</head>\n<body>\n",
        "<h1>A-Train comparison report</h1>\n",
        "<table class=\"meta-table\">\n"
        "<tr><th></th><th>path</th><th>size</th><th>digest (BLAKE2b-128)</th>"
        "<th>encoding</th><th>newlines</th><th>binary</th></tr>\n",
        _meta_rows(result),
        "</table>\n",
    ]
    if result.identical:
        parts.append("<p class=\"notice\">Files are identical "
                     "(hash-based early exit, no diff performed).</p>\n")
    elif not result.hunks and (result.source.is_binary or result.target.is_binary):
        parts.append("<p class=\"notice\">Binary files differ "
                     "(content not rendered).</p>\n")
    else:
        stats = result.stats
        parts.append(
            f"<p>{stats.hunks} hunk(s): <span style=\"color:#cf222e\">"
            f"{stats.removed} removed</span>, <span style=\"color:#1a7f37\">"
            f"{stats.added} added</span></p>\n"
        )
        parts.append("<h2>Changes</h2>\n<table>\n")
        for hunk in result.hunks:
            header = (
                f"@@ -{hunk.a_start + 1},{hunk.a_count} "
                f"+{hunk.b_start + 1},{hunk.b_count} @@"
            )
            parts.append(
                f"<tr><td class=\"tag\" colspan=\"4\"><code>{escape(header)}</code></td></tr>\n"
            )
            a_no = hunk.a_start + 1
            b_no = hunk.b_start + 1
            for line in hunk.lines:
                cls = {LineTag.CONTEXT: "ctx", LineTag.DELETE: "del", LineTag.INSERT: "ins"}[
                    line.tag
                ]
                left = (
                    f'<td class="ln">{a_no}</td>'
                    if line.tag is not LineTag.INSERT
                    else '<td class="ln"></td>'
                )
                right = (
                    f'<td class="ln">{b_no}</td>'
                    if line.tag is not LineTag.DELETE
                    else '<td class="ln"></td>'
                )
                mark = escape(line.tag.value)
                parts.append(
                    f"<tr class=\"{cls}\">{left}{right}"
                    f"<td class=\"tag\">{mark}</td>"
                    f"<td class=\"text\">{_line_cell(line) or ' '}</td></tr>\n"
                )
                if line.tag is LineTag.CONTEXT:
                    a_no += 1
                    b_no += 1
                elif line.tag is LineTag.DELETE:
                    a_no += 1
                else:
                    b_no += 1
        parts.append("</table>\n")
    parts.append("</body>\n</html>\n")
    return "".join(parts)
