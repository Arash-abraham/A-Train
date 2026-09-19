"""Semantic comparison for JSON and CSV (ROADMAP.md, §4).

JSON comparison is **value-based and key-order-insensitive**; changes are
reported per JSONPath-style location (``$.a.b[2]``).  Arrays are compared
index-wise (reordering *is* reported as changes — see
IMPROVEMENT_SUGGESTIONS.md for array-matching ideas).

CSV comparison supports a **key column** (by header name or 1-based
index): rows are matched by key and reported as added / removed /
modified with field-level detail.  Without a key, rows are compared by
position.  Duplicate keys keep the first occurrence (documented).

Malformed input raises :class:`ValueError` with a precise message; the
CLI translates that into exit code 2.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from pathlib import Path

from atrain.core.models import DiffResult, FileMeta, NodeChange

PREVIEW_LIMIT = 120
"""Maximum rendered length of a value preview in NodeChange."""


def _preview(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) > PREVIEW_LIMIT:
        text = text[: PREVIEW_LIMIT - 3] + "..."
    return text


def _scalar_equal(a: object, b: object) -> bool:
    """JSON-semantics equality: bool is not 1, 1 == 1.0, exact str."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    return a == b


# ----------------------------------------------------------------- JSON

def _walk_json(a: object, b: object, path: str, nodes: list[NodeChange]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in a.keys() | b.keys():
            child = f"{path}.{key}"
            if key not in b:
                nodes.append(NodeChange(path=child, change="removed", old=_preview(a[key])))
            elif key not in a:
                nodes.append(NodeChange(path=child, change="added", new=_preview(b[key])))
            else:
                _walk_json(a[key], b[key], child, nodes)
        return
    if isinstance(a, list) and isinstance(b, list):
        for index in range(max(len(a), len(b))):
            child = f"{path}[{index}]"
            if index >= len(b):
                nodes.append(NodeChange(path=child, change="removed", old=_preview(a[index])))
            elif index >= len(a):
                nodes.append(NodeChange(path=child, change="added", new=_preview(b[index])))
            else:
                _walk_json(a[index], b[index], child, nodes)
        return
    if not _scalar_equal(a, b):
        nodes.append(
            NodeChange(path=path, change="changed", old=_preview(a), new=_preview(b))
        )


def _finish(
    mode: str, meta_a: FileMeta, meta_b: FileMeta, nodes: list[NodeChange]
) -> DiffResult:
    result = DiffResult(mode=mode, source=meta_a, target=meta_b, identical=False)
    result.nodes = nodes
    result.identical = not nodes
    return result


def diff_json_strings(a_text: str, b_text: str, a_label: str, b_label: str) -> DiffResult:
    """Semantic JSON comparison of two decoded documents."""
    try:
        doc_a = json.loads(a_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{a_label}: invalid JSON: {exc}") from exc
    try:
        doc_b = json.loads(b_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{b_label}: invalid JSON: {exc}") from exc

    meta_a = FileMeta(path=a_label, size=len(a_text.encode("utf-8")), encoding="utf-8")
    meta_b = FileMeta(path=b_label, size=len(b_text.encode("utf-8")), encoding="utf-8")
    nodes: list[NodeChange] = []
    _walk_json(doc_a, doc_b, "$", nodes)
    return _finish("json", meta_a, meta_b, nodes)


def diff_json_files(path_a: Path, path_b: Path, encoding: str | None = None) -> DiffResult:
    """Load two JSON files and compare them semantically."""
    from atrain.core.reader import decode_text, load_bytes

    with load_bytes(path_a) as raw_a:
        text_a, enc_a = decode_text(raw_a.data, encoding)
    with load_bytes(path_b) as raw_b:
        text_b, enc_b = decode_text(raw_b.data, encoding)
    meta_a = FileMeta(path=str(path_a), size=len(text_a.encode("utf-8")), encoding=enc_a)
    meta_b = FileMeta(path=str(path_b), size=len(text_b.encode("utf-8")), encoding=enc_b)
    try:
        doc_a = json.loads(text_a)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path_a}: invalid JSON: {exc}") from exc
    try:
        doc_b = json.loads(text_b)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path_b}: invalid JSON: {exc}") from exc
    nodes: list[NodeChange] = []
    _walk_json(doc_a, doc_b, "$", nodes)
    return _finish("json", meta_a, meta_b, nodes)


# ------------------------------------------------------------------ CSV

def _parse_csv(text: str, label: str) -> list[list[str]]:
    try:
        return list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise ValueError(f"{label}: malformed CSV: {exc}") from exc


def _row_preview(row: list[str]) -> str:
    text = json.dumps(row, ensure_ascii=False)
    if len(text) > PREVIEW_LIMIT:
        text = text[: PREVIEW_LIMIT - 3] + "..."
    return text


def _diff_csv_rows(
    rows_a: list[list[str]], rows_b: list[list[str]], key: str | int | None
) -> list[NodeChange]:
    key_index = _resolve_key_index(key, rows_a[0] if rows_a else [])
    if key_index is None:
        return _diff_csv_positional(rows_a, rows_b)
    return _diff_csv_keyed(
        rows_a, rows_b, key_index, rows_a[0] if rows_a else [], rows_b[0] if rows_b else []
    )


def _resolve_key_index(key: str | int | None, header: list[str]) -> int | None:
    if key is None:
        return None
    if isinstance(key, bool):  # bool is an int subclass — reject explicitly
        raise ValueError(f"invalid key column: {key!r}")
    if isinstance(key, int):
        if not 1 <= key <= len(header):
            raise ValueError(f"key column {key} out of range (1..{len(header)})")
        return key - 1
    if key not in header:
        raise ValueError(f"key column {key!r} not found in header {header}")
    return header.index(key)


def _diff_csv_positional(
    rows_a: list[list[str]], rows_b: list[list[str]]
) -> list[NodeChange]:
    nodes: list[NodeChange] = []
    for index in range(max(len(rows_a), len(rows_b))):
        if index >= len(rows_b):
            nodes.append(
                NodeChange(
                    path=f"row[{index}]", change="removed", old=_row_preview(rows_a[index])
                )
            )
        elif index >= len(rows_a):
            nodes.append(
                NodeChange(
                    path=f"row[{index}]", change="added", new=_row_preview(rows_b[index])
                )
            )
        else:
            for column in range(max(len(rows_a[index]), len(rows_b[index]))):
                cell_a = rows_a[index][column] if column < len(rows_a[index]) else ""
                cell_b = rows_b[index][column] if column < len(rows_b[index]) else ""
                if cell_a != cell_b:
                    nodes.append(
                        NodeChange(
                            path=f"row[{index}].col[{column}]",
                            change="changed",
                            old=cell_a,
                            new=cell_b,
                        )
                    )
    return nodes


def _keyed_rows(
    rows: list[list[str]], key_of: Callable[[list[str]], str]
) -> dict[str, list[str]]:
    """Map key -> first row with that key (duplicates keep the first)."""
    keyed: dict[str, list[str]] = {}
    for row in rows:
        keyed.setdefault(key_of(row), row)
    return keyed


def _diff_csv_keyed(
    rows_a: list[list[str]],
    rows_b: list[list[str]],
    key_index: int,
    header_a: list[str],
    header_b: list[str],
) -> list[NodeChange]:
    nodes: list[NodeChange] = []
    if header_a != header_b:
        nodes.append(
            NodeChange(
                path="header",
                change="changed",
                old=_row_preview(header_a),
                new=_row_preview(header_b),
            )
        )

    def key_of(row: list[str]) -> str:
        return row[key_index] if key_index < len(row) else ""

    map_a = _keyed_rows(rows_a[1:], key_of)
    map_b = _keyed_rows(rows_b[1:], key_of)
    for row_key in sorted(map_a.keys() | map_b.keys()):
        where = f"row[key={row_key}]"
        if row_key not in map_b:
            nodes.append(
                NodeChange(path=where, change="removed", old=_row_preview(map_a[row_key]))
            )
        elif row_key not in map_a:
            nodes.append(
                NodeChange(path=where, change="added", new=_row_preview(map_b[row_key]))
            )
        else:
            row_a, row_b = map_a[row_key], map_b[row_key]
            for column in range(max(len(row_a), len(row_b))):
                cell_a = row_a[column] if column < len(row_a) else ""
                cell_b = row_b[column] if column < len(row_b) else ""
                if cell_a != cell_b:
                    name = header_a[column] if column < len(header_a) else f"col[{column}]"
                    nodes.append(
                        NodeChange(
                            path=f"{where}.{name}",
                            change="changed",
                            old=cell_a,
                            new=cell_b,
                            detail=f"column {name!r}",
                        )
                    )
    return nodes


def _diff_csv_text(
    text_a: str,
    text_b: str,
    meta_a: FileMeta,
    meta_b: FileMeta,
    key: str | int | None,
) -> DiffResult:
    rows_a = _parse_csv(text_a, meta_a.path)
    rows_b = _parse_csv(text_b, meta_b.path)
    return _finish("csv", meta_a, meta_b, _diff_csv_rows(rows_a, rows_b, key))


def diff_csv_strings(
    a_text: str, b_text: str, a_label: str, b_label: str, key: str | int | None = None
) -> DiffResult:
    """CSV comparison of two decoded texts."""
    meta_a = FileMeta(path=a_label, size=len(a_text.encode("utf-8")), encoding="utf-8")
    meta_b = FileMeta(path=b_label, size=len(b_text.encode("utf-8")), encoding="utf-8")
    return _diff_csv_text(a_text, b_text, meta_a, meta_b, key)


def diff_csv_files(
    path_a: Path, path_b: Path, key: str | int | None = None, encoding: str | None = None
) -> DiffResult:
    """Load two CSV files and compare their records."""
    from atrain.core.reader import decode_text, load_bytes

    with load_bytes(path_a) as raw_a:
        text_a, enc_a = decode_text(raw_a.data, encoding)
    with load_bytes(path_b) as raw_b:
        text_b, enc_b = decode_text(raw_b.data, encoding)
    meta_a = FileMeta(path=str(path_a), size=len(text_a.encode("utf-8")), encoding=enc_a)
    meta_b = FileMeta(path=str(path_b), size=len(text_b.encode("utf-8")), encoding=enc_b)
    return _diff_csv_text(text_a, text_b, meta_a, meta_b, key)
