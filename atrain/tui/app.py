"""Textual application showing a color-coded unified diff view.

The diff is rendered as a *single* scrollable stream — one scroll view is
inherently synchronized between the two inputs — with keyboard navigation
across hunks (n/p), line scrolling (j/k), top/bottom jumps (g/G) and a
live refresh (r).  All comparison logic comes from the same core the CLI
uses; the TUI is presentation-only.
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.widgets import Footer, Header, Static

from atrain.core.diff_text import compare_files
from atrain.core.models import DiffResult, FileMeta, LineTag
from atrain.core.reader import load_bytes

_STYLE = {
    LineTag.CONTEXT: "",
    LineTag.DELETE: "red",
    LineTag.INSERT: "green",
}


def diff_segments(result: DiffResult) -> list[tuple[str, str]]:
    """Flat (style, text) pairs; one pair per rendered row, hunk first."""
    segments: list[tuple[str, str]] = []
    for hunk in result.hunks:
        header = (
            f"@@ -{hunk.a_start + 1},{hunk.a_count} "
            f"+{hunk.b_start + 1},{hunk.b_count} @@"
        )
        segments.append(("cyan", header))
        for line in hunk.lines:
            prefix = "  " if line.tag is LineTag.CONTEXT else line.tag.value + " "
            segments.append((_STYLE[line.tag], f"{prefix}{line.text}"))
    return segments


class DiffTui(App[None]):
    """Interactive diff viewer for two files."""

    CSS = """
    #body { padding: 0 1; }
    #diff { width: 100%; }
    #status {
        dock: bottom;
        height: 1;
        background: $panel;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "next_hunk", "Next hunk"),
        Binding("p", "prev_hunk", "Previous hunk"),
        Binding("j,down", "scroll_down", "Down", show=False),
        Binding("k,up", "scroll_up", "Up", show=False),
        Binding("g,home", "scroll_home", "Top", show=False),
        Binding("G,end", "scroll_end", "Bottom", show=False),
        Binding("r", "refresh", "Reload files"),
    ]

    def __init__(self, path_a: Path, path_b: Path) -> None:
        super().__init__()
        self.path_a = path_a
        self.path_b = path_b
        self.result: DiffResult | None = None
        self.hunk_rows: list[int] = []  # rendered row index of each hunk header
        self.cursor = -1  # index into hunk_rows
        self.error: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with ScrollableContainer(id="body"):
            yield Static("", id="diff")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._recompute()

    def action_refresh(self) -> None:
        self._recompute()

    def action_next_hunk(self) -> None:
        if self.hunk_rows:
            self.cursor = (self.cursor + 1) % len(self.hunk_rows)
            self._jump()

    def action_prev_hunk(self) -> None:
        if self.hunk_rows:
            self.cursor = (self.cursor - 1) % len(self.hunk_rows)
            self._jump()

    def action_scroll_down(self) -> None:
        self.query_one("#body", ScrollableContainer).scroll_down(animate=False)

    def action_scroll_up(self) -> None:
        self.query_one("#body", ScrollableContainer).scroll_up(animate=False)

    def action_scroll_home(self) -> None:
        self.query_one("#body", ScrollableContainer).scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        self.query_one("#body", ScrollableContainer).scroll_end(animate=False)

    def _recompute(self) -> None:
        view = self.query_one("#diff", Static)
        status = self.query_one("#status", Static)
        try:
            with load_bytes(self.path_a) as raw_a, load_bytes(self.path_b) as raw_b:
                identical = raw_a.data == raw_b.data
            result = (
                DiffResult(
                    mode="text",
                    source=FileMeta(path=str(self.path_a)),
                    target=FileMeta(path=str(self.path_b)),
                    identical=True,
                )
                if identical
                else compare_files(self.path_a, self.path_b)
            )
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            self.result = None
            view.update(Text(f"error: {self.error}", style="red"))
            status.update(f"{self.path_a} ↔ {self.path_b} — error")
            return

        self.error = None
        self.result = result
        segments = diff_segments(result)
        self.hunk_rows = [row for row, (_s, text) in enumerate(segments) if text.startswith("@@")]
        self.cursor = -1
        if not segments:
            view.update(Text("Files are identical.", style="bold green"))
            status.update(f"{self.path_a.name} ↔ {self.path_b.name} — identical")
            return
        rich_text = Text()
        for style, chunk in segments:
            rich_text.append(chunk + "\n", style=style or None)
        view.update(rich_text)
        status.update(
            f"{self.path_a.name} ↔ {self.path_b.name} — {len(self.hunk_rows)} hunk(s)  "
            "(n/p hunks · j/k scroll · r reload · q quit)"
        )

    def _jump(self) -> None:
        if not self.hunk_rows:
            return
        target = self.hunk_rows[self.cursor]
        self.query_one("#body", ScrollableContainer).scroll_to(y=target, animate=False)
        self.query_one("#status", Static).update(
            f"hunk {self.cursor + 1}/{len(self.hunk_rows)}"
        )


def run(path_a: Path, path_b: Path) -> None:
    """Entry point used by the CLI; raises ImportError with a hint."""
    try:
        import textual  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ImportError(
            "The TUI needs the optional dependency 'textual'. "
            "Install it with: pip install textual"
        ) from exc
    DiffTui(path_a, path_b).run()
