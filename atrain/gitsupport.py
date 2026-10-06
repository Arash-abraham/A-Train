"""Git integration helpers.

Three ways to use A-Train together with Git are supported, all without any
dependency beyond the ``git`` executable:

1. **Revision shorthand** — ``atrain --git HEAD~1 src/app.py`` compares a
   blob from history with the working tree; ``atrain --git v1.0..v2.0 f``
   compares two revisions.  Blobs are materialised in a temporary
   directory (keeping the original file name so mode auto-detection works)
   and removed afterwards.

2. **External diff driver** — Git invokes ``GIT_EXTERNAL_DIFF`` /
   ``diff.external`` with seven (or nine, for renames) positional
   arguments.  :func:`parse_external_diff_argv` recognises that calling
   convention so ``git diff`` can be routed through A-Train with
   ``git config diff.external atrain``.

3. **difftool** — ``git difftool -x atrain`` already works because
   difftool passes exactly two paths; nothing special is needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

#: Git sets these when invoking an external diff command.
_EXTERNAL_DIFF_ENV = ("GIT_DIFF_PATH_COUNTER", "GIT_DIFF_PATH_TOTAL")
_NULL_PATH = "/dev/null"


class GitError(RuntimeError):
    """Raised when git is unavailable or a revision/path cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ExternalDiffCall:
    """The arguments Git hands to an external diff program."""

    path: str
    old_file: Path | None
    old_hex: str
    old_mode: str
    new_file: Path | None
    new_hex: str
    new_mode: str
    new_path: str | None = None
    similarity: str | None = None

    @property
    def old_label(self) -> str:
        return _NULL_PATH if self.old_file is None else f"a/{self.path}"

    @property
    def new_label(self) -> str:
        if self.new_file is None:
            return _NULL_PATH
        return f"b/{self.new_path or self.path}"


def parse_external_diff_argv(
    argv: list[str], environ: dict[str, str] | None = None
) -> ExternalDiffCall | None:
    """Return an :class:`ExternalDiffCall` if *argv* matches Git's convention.

    Git passes ``path old-file old-hex old-mode new-file new-hex new-mode``
    and, for renames/copies, ``new-path similarity-index`` as well.  We
    additionally require Git's environment markers to avoid misreading an
    ordinary seven-argument invocation.
    """
    env = os.environ if environ is None else environ
    if len(argv) not in (7, 9) or not all(k in env for k in _EXTERNAL_DIFF_ENV):
        return None
    path, old_file, old_hex, old_mode, new_file, new_hex, new_mode = argv[:7]
    extra = argv[7:]

    def _p(raw: str) -> Path | None:
        return None if raw == _NULL_PATH else Path(raw)

    return ExternalDiffCall(
        path=path,
        old_file=_p(old_file),
        old_hex=old_hex,
        old_mode=old_mode,
        new_file=_p(new_file),
        new_hex=new_hex,
        new_mode=new_mode,
        new_path=extra[0] if extra else None,
        similarity=extra[1] if extra else None,
    )


# ---------------------------------------------------------------- revisions


def _git(*args: str, cwd: Path | None = None) -> bytes:
    exe = shutil.which("git")
    if exe is None:
        raise GitError("git executable not found on PATH")
    proc = subprocess.run(
        [exe, *args], cwd=cwd, capture_output=True, check=False
    )
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed"
        raise GitError(msg)
    return proc.stdout


def repo_root(start: Path) -> Path:
    """Return the top-level directory of the repository containing *start*."""
    base = start if start.is_dir() else start.parent
    out = _git("rev-parse", "--show-toplevel", cwd=base if base.exists() else None)
    return Path(out.decode("utf-8", "replace").strip())


def repo_relative(path: Path, root: Path) -> str:
    """Repository-relative POSIX path for *path* (what ``git show`` expects)."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise GitError(f"{path} is outside the repository at {root}") from exc
    return PurePosixPath(rel).as_posix()


def show_blob(rev: str, rel_path: str, root: Path) -> bytes:
    """Return the content of *rel_path* at *rev*."""
    return _git("show", f"{rev}:{rel_path}", cwd=root)


def split_revspec(spec: str) -> tuple[str, str | None]:
    """``"A..B"`` → ``("A", "B")``; ``"A"`` → ``("A", None)``; ``""`` → HEAD."""
    if ".." in spec:
        left, _, right = spec.partition("..")
        right = right.lstrip(".")  # tolerate the three-dot form
        return (left or "HEAD", right or "HEAD")
    return (spec or "HEAD", None)


@dataclass(slots=True)
class RevisionPair:
    """Two paths ready for comparison plus the labels to print for them."""

    source: Path
    target: Path
    source_label: str
    target_label: str
    _tmpdir: tempfile.TemporaryDirectory[str] | None = None

    def cleanup(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None

    def __enter__(self) -> RevisionPair:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cleanup()


def materialise(spec: str, path: Path) -> RevisionPair:
    """Resolve ``--git SPEC PATH`` into two on-disk files.

    * ``SPEC`` = ``REV`` → ``REV:PATH`` versus the working-tree *path*.
    * ``SPEC`` = ``REV1..REV2`` → ``REV1:PATH`` versus ``REV2:PATH``.
    """
    root = repo_root(path)
    rel = repo_relative(path, root)
    left, right = split_revspec(spec)
    tmp = tempfile.TemporaryDirectory(prefix="atrain-git-")
    tmp_root = Path(tmp.name)
    try:
        src = tmp_root / "a" / path.name
        src.parent.mkdir(parents=True)
        src.write_bytes(show_blob(left, rel, root))
        src_label = f"{rel}@{left}"
        if right is None:
            if not path.is_file():
                raise GitError(f"{path}: not a file in the working tree")
            tgt, tgt_label = path, str(path)
        else:
            tgt = tmp_root / "b" / path.name
            tgt.parent.mkdir(parents=True)
            tgt.write_bytes(show_blob(right, rel, root))
            tgt_label = f"{rel}@{right}"
    except Exception:
        tmp.cleanup()
        raise
    return RevisionPair(src, tgt, src_label, tgt_label, tmp)


SETUP_SNIPPET = """\
# Route `git diff` through A-Train (per repository; add --global for all repos)
git config diff.external atrain

# Or keep `git diff` as is and use A-Train on demand
git difftool -x atrain            # two-pane in the terminal
git difftool -x 'atrain --format side'
git config alias.adiff 'difftool -x atrain -y'

# Compare a file against history without touching git config
atrain --git HEAD~1 path/to/file
atrain --git v1.0..v2.0 path/to/file --format side
"""

__all__ = [
    "ExternalDiffCall",
    "GitError",
    "RevisionPair",
    "SETUP_SNIPPET",
    "materialise",
    "parse_external_diff_argv",
    "repo_relative",
    "repo_root",
    "show_blob",
    "split_revspec",
]
