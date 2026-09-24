"""Machine-readable JSON output (ROADMAP.md, §5, format ``json``).

Stable, deterministic structure for CI pipelines and downstream tooling:
top-level ``mode``/``identical``/``stats`` plus per-file metadata and the
hunk list.  Field names mirror the model; positions stay 0-based like
:class:`atrain.core.models.Hunk`.
"""

from __future__ import annotations

import json

from atrain import __version__
from atrain.core.models import DiffLine, DiffResult, FileMeta


def _file_json(meta: FileMeta) -> dict[str, object]:
    return {
        "path": meta.path,
        "size": meta.size,
        "digest": meta.digest,
        "encoding": meta.encoding,
        "newline": meta.newline.name if meta.newline else None,
        "binary": meta.is_binary,
    }


def _line_json(line: DiffLine) -> dict[str, object]:
    entry: dict[str, object] = {
        "tag": line.tag.value,
        "text": line.text,
        "newline": line.newline,
    }
    if line.inline is not None:
        entry["inline"] = {
            "prefix": line.inline.prefix_len,
            "suffix": line.inline.suffix_len,
        }
    return entry


def as_dict(result: DiffResult) -> dict[str, object]:
    """Convert *result* into the JSON-serialisable document."""
    doc: dict[str, object] = {
        "tool": "atrain",
        "version": __version__,
        "mode": result.mode,
        "identical": result.identical,
        "stats": {
            "added": result.stats.added,
            "removed": result.stats.removed,
            "hunks": result.stats.hunks,
        },
        "source": _file_json(result.source),
        "target": _file_json(result.target),
        "hunks": [
            {
                "a_start": hunk.a_start,
                "a_count": hunk.a_count,
                "b_start": hunk.b_start,
                "b_count": hunk.b_count,
                "lines": [_line_json(line) for line in hunk.lines],
            }
            for hunk in result.hunks
        ],
    }
    if result.regions:
        doc["regions"] = [
            {
                "a_start": region.a_start,
                "a_end": region.a_end,
                "b_start": region.b_start,
                "b_end": region.b_end,
            }
            for region in result.regions
        ]
    if result.nodes:
        doc["nodes"] = [
            {
                "path": node.path,
                "change": node.change,
                "old": node.old,
                "new": node.new,
                "detail": node.detail,
            }
            for node in result.nodes
        ]
    if result.entries:
        doc["entries"] = [
            {
                "path": entry.path,
                "change": entry.change,
                "kind": entry.kind,
                "detail": entry.detail,
            }
            for entry in result.entries
        ]
    if result.children:
        doc["children"] = {rel: as_dict(child) for rel, child in result.children.items()}
    if result.errors:
        doc["errors"] = list(result.errors)
    return doc


def render(result: DiffResult) -> str:
    """Serialise *result* as pretty-printed JSON (always non-empty)."""
    return json.dumps(as_dict(result), indent=2, ensure_ascii=False) + "\n"
