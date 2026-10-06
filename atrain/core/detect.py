"""Automatic comparison-mode detection.

When the CLI is invoked without ``--mode`` (or with ``--mode auto``), the
engine is chosen from the inputs themselves so that
``atrain a.json b.json`` "just works":

1. Two directories → ``dir``.
2. Both files share a well-known structured extension → ``json`` / ``csv``,
   confirmed by a cheap content sniff so that a ``.json`` file holding
   garbage still falls back to a plain text diff.
3. Either file sniffs as binary (NUL byte in the head, no Unicode BOM)
   → ``binary``.
4. Otherwise ``text``.

Detection is deliberately conservative: it only switches engine when *both*
inputs agree, because mixed inputs are far more likely to be a mistake
than an intentional cross-format comparison.  The chosen engine is
reported on stderr by the CLI so CI logs stay explicit.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from atrain.core.reader import decode_text, is_textual, load_bytes

JSON_EXTENSIONS: frozenset[str] = frozenset({".json", ".jsonc", ".geojson", ".har"})
CSV_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv"})

#: Bytes examined when confirming a structured format.
SNIFF_BYTES = 64 * 1024


def _head(path: Path) -> bytes:
    with load_bytes(path) as raw:
        return bytes(raw.data[:SNIFF_BYTES])


def _is_binary_file(path: Path) -> bool:
    return not is_textual(_head(path))


def _sniff_json(path: Path, encoding: str | None) -> bool:
    """True when the file parses as JSON (whole file; JSON must be complete)."""
    try:
        with load_bytes(path) as raw:
            text, _ = decode_text(raw.data, encoding)
        json.loads(text)
    except (ValueError, UnicodeDecodeError, OSError):
        return False
    return True


def _sniff_csv(path: Path, encoding: str | None) -> bool:
    """True when the leading chunk has a consistent delimiter structure."""
    try:
        text, _ = decode_text(_head(path), encoding)
    except (UnicodeDecodeError, LookupError):
        return False
    sample = text[:8192]
    if not sample.strip():
        return False
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return False
    rows = [r for r in csv.reader(sample.splitlines()[:20], dialect) if r]
    if len(rows) < 2:
        return False
    widths = {len(r) for r in rows[:-1]}  # last sampled row may be truncated
    return len(widths) == 1 and widths.pop() >= 2


def detect_mode(source: Path, target: Path, encoding: str | None = None) -> str:
    """Return the comparison mode best suited to *source* and *target*."""
    if source.is_dir() and target.is_dir():
        return "dir"
    if not (source.is_file() and target.is_file()):
        return "text"  # let the validator produce the proper error

    exts = {source.suffix.lower(), target.suffix.lower()}
    if len(exts) == 1:
        ext = next(iter(exts))
        if ext in JSON_EXTENSIONS:
            if _sniff_json(source, encoding) and _sniff_json(target, encoding):
                return "json"
        elif ext in CSV_EXTENSIONS:
            if _sniff_csv(source, encoding) and _sniff_csv(target, encoding):
                return "csv"

    try:
        if _is_binary_file(source) or _is_binary_file(target):
            return "binary"
    except OSError:
        return "text"
    return "text"


__all__ = ["CSV_EXTENSIONS", "JSON_EXTENSIONS", "detect_mode"]
