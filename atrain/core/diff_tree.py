"""Directory-tree comparison with parallel hashing (ROADMAP.md, §3.6).

Design notes:

- **Architecture addition (documented per the project rules):** the
  roadmap's tree in §2 lists no ``diff_tree.py``; tree walking lives in
  this new core module because neither ``diff_text`` nor
  ``diff_structured`` owns it.  ``DEVELOPMENT_REPORT.md``, §Architecture
  additions, records the rationale.
- **Determinism:** file sets are gathered with sorted walks and every
  result list is sorted by path — output never depends on scheduling.
- **Parallelism:** per-file digests are computed in a
  ``ProcessPoolExecutor`` (hashing releases the GIL only for large
  buffers; processes keep the per-file text diffs off one GIL as well).
  Worker count defaults to ``min(8, cpu_count())`` and can be capped via
  ``--workers``.  Any pool start failure falls back to sequential
  execution; per-file exceptions are captured as ``error`` entries, never
  fatal.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from atrain.core.hasher import file_digest
from atrain.core.models import DiffResult, FileMeta, TreeEntry


def _open_cache(opts: TreeOptions) -> object | None:
    """Instantiate the digest cache when enabled; None on any failure."""
    if not opts.use_cache:
        return None
    try:
        from atrain.core.cache import DigestCache

        return DigestCache(opts.cache_path)
    except Exception:  # noqa: BLE001 — cache must never break comparing
        return None


def _save_cache(cache: object | None) -> None:
    if cache is None:
        return
    try:
        cache.save()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

DEFAULT_MAX_WORKERS = 8


@dataclass(frozen=True, slots=True)
class TreeOptions:
    """Options for tree comparison."""

    workers: int | None = None  # None = min(DEFAULT_MAX_WORKERS, cpu_count)
    diff_modified: bool = True  # attach per-file text diffs for modified files
    context: int = 3
    use_cache: bool = False  # persistent digest cache (ROADMAP §3.7)
    cache_path: Path | None = field(default=None, kw_only=True)


def _resolve_workers(workers: int | None) -> int:
    if workers is not None and workers >= 1:
        return workers
    return max(1, min(DEFAULT_MAX_WORKERS, os.cpu_count() or 1))


def _hash_one(path_str: str) -> tuple[str, str | None, str | None]:
    """Worker: BLAKE2b digest of one file; returns (path, digest, error)."""
    path = Path(path_str)
    try:
        return path_str, file_digest(path), None
    except OSError as exc:
        return path_str, None, str(exc)


def _walk_files(root: Path) -> tuple[set[str], set[str]]:
    """Sorted relative file paths and directory paths under *root*."""
    files: set[str] = set()
    dirs: set[str] = set()
    for current, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel = Path(current).relative_to(root)
        prefix = "" if rel == Path(".") else rel.as_posix() + "/"
        dirs.update(prefix + name for name in dirnames)
        for name in sorted(filenames):
            files.add(prefix + name)
    return files, dirs


def compare_trees(
    path_a: Path, path_b: Path, options: TreeOptions | None = None
) -> DiffResult:
    """Compare two directory trees; per-file diffs attached for modified text files."""
    opts = options or TreeOptions()
    files_a, dirs_a = _walk_files(path_a)
    files_b, dirs_b = _walk_files(path_b)

    meta_a = FileMeta(path=str(path_a), size=len(files_a))
    # size carries the file count for tree roots (documented in json_out).
    meta_b = FileMeta(path=str(path_b), size=len(files_b))
    result = DiffResult(mode="dir", source=meta_a, target=meta_b, identical=False)

    added = sorted(files_b - files_a)
    removed = sorted(files_a - files_b)
    common = sorted(files_a & files_b)

    digest_cache = _open_cache(opts)
    digests_a, errors_a = _digest_all(path_a, common, opts.workers, digest_cache)
    digests_b, errors_b = _digest_all(path_b, common, opts.workers, digest_cache)
    _save_cache(digest_cache)

    entries: list[TreeEntry] = []
    for rel in added:
        entries.append(TreeEntry(path=rel, change="added", kind="file"))
    for rel in removed:
        entries.append(TreeEntry(path=rel, change="removed", kind="file"))
    modified: list[str] = []
    for rel in common:
        da, db = digests_a.get(rel), digests_b.get(rel)
        if da is None or db is None:
            detail = errors_a.get(rel) or errors_b.get(rel) or "unreadable"
            entries.append(TreeEntry(path=rel, change="error", kind="file", detail=detail))
            result.errors.append(f"{rel}: {detail}")
        elif da == db:
            entries.append(TreeEntry(path=rel, change="unchanged", kind="file"))
        else:
            entries.append(TreeEntry(path=rel, change="modified", kind="file"))
            modified.append(rel)

    # Directories that exist on exactly one side (incl. empty ones).
    for rel in sorted(dirs_b - dirs_a):
        entries.append(TreeEntry(path=rel + "/", change="added", kind="dir"))
    for rel in sorted(dirs_a - dirs_b):
        entries.append(TreeEntry(path=rel + "/", change="removed", kind="dir"))

    entries.sort(key=lambda e: e.path)
    result.entries = entries

    if opts.diff_modified and modified:
        result.children, diff_errors = _diff_all_modified(
            path_a, path_b, modified, opts
        )
        for rel, message in diff_errors.items():
            result.errors.append(f"{rel}: {message}")

    result.identical = not (added or removed or modified or result.errors)
    return result


def _diff_one_worker(job: tuple[str, str, str, int]) -> tuple[str, DiffResult | None, str | None]:
    """Worker: diff one modified file pair (text or binary); never raises."""
    pa_str, pb_str, rel, context = job
    try:
        from atrain.core.diff_binary import compare_binary
        from atrain.core.diff_text import TextOptions, compare_files

        child = compare_files(Path(pa_str), Path(pb_str), TextOptions(context=context))
        if not child.hunks and (child.source.is_binary or child.target.is_binary):
            # Binary payload: switch to region-based comparison.
            child = compare_binary(Path(pa_str), Path(pb_str))
    except (OSError, UnicodeDecodeError) as exc:
        return rel, None, str(exc)
    child.source = FileMeta(path=rel, size=child.source.size, digest=child.source.digest)
    child.target = FileMeta(path=rel, size=child.target.size, digest=child.target.digest)
    return rel, child, None


def _diff_all_modified(
    root_a: Path, root_b: Path, modified: list[str], opts: TreeOptions
) -> tuple[dict[str, DiffResult], dict[str, str]]:
    """Text-diff modified files (parallel); unreadable files yield errors."""
    children: dict[str, DiffResult] = {}
    errors: dict[str, str] = {}
    jobs = [
        (str(root_a / rel), str(root_b / rel), rel, opts.context) for rel in modified
    ]
    count = _resolve_workers(opts.workers)
    if count > 1:
        try:
            with ProcessPoolExecutor(max_workers=count) as pool:
                for rel, child, error in pool.map(_diff_one_worker, jobs):
                    if error is not None:
                        errors[rel] = error
                    elif child is not None:
                        children[rel] = child
            return children, errors
        except (OSError, ImportError):
            pass  # fall through to sequential execution
    for job in jobs:
        rel, child, error = _diff_one_worker(job)
        if error is not None:
            errors[rel] = error
        elif child is not None:
            children[rel] = child
    return children, errors


def _digest_all(
    root: Path,
    rels: list[str],
    workers: int | None,
    cache: object | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Digest *rels* under *root*; returns ({rel: digest}, {rel: error}).

    When *cache* (a :class:`atrain.core.cache.DigestCache`) is given,
    entries validated by size+mtime are served from it and fresh digests
    are written back.
    """
    digests: dict[str, str] = {}
    errors: dict[str, str] = {}
    if not rels:
        return digests, errors

    from atrain.core.cache import stat_key

    pending: list[str] = []
    for rel in rels:
        abs_path = root / rel
        if cache is not None:
            key = stat_key(abs_path)
            if key is not None:
                cached = cache.get(abs_path, key[0], key[1])  # type: ignore[attr-defined]
                if cached is not None:
                    digests[rel] = cached
                    continue
        pending.append(rel)

    jobs = [str(root / rel) for rel in pending]
    count = _resolve_workers(workers)
    if count > 1:
        try:
            with ProcessPoolExecutor(max_workers=count) as pool:
                for path_str, digest, error in pool.map(_hash_one, jobs, chunksize=32):
                    rel = os.path.relpath(path_str, root).replace(os.sep, "/")
                    if error is not None:
                        errors[rel] = error
                    elif digest is not None:
                        digests[rel] = digest
                        _cache_store(cache, root, rel, digest)
            return digests, errors
        except (OSError, ImportError):
            # Pool unavailable (e.g. restricted sandbox): fall through to
            # sequential execution rather than failing the comparison.
            pass
    for path_str in jobs:
        rel = os.path.relpath(path_str, root).replace(os.sep, "/")
        _path, digest, error = _hash_one(path_str)
        if error is not None:
            errors[rel] = error
        elif digest is not None:
            digests[rel] = digest
            _cache_store(cache, root, rel, digest)
    return digests, errors


def _cache_store(cache: object | None, root: Path, rel: str, digest: str) -> None:
    """Best-effort cache write; the cache never breaks a comparison."""
    if cache is None:
        return
    from atrain.core.cache import stat_key

    key = stat_key(root / rel)
    if key is None:
        return
    try:
        cache.put(root / rel, key[0], key[1], digest)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return
