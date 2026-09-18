"""Command-line interface for A-Train.

Exit codes follow the GNU diff convention, so the tool is CI-friendly:

- ``0`` — no differences found
- ``1`` — differences found
- ``2`` — trouble (bad paths, bad options, undecodable input, ...)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from atrain import __version__
from atrain.core import diff_text
from atrain.core.diff_text import TextOptions
from atrain.core.models import DiffResult
from atrain.output import color, html_report, json_out, side_by_side, unified

EXIT_SAME = 0
EXIT_DIFFERENCES = 1
EXIT_ERROR = 2

_TEXT_FORMATS = ("unified", "color", "side")
_DOC_FORMATS = ("html", "json")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="atrain",
        description="A-Train — a high-performance file comparison tool.",
    )
    parser.add_argument("source", help="first file (or directory, with --mode dir)")
    parser.add_argument("target", help="second file (or directory, with --mode dir)")
    parser.add_argument(
        "--mode",
        choices=("text",),
        default="text",
        help="comparison mode (default: text)",
    )
    parser.add_argument(
        "--format",
        choices=("unified", "color", "side", "html", "json"),
        default="unified",
        help="output format (default: unified)",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="when to colourise --format color output (default: auto = TTY)",
    )
    parser.add_argument(
        "-U",
        "--context",
        type=int,
        default=3,
        metavar="N",
        help="lines of context around changes (default: 3)",
    )
    parser.add_argument(
        "--ignore-space",
        action="store_true",
        help="ignore all whitespace when comparing lines",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="ignore letter case when comparing lines",
    )
    parser.add_argument(
        "--ignore-matching",
        "--ignore-matching-lines",
        default=None,
        metavar="REGEX",
        help="drop hunks whose changed lines all match REGEX",
    )
    parser.add_argument(
        "--strip-trailing-cr",
        action="store_true",
        help="treat CRLF and LF newlines as equal when comparing",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        metavar="ENCODING",
        help="force a text encoding instead of automatic detection",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        metavar="COLUMNS",
        help="total width for --format side (default: terminal width)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="write output to FILE instead of standard output",
    )
    parser.add_argument(
        "--version", action="version", version=f"atrain {__version__}"
    )
    return parser


def _fail(message: str) -> int:
    print(f"atrain: error: {message}", file=sys.stderr)
    return EXIT_ERROR


def _use_color(args: argparse.Namespace) -> bool:
    if args.format != "color":
        return False
    if args.color == "always":
        return True
    if args.color == "never":
        return False
    writing_to_file = args.output is not None
    return not writing_to_file and sys.stdout.isatty()


def _render(result: DiffResult, args: argparse.Namespace, source: Path, target: Path) -> str:
    a_label, b_label = str(source), str(target)
    if args.format == "unified":
        return unified.render(result, a_label, b_label)
    if args.format == "color":
        return color.render(result, a_label, b_label, color=_use_color(args))
    if args.format == "side":
        return side_by_side.render(result, a_label, b_label, width=args.width)
    if args.format == "html":
        return html_report.render(result, a_label, b_label)
    if args.format == "json":
        return json_out.render(result)
    raise AssertionError(f"unhandled format: {args.format}")  # pragma: no cover


def _compare_text(args: argparse.Namespace, source: Path, target: Path) -> int:
    options = TextOptions(
        context=args.context,
        encoding=args.encoding,
        ignore_all_space=args.ignore_space,
        ignore_case=args.ignore_case,
        ignore_matching=args.ignore_matching,
        strip_trailing_cr=args.strip_trailing_cr,
    )
    result = diff_text.compare_files(source, target, options)
    binary_diff = (
        not result.identical
        and (result.source.is_binary or result.target.is_binary)
        and args.format in _TEXT_FORMATS
    )
    if result.identical and args.format in _TEXT_FORMATS:
        return EXIT_SAME  # GNU behaviour: silence on equality
    if binary_diff:
        print(f"Binary files {source} and {target} differ")
        return EXIT_DIFFERENCES
    _emit(_render(result, args, source, target), args.output)
    return EXIT_DIFFERENCES if not result.identical else EXIT_SAME


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    source = Path(args.source)
    target = Path(args.target)
    for path in (source, target):
        if not path.exists():
            return _fail(f"{path}: No such file or directory")
        if path.is_dir():
            return _fail(f"{path}: Is a directory (directory mode is not available yet)")

    if args.context < 0:
        return _fail("context must be >= 0")
    if args.encoding is not None:
        try:
            "".encode(args.encoding)
        except LookupError:
            return _fail(f"unknown encoding: {args.encoding!r}")
    if args.ignore_matching is not None:
        try:
            re.compile(args.ignore_matching)
        except re.error as exc:
            return _fail(f"invalid regular expression: {exc}")

    try:
        if args.mode == "text":
            return _compare_text(args, source, target)
        return _fail(f"unhandled mode: {args.mode}")  # pragma: no cover
    except UnicodeDecodeError as exc:
        return _fail(f"{source} or {target}: cannot decode: {exc}")
    except OSError as exc:
        return _fail(str(exc))


def _emit(text: str, destination: str | None) -> None:
    if destination is None:
        sys.stdout.write(text)
        sys.stdout.flush()
    else:
        Path(destination).write_text(text, encoding="utf-8")
