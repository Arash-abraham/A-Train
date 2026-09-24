"""A-Train TUI (ROADMAP.md, §8 v0.4).

Optional interactive front-end built on Textual.  The core stays
dependency-free: this package imports Textual lazily and the CLI reports
a friendly installation hint when it is missing.
"""

from atrain.tui.app import DiffTui

__all__ = ["DiffTui"]
