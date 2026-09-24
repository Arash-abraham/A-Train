"""Standalone HTML report (ROADMAP.md, §5, format ``html``).

Self-contained: a single document with embedded CSS, no JavaScript, no
external resources — safe to open offline or attach to an e-mail.  All
file content is HTML-escaped; the changed middle of refined line pairs is
wrapped in ``<mark>``.

Layout
------
- a header naming both inputs, the comparison mode and an overall status;
- summary cards (added / removed / hunks or the mode's own counters) with a
  proportional diff-stat bar;
- side-by-side metadata cards for the source and target files;
- the mode-specific body (text hunks, binary regions, structured changes,
  or a directory listing with collapsible per-file diffs);
- an errors panel when the engine reported problems.

The palette follows the user's light/dark preference via
``prefers-color-scheme`` and has a dedicated print stylesheet.
"""

from __future__ import annotations

from collections import Counter
from html import escape

from atrain import __version__
from atrain.core.models import DiffLine, DiffResult, FileMeta, Hunk, LineTag
from atrain.output.unified import hunk_header

_CSS = """\
:root {
  color-scheme: light dark;
  --bg: #f6f8fa; --surface: #ffffff; --surface-2: #f6f8fa; --border: #d0d7de;
  --text: #1f2328; --muted: #59636e; --accent: #0969da; --accent-soft: #ddf4ff;
  --add-bg: #e6ffec; --add-ln: #ccffd8; --add-mark: #abf2bc; --add-fg: #1a7f37;
  --del-bg: #ffebe9; --del-ln: #ffd7d5; --del-mark: #ff818266; --del-fg: #cf222e;
  --chg-bg: #fff8c5; --chg-fg: #9a6700;
  --hunk-bg: #ddf4ff; --hunk-fg: #0550ae;
  --shadow: 0 1px 3px rgba(31, 35, 40, .08), 0 1px 0 rgba(31, 35, 40, .04);
  --radius: 10px;
  --mono: ui-monospace, "SF Mono", "Cascadia Code", Consolas, "DejaVu Sans Mono", monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial,
          sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --surface: #151b23; --surface-2: #0d1117; --border: #30363d;
    --text: #e6edf3; --muted: #9198a1; --accent: #4493f8; --accent-soft: #121d2f;
    --add-bg: #12261e; --add-ln: #1b4721; --add-mark: #2ea04366; --add-fg: #3fb950;
    --del-bg: #25171c; --del-ln: #542426; --del-mark: #f8514966; --del-fg: #f85149;
    --chg-bg: #2e2a1a; --chg-fg: #d29922;
    --hunk-bg: #121d2f; --hunk-fg: #79c0ff;
    --shadow: 0 0 0 1px rgba(240, 246, 252, .03);
  }
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body { margin: 0; padding: 2rem 1.25rem 3rem; color: var(--text); background: var(--bg);
       font: 14px/1.5 var(--sans); }
.wrap { max-width: 78rem; margin: 0 auto; }
code, .mono { font-family: var(--mono); font-size: 12.5px; }
h2 { font-size: 1rem; margin: 2rem 0 .75rem; display: flex; align-items: center; gap: .5rem; }
h2 .count { font-weight: 500; color: var(--muted); font-size: .85rem; }

/* ---- header ---- */
.hero { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
        gap: 1rem; margin-bottom: 1.5rem; }
.brand { display: flex; align-items: center; gap: .85rem; }
.logo { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center;
        background: linear-gradient(135deg, #0969da, #8250df); color: #fff;
        font-weight: 800; font-size: 1.1rem; letter-spacing: -.5px;
        box-shadow: 0 4px 14px rgba(9, 105, 218, .35); }
.brand h1 { margin: 0; font-size: 1.35rem; line-height: 1.2; }
.brand .sub { color: var(--muted); font-size: .85rem; }
.files { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-top: .3rem; }
.files code { background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
              padding: .1rem .45rem; overflow-wrap: anywhere; }
.files .arrow { color: var(--muted); }
.pill { display: inline-flex; align-items: center; gap: .4rem; border-radius: 999px;
        padding: .3rem .8rem; font-weight: 600; font-size: .85rem; border: 1px solid; }
.pill .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.pill.same { color: var(--add-fg); background: var(--add-bg); border-color: var(--add-fg); }
.pill.diff { color: var(--chg-fg); background: var(--chg-bg); border-color: var(--chg-fg); }
.pill.err { color: var(--del-fg); background: var(--del-bg); border-color: var(--del-fg); }
.tags { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
.tag-mode { font-size: .75rem; text-transform: uppercase; letter-spacing: .06em;
            color: var(--accent); background: var(--accent-soft); border-radius: 6px;
            padding: .2rem .55rem; font-weight: 700; }

/* ---- cards ---- */
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius); box-shadow: var(--shadow); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
         gap: .75rem; }
.stat { padding: .9rem 1.1rem; }
.stat .label { color: var(--muted); font-size: .75rem; text-transform: uppercase;
               letter-spacing: .06em; font-weight: 600; }
.stat .value { font-size: 1.6rem; font-weight: 700; line-height: 1.2; margin-top: .15rem;
               font-variant-numeric: tabular-nums; }
.stat.add .value { color: var(--add-fg); } .stat.del .value { color: var(--del-fg); }
.stat.chg .value { color: var(--chg-fg); }
.bar { display: flex; height: 8px; border-radius: 999px; overflow: hidden;
       background: var(--surface-2); border: 1px solid var(--border); margin-top: .75rem; }
.bar .a { background: var(--add-fg); } .bar .d { background: var(--del-fg); }

.meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr));
        gap: .75rem; margin-top: .75rem; }
.meta .card { padding: .9rem 1.1rem; }
.meta .role { display: flex; align-items: center; gap: .5rem; font-weight: 700;
              margin-bottom: .5rem; }
.meta .role .sign { width: 22px; height: 22px; border-radius: 6px; display: grid;
                    place-items: center; font-family: var(--mono); font-weight: 700; }
.meta .src .sign { background: var(--del-bg); color: var(--del-fg); }
.meta .dst .sign { background: var(--add-bg); color: var(--add-fg); }
.meta .path { overflow-wrap: anywhere; font-weight: 400; }
dl.kv { display: grid; grid-template-columns: max-content 1fr; gap: .25rem 1rem; margin: 0; }
dl.kv dt { color: var(--muted); }
dl.kv dd { margin: 0; overflow-wrap: anywhere; }
.chip { display: inline-block; border-radius: 6px; padding: 0 .4rem; font-size: .8rem;
        background: var(--surface-2); border: 1px solid var(--border); }

/* ---- notices ---- */
.notice { display: flex; gap: .75rem; align-items: flex-start; padding: 1rem 1.1rem;
          border-radius: var(--radius); border: 1px solid; margin-top: 1rem; }
.notice .icon { font-weight: 800; font-size: 1.1rem; line-height: 1.3; }
.notice.ok { background: var(--add-bg); border-color: var(--add-fg); color: var(--text); }
.notice.ok .icon { color: var(--add-fg); }
.notice.info { background: var(--chg-bg); border-color: var(--chg-fg); }
.notice.info .icon { color: var(--chg-fg); }
.notice.error { background: var(--del-bg); border-color: var(--del-fg); }
.notice.error .icon { color: var(--del-fg); }
.notice ul { margin: .25rem 0 0; padding-left: 1.1rem; }

/* ---- diff tables ---- */
.file { overflow: hidden; margin-bottom: 1rem; }
.file-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem;
             padding: .6rem 1rem; background: var(--surface-2);
             border-bottom: 1px solid var(--border); }
.file-head .name { font-weight: 600; overflow-wrap: anywhere; }
.file-head .mini { color: var(--muted); font-size: .8rem; white-space: nowrap; }
.mini .a { color: var(--add-fg); font-weight: 600; }
.mini .d { color: var(--del-fg); font-weight: 600; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
table.diff { font-family: var(--mono); font-size: 12.5px; line-height: 20px;
             table-layout: fixed; }
table.diff col.ln { width: 4.2em; } table.diff col.sg { width: 1.6em; }
table.diff td { padding: 0 .5rem; vertical-align: top; border: 0; }
td.ln { text-align: right; color: var(--muted); user-select: none; opacity: .85; }
td.sg { text-align: center; user-select: none; color: var(--muted); padding: 0; }
td.text { white-space: pre-wrap; overflow-wrap: anywhere; tab-size: 4; }
tr.del td { background: var(--del-bg); } tr.del td.ln { background: var(--del-ln); }
tr.ins td { background: var(--add-bg); } tr.ins td.ln { background: var(--add-ln); }
tr.del td.sg { color: var(--del-fg); } tr.ins td.sg { color: var(--add-fg); }
tr.hunk td { background: var(--hunk-bg); color: var(--hunk-fg); padding: .25rem .75rem; }
tr.hunk + tr td { padding-top: 2px; }
tr.gap td { height: .5rem; background: var(--surface-2); }
tr.eof td.text { color: var(--muted); font-style: italic; }
mark { color: inherit; border-radius: 3px; padding: 0 1px; }
tr.del mark { background: var(--del-mark); } tr.ins mark { background: var(--add-mark); }
.empty { color: var(--muted); }

/* ---- generic data tables (binary / structured / dir) ---- */
table.grid { font-size: 13px; }
table.grid th { text-align: left; font-weight: 600; color: var(--muted); font-size: .75rem;
                text-transform: uppercase; letter-spacing: .05em; padding: .55rem .9rem;
                background: var(--surface-2); border-bottom: 1px solid var(--border); }
table.grid td { padding: .45rem .9rem; border-bottom: 1px solid var(--border);
                vertical-align: top; }
table.grid tr:last-child td { border-bottom: 0; }
table.grid td.text { font-family: var(--mono); font-size: 12.5px; }
table.grid td.old { color: var(--del-fg); } table.grid td.new { color: var(--add-fg); }
.badge { display: inline-block; min-width: 5.5rem; text-align: center; border-radius: 999px;
         padding: .05rem .6rem; font-size: .75rem; font-weight: 600; border: 1px solid; }
.badge.ins { color: var(--add-fg); background: var(--add-bg); border-color: var(--add-fg); }
.badge.del { color: var(--del-fg); background: var(--del-bg); border-color: var(--del-fg); }
.badge.chg { color: var(--chg-fg); background: var(--chg-bg); border-color: var(--chg-fg); }
.badge.same { color: var(--muted); background: var(--surface-2); border-color: var(--border); }
tr.same td { color: var(--muted); }

details.file > summary { list-style: none; cursor: pointer; }
details.file > summary::-webkit-details-marker { display: none; }
details.file > summary .name::before { content: "\\25B8"; display: inline-block;
  margin-right: .5rem; color: var(--muted); transition: transform .15s; }
details.file[open] > summary .name::before { transform: rotate(90deg); }
details.file:not([open]) > summary { border-bottom: 0; }

footer { margin-top: 2.5rem; color: var(--muted); font-size: .8rem; text-align: center; }

@media print {
  body { background: #fff; padding: 0; }
  .card { box-shadow: none; }
  .file { break-inside: avoid-page; }
  details.file > summary .name::before { display: none; }
}
"""


