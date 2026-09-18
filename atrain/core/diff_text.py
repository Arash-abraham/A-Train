"""Text diff engine: Myers O(ND) with linear-space refinement.

Design notes (ROADMAP.md, §3):

- **Pre-hashed lines.** Lines are never compared as strings inside the diff
  algorithm.  Each distinct line is interned to a dense integer id in one
  pass (dict lookup, amortised O(1) on the string's cached hash); Myers then
  operates on ``int`` arrays.  Interning realises the roadmap's "map every
  line to an integer" idea with *zero* collision risk: two ids are equal iff
  the lines are byte-equal, so no verification pass is needed.  (Documented
  in DEVELOPMENT_REPORT.md, architecture decisions.)
- **Linear-space refinement.** The middle-snake divide & conquer variant
  (Myers 1986, §4b) keeps memory at O(N + M) instead of storing the V trace
  (O(D²)).  Common prefix/suffix trimming runs at every recursion node.
- **Complexity guard.** If the edit script would cost more than the budget,
  the search aborts and the differing interior is reported as one REPLACE
  hunk — a correct, non-minimal edit script, mirroring GNU diff's own
  give-up heuristics.  Correctness is never sacrificed for speed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from atrain.core.hasher import digest_bytes
from atrain.core.models import (
    DiffLine,
    DiffResult,
    FileMeta,
    Hunk,
    InlineRef,
    LineTag,
    Opcode,
    OpcodeTag,
    compute_stats,
)
from atrain.core.reader import (
    is_textual,
    line_content,
    load_bytes,
    load_text,
    split_lines,
)

MAX_EDIT_COST = 50_000_000
"""Default work budget for the Myers search (inner-loop iterations)."""

INLINE_REF_MAX_CHARS = 300
"""Pair lines are only character-refined up to this length (cost guard)."""


class DiffTooComplex(Exception):
    """Raised internally when the edit script exceeds its work budget."""


@dataclass(frozen=True, slots=True)
class TextOptions:
    """Comparison options for the text engine (ROADMAP.md, §4, v0.2).

    ``ignore_all_space``/``ignore_case``/``strip_trailing_cr`` affect the
    *comparison keys* only — rendered output always shows the original
    line text.  ``ignore_matching`` drops hunks whose changed lines all
    match the regular expression (GNU ``--ignore-matching-lines``).
    """

    context: int = 3
    encoding: str | None = None
    ignore_all_space: bool = False
    ignore_case: bool = False
    ignore_matching: str | None = None
    strip_trailing_cr: bool = False


def comparison_key(line: str, options: TextOptions) -> str:
    """Normalised form of *line* used for equality comparison."""
    if options.strip_trailing_cr:
        if line.endswith("\r\n"):
            line = line[:-2] + "\n"
        elif line.endswith("\r"):
            line = line[:-1]
    if options.ignore_case:
        line = line.lower()
    if options.ignore_all_space:
        line = "".join(line.split())
    return line


class _Budget:
    """Simple countdown of allowed search work."""

    __slots__ = ("remaining",)

    def __init__(self, limit: int) -> None:
        self.remaining = limit

    def spend(self, work: int) -> None:
        self.remaining -= work
        if self.remaining < 0:
            raise DiffTooComplex


def _intern_into(ids: dict[str, int], lines: Sequence[str]) -> list[int]:
    """Intern *lines* into the shared *ids* table, returning their id list."""
    out: list[int] = []
    append = out.append
    for line in lines:
        i = ids.get(line)
        if i is None:
            i = len(ids)
            ids[line] = i
        append(i)
    return out


def intern_lines(lines: Sequence[str]) -> list[int]:
    """Map a single line sequence to dense integer ids.

    Note:
        For *comparing* two sequences always use :func:`intern_line_pairs` —
        ids are only meaningful within one shared interning table.
    """
    return _intern_into({}, lines)


def intern_line_pairs(
    a_lines: Sequence[str], b_lines: Sequence[str]
) -> tuple[list[int], list[int]]:
    """Intern both line sequences into one shared table.

    Identical lines across the two inputs receive the same id — the
    precondition for running Myers over the id arrays.
    """
    ids: dict[str, int] = {}
    return _intern_into(ids, a_lines), _intern_into(ids, b_lines)


def _forward_step(
    a: Sequence[int], b: Sequence[int], vf: dict[int, int], d: int
) -> dict[int, tuple[int, int, int, int]]:
    """Advance the forward frontier to depth *d*.

    Returns ``{k: (x0, y0, x, y)}`` — the position before and after the
    snake for each reached diagonal *k*.
    """
    n, m = len(a), len(b)
    res: dict[int, tuple[int, int, int, int]] = {}
    for k in range(-d, d + 1, 2):
        if k == -d:
            x = vf[k + 1]
        elif k == d:
            x = vf[k - 1] + 1
        elif vf[k - 1] < vf[k + 1]:
            x = vf[k + 1]
        else:
            x = vf[k - 1] + 1
        y = x - k
        x0, y0 = x, y
        while x < n and y < m and a[x] == b[y]:
            x += 1
            y += 1
        vf[k] = x
        res[k] = (x0, y0, x, y)
    return res


def _middle_snake(
    a: Sequence[int], b: Sequence[int], budget: _Budget
) -> tuple[int, int, int, int, int]:
    """Find the middle snake of *a*, *b* (full sequences, already trimmed).

    Returns ``(d, sx, sy, ex, ey)``: the edit distance of the whole span and
    the snake's half-open extent ``a[sx:ex] == b[sy:ey]``.

    The backward search runs the *forward* step function on reversed
    sequences; reversed coordinates ``(x', y')`` map back to
    ``(N - x', M - y')`` and diagonals via ``k = delta - k'``.
    """
    n, m = len(a), len(b)
    ra = a[::-1]
    rb = b[::-1]
    delta = n - m
    vf: dict[int, int] = {1: 0}
    vr: dict[int, int] = {1: 0}
    max_d = (n + m + 1) // 2
    for d in range(max_d + 1):
        budget.spend(d + 1)
        f_res = _forward_step(a, b, vf, d)
        if delta % 2 != 0:
            # A forward d-path may meet a reverse (d-1)-path on the same
            # original diagonal.
            lo, hi = delta - (d - 1), delta + (d - 1)
            for k, (x0, y0, x, y) in f_res.items():
                if lo <= k <= hi:
                    xp = vr.get(delta - k)
                    if xp is not None and x + xp >= n:
                        return 2 * d - 1, x0, y0, x, y
        r_res = _forward_step(ra, rb, vr, d)
        if delta % 2 == 0:
            # A reverse d-path may meet a forward d-path on the same
            # original diagonal; the snake in original coordinates runs
            # backwards through the meeting point.
            for k_rev, (rx0, ry0, rx, ry) in r_res.items():
                k = delta - k_rev
                if -d <= k <= d:
                    xf = vf.get(k)
                    if xf is not None and rx + xf >= n:
                        return 2 * d, n - rx, m - ry, n - rx0, m - ry0
    raise AssertionError("unreachable: Myers search space exhausted")  # pragma: no cover


_DiffFrame = tuple[str, int, int, int, int]
_EmitFrame = tuple[str, Opcode]
_Frame = _DiffFrame | _EmitFrame


def _run_myers(a: Sequence[int], b: Sequence[int], budget: _Budget) -> list[Opcode]:
    """Produce merged opcodes via iterative middle-snake recursion.

    The divide & conquer recursion is expressed with an explicit stack of
    ``("diff", ...)`` and ``("emit", ...)`` frames so inputs beyond Python's
    recursion limit cannot crash the engine.
    """
    ops: list[Opcode] = []
    stack: list[_Frame] = [("diff", 0, len(a), 0, len(b))]
    while stack:
        frame = stack.pop()
        match frame:
            case ("emit", op):
                ops.append(op)
                continue
            case ("diff", a0, a1, b0, b1):
                pass
            case _:  # pragma: no cover
                raise AssertionError(f"bad stack frame: {frame!r}")

        # Common prefix.
        pa0, pb0 = a0, b0
        while a0 < a1 and b0 < b1 and a[a0] == b[b0]:
            a0 += 1
            b0 += 1
        # Common suffix.
        tail = 0
        while a1 > a0 and b1 > b0 and a[a1 - 1] == b[b1 - 1]:
            a1 -= 1
            b1 -= 1
            tail += 1
        n, m = a1 - a0, b1 - b0

        # Push in the reverse of the desired emission order:
        # suffix-equal, then the interior, then prefix-equal.
        if tail:
            equal = Opcode(
                OpcodeTag.EQUAL, a1, a1 + tail, b1, b1 + tail
            )
            stack.append(("emit", equal))
        if n == 0 and m == 0:
            pass
        elif n == 0:
            stack.append(("emit", Opcode(OpcodeTag.INSERT, a0, a0, b0, b1)))
        elif m == 0:
            stack.append(("emit", Opcode(OpcodeTag.DELETE, a0, a1, b0, b0)))
        else:
            d, sx, sy, ex, ey = _middle_snake(a[a0:a1], b[b0:b1], budget)
            if d > 1:
                stack.append(("diff", a0 + ex, a1, b0 + ey, b1))
                snake = Opcode(
                    OpcodeTag.EQUAL, a0 + sx, a0 + ex, b0 + sy, b0 + ey
                )
                stack.append(("emit", snake))
                stack.append(("diff", a0, a0 + sx, b0, b0 + sy))
            else:
                # d == 1 with both sides non-empty cannot occur after
                # two-sided trimming (a single insertion/deletion would
                # leave one side empty).  Defensive fallback: one
                # replacement — still a correct edit script.
                stack.append(("emit", Opcode(OpcodeTag.REPLACE, a0, a1, b0, b1)))
        if a0 > pa0:
            prefix = Opcode(OpcodeTag.EQUAL, pa0, a0, pb0, b0)
            stack.append(("emit", prefix))
    return _merge_opcodes(ops)


def _merge_opcodes(ops: list[Opcode]) -> list[Opcode]:
    """Merge adjacent EQUAL blocks and DELETE+INSERT pairs; drop empty ops."""
    merged: list[Opcode] = []
    for op in ops:
        if op.tag is OpcodeTag.EQUAL and op.a_end == op.a_start:
            continue
        prev = merged[-1] if merged else None
        if prev is not None and prev.a_end == op.a_start and prev.b_end == op.b_start:
            if prev.tag is OpcodeTag.EQUAL and op.tag is OpcodeTag.EQUAL:
                merged[-1] = Opcode(
                    OpcodeTag.EQUAL, prev.a_start, op.a_end, prev.b_start, op.b_end
                )
                continue
            if (
                prev.tag in (OpcodeTag.DELETE, OpcodeTag.INSERT)
                and op.tag in (OpcodeTag.DELETE, OpcodeTag.INSERT)
                and prev.tag is not op.tag
            ):
                merged[-1] = Opcode(
                    OpcodeTag.REPLACE, prev.a_start, op.a_end, prev.b_start, op.b_end
                )
                continue
        merged.append(op)
    return merged


def myers_opcodes(
    a: Sequence[int], b: Sequence[int], budget: _Budget | None = None
) -> list[Opcode]:
    """Minimal edit script between two id sequences as merged opcodes.

    When the work budget is exhausted the differing interior (after cheap
    prefix/suffix trimming) is reported as a single REPLACE — correct but
    not minimal, mirroring GNU diff's give-up behaviour.
    """
    own_budget = budget or _Budget(MAX_EDIT_COST)
    try:
        ops = _run_myers(a, b, own_budget)
    except DiffTooComplex:
        p = 0
        while p < len(a) and p < len(b) and a[p] == b[p]:
            p += 1
        s = 0
        while s < len(a) - p and s < len(b) - p and a[len(a) - 1 - s] == b[len(b) - 1 - s]:
            s += 1
        ops = _merge_opcodes(
            [
                Opcode(OpcodeTag.EQUAL, 0, p, 0, p),
                Opcode(OpcodeTag.REPLACE, p, len(a) - s, p, len(b) - s),
                Opcode(OpcodeTag.EQUAL, len(a) - s, len(a), len(b) - s, len(b)),
            ]
        )
    if all(op.tag is OpcodeTag.EQUAL for op in ops):
        return []  # identical inputs: no edit script at all
    return ops


def build_hunks(
    ops: Sequence[Opcode],
    a_lines: Sequence[str],
    b_lines: Sequence[str],
    context: int = 3,
) -> list[Hunk]:
    """Group opcodes into :class:`Hunk` objects with *context* lines.

    Grouping follows the same boundary rules as ``difflib`` (and hence GNU
    diff for equal context values): changed blocks separated by more than
    ``2 * context`` equal lines become separate hunks.
    """
    if context < 0:
        raise ValueError("context must be >= 0")
    if not any(op.tag is not OpcodeTag.EQUAL for op in ops):
        return []

    rows: list[tuple[str, int, int, int, int]] = [
        (op.tag.value, op.a_start, op.a_end, op.b_start, op.b_end) for op in ops
    ]
    # Trim surplus leading/trailing equal context.
    tag, i1, i2, j1, j2 = rows[0]
    if tag == "equal":
        rows[0] = (tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2)
    tag, i1, i2, j1, j2 = rows[-1]
    if tag == "equal":
        rows[-1] = (tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context))

    groups: list[list[tuple[str, int, int, int, int]]] = []
    group: list[tuple[str, int, int, int, int]] = []
    span = 2 * context
    for row in rows:
        tag, i1, i2, j1, j2 = row
        if tag == "equal" and i2 - i1 > span:
            group.append((tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)))
            groups.append(group)
            group = [(tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2)]
        else:
            group.append(row)
    if group and not (len(group) == 1 and group[0][0] == "equal"):
        groups.append(group)

    hunks: list[Hunk] = []
    for entries in groups:
        a_start, a_end = entries[0][1], entries[-1][2]
        b_start, b_end = entries[0][3], entries[-1][4]
        lines: list[DiffLine] = []
        for row_tag, i1, i2, j1, j2 in entries:
            if row_tag == "equal":
                for k in range(i1, i2):
                    text, nl = line_content(a_lines[k])
                    lines.append(DiffLine(LineTag.CONTEXT, text, nl))
                continue
            if row_tag == "replace":
                lines.extend(
                    _replace_lines(a_lines, i1, i2, b_lines, j1, j2)
                )
                continue
            if row_tag == "delete":
                for k in range(i1, i2):
                    text, nl = line_content(a_lines[k])
                    lines.append(DiffLine(LineTag.DELETE, text, nl))
            if row_tag == "insert":
                for k in range(j1, j2):
                    text, nl = line_content(b_lines[k])
                    lines.append(DiffLine(LineTag.INSERT, text, nl))
        hunks.append(Hunk(a_start, a_end - a_start, b_start, b_end - b_start, lines))
    return hunks


def _common_ends(a: str, b: str) -> tuple[int, int]:
    """Lengths of the equal prefix and suffix runs of *a* and *b*."""
    limit = min(len(a), len(b))
    prefix = 0
    while prefix < limit and a[prefix] == b[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and a[-1 - suffix] == b[-1 - suffix]:
        suffix += 1
    return prefix, suffix


def _replace_lines(
    a_lines: Sequence[str], i1: int, i2: int, b_lines: Sequence[str], j1: int, j2: int
) -> list[DiffLine]:
    """Render a REPLACE row, pairing lines for character-level refinement.

    The first ``min(#deleted, #inserted)`` lines are paired in order; each
    pair gets an :class:`InlineRef` marking the common prefix/suffix so
    formatters can highlight just the changed middle (two-phase diffing,
    ROADMAP §3.5).
    """
    deleted: list[DiffLine] = []
    for k in range(i1, i2):
        text, nl = line_content(a_lines[k])
        deleted.append(DiffLine(LineTag.DELETE, text, nl))
    inserted: list[DiffLine] = []
    for k in range(j1, j2):
        text, nl = line_content(b_lines[k])
        inserted.append(DiffLine(LineTag.INSERT, text, nl))

    for d_line, i_line in zip(deleted, inserted, strict=False):
        if len(d_line.text) > INLINE_REF_MAX_CHARS or len(i_line.text) > INLINE_REF_MAX_CHARS:
            continue
        prefix, suffix = _common_ends(d_line.text, i_line.text)
        ref = InlineRef(prefix_len=prefix, suffix_len=suffix)
        d_line.inline = ref
        i_line.inline = ref
    return deleted + inserted


def diff_lines(
    a_lines: Sequence[str],
    b_lines: Sequence[str],
    context: int = 3,
    budget: _Budget | None = None,
) -> list[Hunk]:
    """Diff two already-split line lists into hunks (no ignore options)."""
    ids_a, ids_b = intern_line_pairs(a_lines, b_lines)
    ops = myers_opcodes(ids_a, ids_b, budget)
    return build_hunks(ops, a_lines, b_lines, context)


def _hunk_all_matches(hunk: Hunk, pattern: re.Pattern[str]) -> bool:
    """True when every changed line of *hunk* matches *pattern* (GNU -I)."""
    changed = [line for line in hunk.lines if line.tag is not LineTag.CONTEXT]
    return bool(changed) and all(pattern.search(line.text) for line in changed)


def diff_line_lists(
    a_lines: Sequence[str],
    b_lines: Sequence[str],
    options: TextOptions | None = None,
) -> list[Hunk]:
    """Diff with the full option set (ignore space/case/regex, CR, context)."""
    opts = options or TextOptions()
    if opts.context < 0:
        raise ValueError("context must be >= 0")
    pattern: re.Pattern[str] | None = None
    if opts.ignore_matching is not None:
        pattern = re.compile(opts.ignore_matching)  # may raise re.error
    keys_a = [comparison_key(line, opts) for line in a_lines]
    keys_b = [comparison_key(line, opts) for line in b_lines]
    ids_a, ids_b = intern_line_pairs(keys_a, keys_b)
    ops = myers_opcodes(ids_a, ids_b)
    hunks = build_hunks(ops, a_lines, b_lines, opts.context)
    if pattern is not None:
        hunks = [hunk for hunk in hunks if not _hunk_all_matches(hunk, pattern)]
    return hunks


def diff_texts(
    a_text: str, b_text: str, options: TextOptions | None = None
) -> list[Hunk]:
    """Diff two complete texts into hunks (convenience for tests/tools)."""
    return diff_line_lists(split_lines(a_text), split_lines(b_text), options)


def compare_files(
    path_a: Path,
    path_b: Path,
    options: TextOptions | None = None,
) -> DiffResult:
    """Full text comparison of two files, with hash-based early exit.

    Binary payloads (NUL sniff) are never decoded on the auto path; the
    result simply carries ``is_binary`` and no hunks, and presentation
    layers decide how to report it (the CLI prints a GNU-style one-liner).
    A forced encoding in *options* overrides the sniff.
    """
    opts = options or TextOptions()
    with load_bytes(path_a) as raw_a, load_bytes(path_b) as raw_b:
        meta_a = FileMeta(
            path=str(path_a),
            size=raw_a.size,
            digest=digest_bytes(raw_a.data),
            is_binary=not is_textual(raw_a.data),
        )
        meta_b = FileMeta(
            path=str(path_b),
            size=raw_b.size,
            digest=digest_bytes(raw_b.data),
            is_binary=not is_textual(raw_b.data),
        )

    result = DiffResult(mode="text", source=meta_a, target=meta_b, identical=False)

    if meta_a.digest == meta_b.digest and meta_a.size == meta_b.size:
        result.identical = True
        return result
    if opts.encoding is None and (meta_a.is_binary or meta_b.is_binary):
        return result  # no hunks; caller reports a binary difference

    lines_a, meta_a = load_text(path_a, opts.encoding)
    lines_b, meta_b = load_text(path_b, opts.encoding)
    result.source = meta_a
    result.target = meta_b
    result.hunks = diff_line_lists(lines_a, lines_b, opts)
    result.stats = compute_stats(result.hunks)
    result.identical = not result.hunks
    return result
