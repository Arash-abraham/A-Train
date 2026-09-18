"""Command-line interface for A-Train.

Exit codes follow the GNU diff convention, so the tool is CI-friendly:

- ``0`` — no differences found
- ``1`` — differences found
- ``2`` — trouble (bad paths, bad options, undecodable input, ...)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from atrain import __version__
from atrain.core import diff_text
from atrain.output import unified

EXIT_SAME = 0
EXIT_DIFFERENCES = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser (grows with each milestone)."""
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
        choices=("unified",),
        default="unified",
        help="output format (default: unified)",
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
        "--encoding",
        default=None,
        metavar="ENCODING",
        help="force a text encoding instead of automatic detection",
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


def _emit(text: str, destination: str | None) -> int:
    if destination is None:
        sys.stdout.write(text)
        sys.stdout.flush()
        return EXIT_SAME
    Path(destination).write_text(text, encoding="utf-8")
    return EXIT_SAME


def _compare_text(args: argparse.Namespace, source: Path, target: Path) -> int:
    result = diff_text.compare_files(source, target, context=args.context, encoding=args.encoding)
    if result.identical:
        return EXIT_SAME
    if result.source.is_binary or result.target.is_binary:
        print(f"Binary files {source} and {target} differ")
        return EXIT_DIFFERENCES
    _emit(unified.render(result, str(source), str(target)), args.output)
    return EXIT_DIFFERENCES


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

    try:
        if args.mode == "text":
            return _compare_text(args, source, target)
        return _fail(f"unhandled mode: {args.mode}")  # pragma: no cover
    except UnicodeDecodeError as exc:
        return _fail(f"{source} or {target}: cannot decode: {exc}")
    except OSError as exc:
        return _fail(str(exc))
