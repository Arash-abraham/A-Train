"""Optional digest cache for repeated comparisons (ROADMAP.md, §3.7).

Maps ``(path, size, mtime_ns)`` to a BLAKE2b digest so development loops
that compare the same trees repeatedly skip re-hashing unchanged files.
Stored as JSON (sorted keys, atomic tmp+rename write).  A corrupt or
unreadable cache is discarded silently — the cache is an accelerator,
never a source of truth: entries are validated against size and mtime_ns
before use.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

CACHE_VERSION = 1
MAX_ENTRIES = 100_000


def default_cache_path() -> Path:
    """``$XDG_CACHE_HOME/atrain/hashes.json`` or ``~/.cache/...``."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "atrain" / "hashes.json"


class DigestCache:
    """File-backed digest cache with size+mtime validation."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_cache_path()
        self.entries: dict[str, list[int | str]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
            return
        entries = raw.get("entries")
        if isinstance(entries, dict):
            self.entries = entries

    def get(self, path: Path, size: int, mtime_ns: int) -> str | None:
        """Validated digest lookup; ``None`` on miss or stale entry."""
        entry = self.entries.get(str(path))
        if entry is None or len(entry) != 3:
            return None
        cached_size, cached_mtime, digest = entry
        if cached_size == size and cached_mtime == mtime_ns and isinstance(digest, str):
            return digest
        return None

    def put(self, path: Path, size: int, mtime_ns: int, digest: str) -> None:
        self.entries[str(path)] = [size, mtime_ns, digest]
        self._dirty = True

    def save(self) -> None:
        """Persist atomically; prunes to ``MAX_ENTRIES`` newest-by-path."""
        if not self._dirty:
            return
        if len(self.entries) > MAX_ENTRIES:
            keep = sorted(self.entries.items(), key=lambda kv: kv[0])[-MAX_ENTRIES:]
            self.entries = dict(keep)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": CACHE_VERSION, "entries": self.entries}
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".hashes-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, sort_keys=True)
            os.replace(tmp_name, self.path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            # A cache that cannot be written is not an error.
        self._dirty = False


def stat_key(path: Path) -> tuple[int, int] | None:
    """``(size, mtime_ns)`` for cache validation, or None on OSError."""
    try:
        info = path.stat()
    except OSError:
        return None
    return info.st_size, info.st_mtime_ns
