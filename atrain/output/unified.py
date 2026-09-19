"""Default text presentation for every mode.

For ``text`` results this is a patch-compatible unified diff (works with
``patch`` and ``git apply``).  The other modes render as plain-text
reports through the same entry point so the CLI's default format works
everywhere:

- ``binary`` — per-region hexdump sections
- ``json`` / ``csv`` — path-based change lines (``+``/``-``/``~``)
- ``dir`` — status lines plus per-file unified diffs
"""

from __future__ import annotations

from atrain.core.models import DiffResult, Hunk, LineTag, NodeChange


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
    """Render *result* for the default ``unified`` output format."""
    if result.identical:
        return ""
    if result.mode == "binary":
        return _render_binary(result)
    if result.mode in ("json", "csv"):
        return _render_nodes(result, a_label, b_label)
    if result.mode == "dir":
        return _render_dir(result, a_label, b_label)
    return _render_text(result, a_label, b_label)


def _render_text(result: DiffResult, a_label: str, b_label: str) -> str:
    if not result.hunks:
        if result.source.is_binary or result.target.is_binary:
            return f"Binary files {a_label} and {b_label} differ\n"
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


def _render_binary(result: DiffResult) -> str:
    from atrain.output.hex import region_lines

    if not result.regions:
        return f"Binary files {result.source.path} and {result.target.path} differ\n"
    return "\n".join(region_lines(result))


def _render_nodes(result: DiffResult, a_label: str, b_label: str) -> str:
    out: list[str] = [f"--- {a_label}\n", f"+++ {b_label}\n"]
    for node in result.nodes:
        out.append(_node_line(node))
    return "".join(out)


def _node_line(node: NodeChange) -> str:
    if node.change == "added":
        return f"+ {node.path}: {node.new}  (added)\n"
    if node.change == "removed":
        return f"- {node.path}: {node.old}  (removed)\n"
    detail = f" [{node.detail}]" if node.detail else ""
    return f"~ {node.path}: {node.old} -> {node.new}{detail}\n"


def _render_dir(result: DiffResult, a_label: str, b_label: str) -> str:
    out: list[str] = [f"--- {a_label}/\n", f"+++ {b_label}/\n"]
    marks = {"added": "+", "removed": "-", "modified": "~", "unchanged": " ", "error": "!"}
    for entry in result.entries:
        mark = marks.get(entry.change, "?")
        suffix = f"  ({entry.detail})" if entry.detail else ""
        out.append(f"{mark} {entry.kind:<4} {entry.path}{suffix}\n")
    for rel in sorted(result.children):
        child = result.children[rel]
        if child.hunks:
            out.append(f"\n--- {a_label}/{rel}\n+++ {b_label}/{rel}\n")
            for hunk in child.hunks:
                out.append(hunk_header(hunk))
                out.append("\n")
                for line in hunk.lines:
                    out.append(line.tag.value)
                    out.append(line.text)
                    out.append("\n")
        elif child.regions:
            from atrain.output.hex import region_lines

            out.append(f"\n--- {a_label}/{rel} (binary)\n+++ {b_label}/{rel} (binary)\n")
            out.extend(
                line + "\n"
                for line in region_lines(child, f"{a_label}/{rel}", f"{b_label}/{rel}")
            )
    if result.errors:
        out.append("\nerrors:\n")
        for message in result.errors:
            out.append(f"! {message}\n")
    return "".join(out)


# Re-exported for formatters that classify lines (e.g. color).
LINE_TAGS = frozenset(tag.value for tag in LineTag)
ENTRY_MARKS = {"added": "+", "removed": "-", "modified": "~", "unchanged": " ", "error": "!"}
