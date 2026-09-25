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
from atrain.core import diff_binary, diff_structured, diff_text, diff_tree
from atrain.core.diff_text import TextOptions
from atrain.core.diff_tree import TreeOptions
from atrain.core.models import DiffResult
from atrain.output import color, html_report, json_out, side_by_side, unified

EXIT_SAME = 0
EXIT_DIFFERENCES = 1
EXIT_ERROR = 2

_TEXTUAL_FORMATS = ("unified", "color", "side")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="atrain",
        description="A-Train — a high-performance file comparison tool.",
    )
    parser.add_argument("source", help="first file or directory")
    parser.add_argument("target", help="second file or directory")
    parser.add_argument(
        "--mode",
        choices=("text", "binary", "json", "csv", "dir"),
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
        help="[text] ignore all whitespace when comparing lines",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="[text] ignore letter case when comparing lines",
    )
    parser.add_argument(
        "--ignore-matching",
        "--ignore-matching-lines",
        default=None,
        metavar="REGEX",
        help="[text] drop hunks whose changed lines all match REGEX",
    )
    parser.add_argument(
        "--strip-trailing-cr",
        action="store_true",
        help="[text] treat CRLF and LF newlines as equal when comparing",
    )
    parser.add_argument(
        "--key-col",
        default=None,
        metavar="NAME|N",
        help="[csv] key column: header name or 1-based index",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help="[dir] maximum parallel workers (default: min(8, CPUs))",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="[dir] cache file digests across runs (validated by size+mtime)",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="open the interactive viewer instead of printing a diff",
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
        help="[side] total width (default: terminal width)",
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


def _run_tui(source: Path, target: Path) -> int:
    """Launch the interactive viewer; friendly error if Textual is absent."""
    if not source.is_file() or not target.is_file():
        return _fail("--tui compares two files; directory TUI is not supported")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return _fail("--tui needs an interactive terminal (no TTY attached)")
    try:
        from atrain.tui import DiffTui
    except ImportError as exc:
        return _fail(str(exc).replace("atrain.tui", "the TUI module"))
    try:
        from textual.widgets import Footer  # noqa: F401
    except ImportError:
        return _fail(
            "The TUI needs the optional dependency 'textual'. "
            "Install it with: pip install textual"
        )
    DiffTui(source, target).run()
    return EXIT_SAME


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


def _text_options(args: argparse.Namespace) -> TextOptions:
    return TextOptions(
        context=args.context,
        encoding=args.encoding,
        ignore_all_space=args.ignore_space,
        ignore_case=args.ignore_case,
        ignore_matching=args.ignore_matching,
        strip_trailing_cr=args.strip_trailing_cr,
    )


def _compare_text(args: argparse.Namespace, source: Path, target: Path) -> int:
    result = diff_text.compare_files(source, target, _text_options(args))
    if result.identical and args.format in _TEXTUAL_FORMATS:
        return EXIT_SAME  # GNU behaviour: silence on equality
    if (
        not result.identical
        and (result.source.is_binary or result.target.is_binary)
        and args.format in _TEXTUAL_FORMATS
    ):
        print(f"Binary files {source} and {target} differ")
        return EXIT_DIFFERENCES
    _emit(_render(result, args, source, target), args.output)
    return EXIT_DIFFERENCES if not result.identical else EXIT_SAME


def _compare_binary(args: argparse.Namespace, source: Path, target: Path) -> int:
    result = diff_binary.compare_binary(source, target)
    if result.identical:
        return EXIT_SAME
    _emit(_render(result, args, source, target), args.output)
    return EXIT_DIFFERENCES


def _parse_key_col(raw: str | None) -> str | int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def _compare_structured(
    args: argparse.Namespace, source: Path, target: Path, mode: str
) -> int:
    key = _parse_key_col(args.key_col)
    if mode == "json":
        result = diff_structured.diff_json_files(
            source, target, encoding=args.encoding
        )
    else:
        result = diff_structured.diff_csv_files(
            source, target, key=key, encoding=args.encoding
        )
    if result.identical and args.format in _TEXTUAL_FORMATS:
        return EXIT_SAME
    _emit(_render(result, args, source, target), args.output)
    return EXIT_DIFFERENCES


def _compare_dir(args: argparse.Namespace, source: Path, target: Path) -> int:
    options = TreeOptions(workers=args.workers, context=args.context, use_cache=args.cache)
    result = diff_tree.compare_trees(source, target, options)
    if result.identical and args.format in _TEXTUAL_FORMATS:
        return EXIT_SAME
    _emit(_render(result, args, source, target), args.output)
    return EXIT_DIFFERENCES if not result.identical else EXIT_SAME


def _validate(args: argparse.Namespace, source: Path, target: Path) -> str | None:
    for path in (source, target):
        if not path.exists():
            return f"{path}: No such file or directory"
    if args.mode == "dir":
        for path in (source, target):
            if not path.is_dir():
                return f"{path}: --mode dir requires directories"
        return None
    for path in (source, target):
        if path.is_dir():
            return f"{path}: Is a directory (try --mode dir)"
    if args.mode in ("json", "csv") and args.format == "side":
        return "side-by-side output supports text mode only"
    if args.mode == "csv" and args.key_col is not None:
        try:
            _parse_key_col(args.key_col)
        except ValueError:
            return f"invalid key column: {args.key_col!r}"
    if args.context < 0:
        return "context must be >= 0"
    if args.encoding is not None:
        try:
            "".encode(args.encoding)
        except LookupError:
            return f"unknown encoding: {args.encoding!r}"
    if args.ignore_matching is not None:
        try:
            re.compile(args.ignore_matching)
        except re.error as exc:
            return f"invalid regular expression: {exc}"
    return None

_BANNER = (
    "\n"
    " █████╗       ████████╗██████╗  █████╗ ██╗███╗   ██╗\n"
    "██╔══██╗      ╚══██╔══╝██╔══██╗██╔══██╗██║████╗  ██║\n"
    "███████║█████╗   ██║   ██████╔╝███████║██║██╔██╗ ██║\n"
    "██╔══██║╚════╝   ██║   ██╔══██╗██╔══██║██║██║╚██╗██║\n"
    "██║  ██║         ██║   ██║  ██║██║  ██║██║██║ ╚████║\n"
    "╚═╝  ╚═╝         ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝\n"
)


def _print_banner() -> None:
    """Print the A-Train banner to stderr when attached to a TTY."""
    if not sys.stderr.isatty():
        return
    try:
        from colorama import Fore, Style, init as _colorama_init
        _colorama_init()
        blue, reset = Fore.BLUE, Style.RESET_ALL
    except ImportError:
        blue = reset = ""
    print(f"{blue}{_BANNER}{reset}", file=sys.stderr, flush=True)

    
def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""

    argv = list(sys.argv[1:] if argv is None else argv)

    if not any(a in ("-h", "--help", "--version", "-v") for a in argv):
        _print_banner()
    
    parser = build_parser()
    args = parser.parse_args(argv)

    source = Path(args.source)
    target = Path(args.target)

    if args.tui:
        return _run_tui(source, target)
    if args.cache and args.mode != "dir":
        return _fail("--cache applies to --mode dir only")

    problem = _validate(args, source, target)
    if problem is not None:
        return _fail(problem)

    try:
        if args.mode == "text":
            return _compare_text(args, source, target)
        if args.mode == "binary":
            return _compare_binary(args, source, target)
        if args.mode in ("json", "csv"):
            return _compare_structured(args, source, target, args.mode)
        if args.mode == "dir":
            return _compare_dir(args, source, target)
        return _fail(f"unhandled mode: {args.mode}")  # pragma: no cover
    except UnicodeDecodeError as exc:
        return _fail(f"cannot decode: {exc}")
    except ValueError as exc:
        return _fail(str(exc))
    except OSError as exc:
        return _fail(str(exc))


def _emit(text: str, destination: str | None) -> None:
    if destination is None:
        sys.stdout.write(text)
        sys.stdout.flush()
    else:
        Path(destination).write_text(text, encoding="utf-8")