# ------------------------------------------------------------------ helpers

def _plural(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count:,} {word}"


def _human_size(size: int) -> str:
    units = ("bytes", "KiB", "MiB", "GiB", "TiB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "bytes":
                return f"{size:,} bytes"
            return f"{value:.1f} {unit} ({size:,} bytes)"
        value /= 1024
    raise AssertionError("unreachable")  # pragma: no cover


def _diffstat_bar(added: int, removed: int) -> str:
    total = added + removed
    if total == 0:
        return ""
    add_pct = added * 100 / total
    return (
        '<div class="bar" role="img" '
        f'aria-label="{added} added, {removed} removed">'
        f'<span class="a" style="width:{add_pct:.2f}%"></span>'
        f'<span class="d" style="width:{100 - add_pct:.2f}%"></span></div>'
    )


def _stat_card(label: str, value: object, cls: str = "") -> str:
    return (
        f'<div class="card stat {cls}"><div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(str(value))}</div></div>'
    )


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


# ------------------------------------------------------------------ sections

def _meta_card(role: str, sign: str, cls: str, meta: FileMeta) -> str:
    newline = meta.newline.name if meta.newline is not None else "—"
    digest = f"<code>{escape(meta.digest)}</code>" if meta.digest else "—"
    encoding = escape(meta.encoding) if meta.encoding else "—"
    kind = "binary" if meta.is_binary else "text"
    return (
        f'<div class="card {cls}">'
        f'<div class="role"><span class="sign">{sign}</span>{escape(role)} '
        f'<code class="path">{escape(meta.path)}</code></div>'
        '<dl class="kv">'
        f"<dt>Size</dt><dd>{escape(_human_size(meta.size))}</dd>"
        f'<dt>Type</dt><dd><span class="chip">{kind}</span></dd>'
        f'<dt>Encoding</dt><dd><span class="chip">{encoding}</span></dd>'
        f'<dt>Newlines</dt><dd><span class="chip">{newline}</span></dd>'
        f"<dt>BLAKE2b-128</dt><dd>{digest}</dd>"
        "</dl></div>"
    )


def _summary(result: DiffResult) -> str:
    cards: list[str] = []
    bar = ""
    if result.mode == "binary":
        total = sum(
            max(r.a_end - r.a_start, r.b_end - r.b_start) for r in result.regions
        )
        cards.append(_stat_card("Differing regions", f"{len(result.regions):,}", "chg"))
        cards.append(_stat_card("Bytes affected", f"{total:,}", "chg"))
        cards.append(_stat_card("Size delta",
                                f"{result.target.size - result.source.size:+,}"))
    elif result.mode in ("json", "csv"):
        counts = Counter(node.change for node in result.nodes)
        cards.append(_stat_card("Added", f"{counts['added']:,}", "add"))
        cards.append(_stat_card("Removed", f"{counts['removed']:,}", "del"))
        cards.append(_stat_card("Changed", f"{counts['changed']:,}", "chg"))
        bar = _diffstat_bar(counts["added"], counts["removed"])
    elif result.mode == "dir":
        counts = Counter(entry.change for entry in result.entries)
        cards.append(_stat_card("Added", f"{counts['added']:,}", "add"))
        cards.append(_stat_card("Removed", f"{counts['removed']:,}", "del"))
        cards.append(_stat_card("Modified", f"{counts['modified']:,}", "chg"))
        cards.append(_stat_card("Unchanged", f"{counts['unchanged']:,}"))
        if counts["error"]:
            cards.append(_stat_card("Errors", f"{counts['error']:,}", "del"))
    else:
        stats = result.stats
        cards.append(_stat_card("Lines added", f"+{stats.added:,}", "add"))
        cards.append(_stat_card("Lines removed", f"-{stats.removed:,}", "del"))
        cards.append(_stat_card("Hunks", f"{stats.hunks:,}"))
        bar = _diffstat_bar(stats.added, stats.removed)
    return f'<div class="stats">{"".join(cards)}</div>{bar}\n'


def _notice(kind: str, icon: str, body: str) -> str:
    return (
        f'<div class="notice {kind}"><span class="icon">{icon}</span>'
        f"<div>{body}</div></div>\n"
    )


def render(result: DiffResult, a_label: str, b_label: str) -> str:
    """Render *result* as a standalone HTML document (always non-empty)."""
    if result.errors and not result.identical:
        pill = '<span class="pill err"><span class="dot"></span>Completed with errors</span>'
    elif result.identical:
        pill = '<span class="pill same"><span class="dot"></span>Identical</span>'
    else:
        pill = '<span class="pill diff"><span class="dot"></span>Differences found</span>'

    title = f"A-Train · {a_label} ↔ {b_label}"
    parts: list[str] = [
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n",
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        '<meta name="generator" content="A-Train ' + escape(__version__) + '">\n',
        f"<title>{escape(title)}</title>\n",
        f"<style>\n{_CSS}</style>\n</head>\n<body>\n<div class=\"wrap\">\n",
        '<header class="hero"><div class="brand"><div class="logo">A</div><div>',
        "<h1>A-Train comparison report</h1>",
        f'<div class="files"><code>{escape(a_label)}</code>'
        f'<span class="arrow">→</span><code>{escape(b_label)}</code></div>',
        "</div></div>",
        f'<div class="tags"><span class="tag-mode">{escape(result.mode)}</span>{pill}</div>',
        "</header>\n",
    ]

    if not result.identical:
        parts.append(_summary(result))

    parts.append('<div class="meta">')
    parts.append(_meta_card("Source", "−", "src", result.source))
    parts.append(_meta_card("Target", "+", "dst", result.target))
    parts.append("</div>\n")

    if result.identical:
        parts.append(_notice(
            "ok", "✓",
            "<strong>Files are identical</strong> (hash-based early exit, "
            "no diff performed).",
        ))
    elif result.mode == "binary":
        parts.append(_binary_html(result))
    elif result.mode in ("json", "csv"):
        parts.append(_nodes_html(result))
    elif result.mode == "dir":
        parts.append(_dir_html(result))
    elif not result.hunks and (result.source.is_binary or result.target.is_binary):
        parts.append(_notice(
            "info", "!",
            "<strong>Binary files differ</strong> (content not rendered). "
            "Use <code>--mode binary</code> for a byte-level comparison.",
        ))
    elif not result.hunks:
        parts.append(_notice(
            "ok", "✓",
            "<strong>No differences to show</strong> with the current "
            "comparison options.",
        ))
    else:
        parts.append(
            f'<h2>Changes <span class="count">{_plural(result.stats.hunks, "hunk")}'
            "</span></h2>\n"
        )
        parts.append(_file_block(b_label, result.hunks, result.stats.added,
                                 result.stats.removed))

    if result.errors:
        items = "".join(f"<li><code>{escape(m)}</code></li>" for m in result.errors)
        parts.append(_notice(
            "error", "✕",
            f"<strong>{_plural(len(result.errors), 'error')}</strong><ul>{items}</ul>",
        ))

    parts.append(
        f"<footer>Generated by A-Train {escape(__version__)} · "
        "self-contained report, no external resources</footer>\n"
    )
    parts.append("</div>\n</body>\n</html>\n")
    return "".join(parts)


# ------------------------------------------------------------------ text

def _file_block(
    name: str,
    hunks: list[Hunk],
    added: int,
    removed: int,
    *,
    collapsible: bool = False,
) -> str:
    mini = (
        f'<span class="mini"><span class="a">+{added:,}</span> '
        f'<span class="d">−{removed:,}</span> · {_plural(len(hunks), "hunk")}</span>'
    )
    head = f'<span class="name"><code>{escape(name)}</code></span>{mini}'
    body = f'<div class="scroll">{_hunks_table(hunks)}</div>'
    if collapsible:
        return (
            f'<details class="card file" open><summary class="file-head">{head}</summary>'
            f"{body}</details>\n"
        )
    return f'<section class="card file"><div class="file-head">{head}</div>{body}</section>\n'


def _hunks_table(hunks: list[Hunk]) -> str:
    parts: list[str] = [
        '<table class="diff"><colgroup><col class="ln"><col class="ln">'
        '<col class="sg"><col></colgroup>\n'
    ]
    classes = {LineTag.CONTEXT: "ctx", LineTag.DELETE: "del", LineTag.INSERT: "ins"}
    signs = {LineTag.CONTEXT: " ", LineTag.DELETE: "−", LineTag.INSERT: "+"}
    for index, hunk in enumerate(hunks):
        if index:
            parts.append('<tr class="gap"><td colspan="4"></td></tr>\n')
        parts.append(
            f'<tr class="hunk"><td colspan="4">{escape(hunk_header(hunk))}</td></tr>\n'
        )
        a_no = hunk.a_start + 1
        b_no = hunk.b_start + 1
        for line in hunk.lines:
            cls = classes[line.tag]
            left = a_no if line.tag is not LineTag.INSERT else ""
            right = b_no if line.tag is not LineTag.DELETE else ""
            text = _line_cell(line) or " "
            parts.append(
                f'<tr class="{cls}"><td class="ln">{left}</td><td class="ln">{right}</td>'
                f'<td class="sg">{signs[line.tag]}</td>'
                f'<td class="text">{text}</td></tr>\n'
            )
            if not line.newline:
                parts.append(
                    '<tr class="eof"><td class="ln"></td><td class="ln"></td>'
                    '<td class="sg"></td>'
                    '<td class="text">\\ No newline at end of file</td></tr>\n'
                )
            if line.tag is LineTag.CONTEXT:
                a_no += 1
                b_no += 1
            elif line.tag is LineTag.DELETE:
                a_no += 1
            else:
                b_no += 1
    parts.append("</table>")
    return "".join(parts)


# ------------------------------------------------------------------ binary

def _binary_html(result: DiffResult) -> str:
    from pathlib import Path

    from atrain.core.reader import load_bytes

    parts: list[str] = [
        f'<h2>Differing regions <span class="count">'
        f"{_plural(len(result.regions), 'region')}</span></h2>\n",
        '<section class="card file"><div class="scroll"><table class="grid">\n',
        "<tr><th>Offset (source)</th><th>Offset (target)</th><th>Size</th>"
        "<th>Source bytes</th><th>Target bytes</th></tr>\n",
    ]
    with load_bytes(Path(result.source.path)) as raw_a, load_bytes(
        Path(result.target.path)
    ) as raw_b:
        for region in result.regions:
            size = max(region.a_end - region.a_start, region.b_end - region.b_start)
            preview_a = escape(_hex_preview(raw_a.data, region.a_start, region.a_end))
            preview_b = escape(_hex_preview(raw_b.data, region.b_start, region.b_end))
            parts.append(
                f"<tr><td><code>0x{region.a_start:08x}</code></td>"
                f"<td><code>0x{region.b_start:08x}</code></td>"
                f"<td>{_plural(size, 'byte')}</td>"
                f'<td class="text old">{preview_a or "<span class=empty>(none)</span>"}</td>'
                f'<td class="text new">{preview_b or "<span class=empty>(none)</span>"}</td>'
                "</tr>\n"
            )
    parts.append("</table></div></section>\n")
    return "".join(parts)


def _hex_preview(data: bytes | memoryview, start: int, end: int, limit: int = 24) -> str:
    chunk = bytes(data[start : min(end, start + limit)])
    text = chunk.hex(" ")
    if end - start > limit:
        text += " …"
    return text


# ------------------------------------------------------------------ structured

def _nodes_html(result: DiffResult) -> str:
    labels = {"added": ("ins", "added"), "removed": ("del", "removed"),
              "changed": ("chg", "changed")}
    parts: list[str] = [
        f'<h2>Changes <span class="count">{_plural(len(result.nodes), "change")}'
        "</span></h2>\n",
        '<section class="card file"><div class="scroll"><table class="grid">\n',
        "<tr><th>Change</th><th>Path</th><th>Old value</th><th>New value</th>"
        "<th>Detail</th></tr>\n",
    ]
    for node in result.nodes:
        cls, label = labels.get(node.change, ("same", node.change))
        old = escape(node.old) if node.old is not None else '<span class="empty">—</span>'
        new = escape(node.new) if node.new is not None else '<span class="empty">—</span>'
        parts.append(
            f'<tr class="{cls}"><td><span class="badge {cls}">{escape(label)}</span></td>'
            f'<td class="text">{escape(node.path)}</td>'
            f'<td class="text old">{old}</td>'
            f'<td class="text new">{new}</td>'
            f"<td>{escape(node.detail)}</td></tr>\n"
        )
    parts.append("</table></div></section>\n")
    return "".join(parts)


# ------------------------------------------------------------------ directory

def _dir_html(result: DiffResult) -> str:
    labels = {
        "added": ("ins", "added"),
        "removed": ("del", "removed"),
        "modified": ("chg", "modified"),
        "unchanged": ("same", "unchanged"),
        "error": ("del", "error"),
    }
    parts: list[str] = [
        f'<h2>Entries <span class="count">{_plural(len(result.entries), "entry", "entries")}'
        "</span></h2>\n",
        '<section class="card file"><div class="scroll"><table class="grid">\n',
        "<tr><th>Status</th><th>Kind</th><th>Path</th><th>Detail</th></tr>\n",
    ]
    for entry in result.entries:
        cls, label = labels.get(entry.change, ("same", entry.change))
        path = escape(entry.path) + ("/" if entry.kind == "dir" else "")
        parts.append(
            f'<tr class="{cls}"><td><span class="badge {cls}">{escape(label)}</span></td>'
            f"<td>{escape(entry.kind)}</td>"
            f'<td class="text">{path}</td>'
            f"<td>{escape(entry.detail)}</td></tr>\n"
        )
    parts.append("</table></div></section>\n")

    if result.children:
        parts.append(
            f'<h2>File diffs <span class="count">'
            f"{_plural(len(result.children), 'file')}</span></h2>\n"
        )
    for rel in sorted(result.children):
        child = result.children[rel]
        if child.hunks:
            parts.append(_file_block(rel, child.hunks, child.stats.added,
                                     child.stats.removed, collapsible=True))
        else:
            reason = (
                "Binary files differ (content not rendered)."
                if child.source.is_binary or child.target.is_binary
                else "No textual diff available."
            )
            parts.append(
                f'<section class="card file"><div class="file-head"><span class="name">'
                f"<code>{escape(rel)}</code></span></div>"
                f'<div class="notice info" style="margin:0;border:0;border-radius:0">'
                f'<span class="icon">!</span><div>{reason}</div></div></section>\n'
            )
    return "".join(parts)
