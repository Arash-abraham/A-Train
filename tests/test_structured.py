"""Tests for semantic JSON and CSV comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atrain.core.diff_structured import (
    diff_csv_strings,
    diff_json_files,
    diff_json_strings,
)


def _nodes_by_path(result: object) -> dict:
    return {node.path: node for node in result.nodes}  # type: ignore[attr-defined]


# ------------------------------------------------------------------ JSON

def test_reordered_keys_are_identical() -> None:
    result = diff_json_strings('{"a": 1, "b": 2}', '{"b": 2, "a": 1}', "a", "b")
    assert result.identical
    assert result.nodes == []


def test_added_removed_changed_nested_paths() -> None:
    a = '{"keep": 1, "gone": [1, 2], "deep": {"x": "old"}}'
    b = '{"keep": 1, "new": true, "deep": {"x": "new"}}'
    result = diff_json_strings(a, b, "a", "b")
    nodes = _nodes_by_path(result)
    # Removing key "gone" reports the whole subtree as one removal.
    assert set(nodes) == {"$.gone", "$.new", "$.deep.x"}
    assert nodes["$.gone"].change == "removed"
    assert nodes["$.gone"].old == "[1, 2]"
    assert nodes["$.new"].change == "added" and nodes["$.new"].new == "true"
    assert nodes["$.deep.x"].change == "changed"
    assert nodes["$.deep.x"].old == '"old"' and nodes["$.deep.x"].new == '"new"'


def test_array_index_changes() -> None:
    result = diff_json_strings("[1, 2, 3]", "[1, 5, 3, 4]", "a", "b")
    nodes = _nodes_by_path(result)
    assert nodes["$[1]"].change == "changed"
    assert nodes["$[3]"].change == "added"


def test_numeric_and_type_semantics() -> None:
    assert diff_json_strings("1", "1.0", "a", "b").identical  # numeric equality
    assert not diff_json_strings("1", "true", "a", "b").identical  # bool ≠ 1
    assert not diff_json_strings('"1"', "1", "a", "b").identical  # str ≠ int
    assert diff_json_strings("null", "null", "a", "b").identical


def test_invalid_json_raises_value_error_with_label() -> None:
    with pytest.raises(ValueError, match="bad.json"):
        diff_json_strings('{"a":', "", "bad.json", "b.json")


def test_unicode_values(tmp_path: Path) -> None:
    pa = tmp_path / "a.json"
    pb = tmp_path / "b.json"
    pa.write_text('{"نام": "آرش"}', encoding="utf-8")
    pb.write_text('{"نام": "سارا"}', encoding="utf-8")
    result = diff_json_files(pa, pb)
    node = result.nodes[0]
    assert node.change == "changed"
    assert "آرش" in node.old and "سارا" in node.new


def test_json_identical_documents_early_semantics(tmp_path: Path) -> None:
    pa = tmp_path / "a.json"
    pb = tmp_path / "b.json"
    pa.write_text('{"x": [1, {"y": null}]}', encoding="utf-8")
    pb.write_text('{ "x": [1, {"y": null}] }', encoding="utf-8")  # whitespace differs
    result = diff_json_files(pa, pb)
    assert result.identical


# ------------------------------------------------------------------- CSV

def test_csv_positional_changes() -> None:
    result = diff_csv_strings("h1,h2\na,b\nc,d\n", "h1,h2\na,B\nc,d\n", "a", "b")
    nodes = _nodes_by_path(result)
    assert nodes["row[1].col[1]"].change == "changed"
    assert nodes["row[1].col[1]"].old == "b" and nodes["row[1].col[1]"].new == "B"


def test_csv_keyed_added_removed_modified() -> None:
    a = "id,name,qty\n1,foo,2\n2,bar,5\n"
    b = "id,name,qty\n1,foo,3\n3,baz,9\n"
    result = diff_csv_strings(a, b, "a", "b", key="id")
    nodes = _nodes_by_path(result)
    assert nodes["row[key=1].qty"].change == "changed"
    assert nodes["row[key=2]"].change == "removed"
    assert nodes["row[key=3]"].change == "added"


def test_csv_key_by_index() -> None:
    a = "id,name\n1,x\n2,y\n"
    b = "id,name\n1,x\n2,z\n"
    result = diff_csv_strings(a, b, "a", "b", key=1)
    nodes = _nodes_by_path(result)
    assert nodes["row[key=2].name"].change == "changed"


def test_csv_duplicate_keys_keep_first(tmp_path: Path) -> None:
    a = "id,v\n1,first\n1,dup\n"
    b = "id,v\n1,changed\n"
    result = diff_csv_strings(a, b, "a", "b", key="id")
    nodes = _nodes_by_path(result)
    # First occurrence (v=first) is authoritative.
    assert nodes["row[key=1].v"].old == "first"
    assert nodes["row[key=1].v"].new == "changed"


def test_csv_key_column_not_found() -> None:
    with pytest.raises(ValueError, match="not found"):
        diff_csv_strings("a,b\n", "a,b\n", "a", "b", key="nope")


def test_csv_key_index_out_of_range() -> None:
    with pytest.raises(ValueError, match="out of range"):
        diff_csv_strings("a\n", "a\n", "a", "b", key=5)


def test_csv_reordered_rows_with_keys_unchanged() -> None:
    a = "id,v\n1,x\n2,y\n"
    b = "id,v\n2,y\n1,x\n"
    assert diff_csv_strings(a, b, "a", "b", key="id").identical


def test_csv_field_limit_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real csv.Error path: fields beyond the (here: tiny) size limit."""
    import csv as csv_module

    old = csv_module.field_size_limit()
    monkeypatch.setattr(csv_module, "field_size_limit", lambda n=None: old)
    # Monkeypatching the module function is fragile; instead shrink the
    # real limit and restore it.
    monkeypatch.undo()
    csv_module.field_size_limit(16)
    try:
        with pytest.raises(ValueError, match="malformed CSV"):
            diff_csv_strings("a,b\nxx," + "y" * 64 + "\n", "a,b\n", "a", "b")
    finally:
        csv_module.field_size_limit(old)


def test_csv_header_change_reported() -> None:
    result = diff_csv_strings("a,b\n1,2\n", "a,c\n1,2\n", "a", "b", key="a")
    nodes = _nodes_by_path(result)
    assert nodes["header"].change == "changed"


def test_csv_empty_files() -> None:
    assert diff_csv_strings("", "", "a", "b").identical
    result = diff_csv_strings("", "a,b\n", "a", "b")
    assert result.nodes[0].change == "added"


def test_json_preview_truncated_for_huge_values() -> None:
    big = json.dumps({"k": "x" * 5_000})
    result = diff_json_strings(big, big.replace("xxxx", "yyyy"), "a", "b")
    node = result.nodes[0]
    assert len(node.old) <= 121 and node.old.endswith("...")
