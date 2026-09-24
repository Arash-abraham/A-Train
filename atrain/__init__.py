"""A-Train: a high-performance file comparison tool for developers.

Named after the fastest member of The Seven — because a diff should arrive
before you finish blinking.  See ``ROADMAP.md`` for the authoritative
development plan.
"""

from __future__ import annotations

from atrain.core.models import DiffResult, DiffStats, FileMeta, Hunk

__version__ = "0.4.0"

__all__ = ["DiffResult", "DiffStats", "FileMeta", "Hunk", "__version__"]
