"""Generate the README screenshots.

Runs real ``atrain`` commands against the fixtures in ``docs/demo`` and
renders the captured terminal output (ANSI colours included) into PNG
"terminal windows" under ``Img/screenshots``.  No browser or native
libraries are needed — only Pillow and the DejaVu Sans Mono font.

    python docs/screenshots/make_screenshots.py

The TUI screenshot is produced headlessly with Textual's own screenshot
facility (SVG).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "docs" / "demo"
OUT = ROOT / "Img" / "screenshots"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

# ------------------------------------------------------------ theme

BG = (24, 26, 32)
FG = (205, 214, 224)
DIM_FG = (120, 128, 140)
PROMPT = (137, 180, 250)
TITLE_BG = (38, 41, 50)
TITLE_FG = (150, 158, 170)
PALETTE = {
    30: (60, 64, 72), 31: (243, 112, 112), 32: (120, 210, 130), 33: (240, 200, 90),
    34: (120, 160, 255), 35: (210, 130, 230), 36: (100, 210, 230), 37: FG,
    90: DIM_FG, 91: (255, 140, 140), 92: (150, 230, 160), 93: (255, 220, 120),
    94: (150, 180, 255), 95: (230, 160, 240), 96: (130, 230, 245), 97: (255, 255, 255),
}
FONT_SIZE = 15
LINE_H = 22
PAD_X, PAD_Y = 18, 14
TITLE_H = 34

_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _font(bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), FONT_SIZE)


FONT, FONT_B = _font(), _font(True)
CHAR_W = FONT.getlength("M")


def parse_ansi(line: str) -> list[tuple[str, tuple[int, int, int], bool]]:
    """Split one line into (text, colour, bold) runs."""
    runs: list[tuple[str, tuple[int, int, int], bool]] = []
    color, bold, dim = FG, False, False
    pos = 0
    for m in _SGR.finditer(line):
        if m.start() > pos:
            runs.append((line[pos:m.start()], DIM_FG if dim and color == FG else color, bold))
        for code in (m.group(1) or "0").split(";"):
            n = int(code or 0)
            if n == 0:
                color, bold, dim = FG, False, False
            elif n == 1:
                bold = True
            elif n == 2:
                dim = True
            elif n == 22:
                bold = dim = False
            elif n == 39:
                color = FG
            elif n in PALETTE:
                color = PALETTE[n]
        pos = m.end()
    if pos < len(line):
        runs.append((line[pos:], DIM_FG if dim and color == FG else color, bold))
    return runs


def render_terminal(
    blocks: list[tuple[str, str]], path: Path, title: str, cols: int = 100, max_rows: int = 60
) -> None:
    """``blocks`` = [(command, output), ...] rendered as one terminal window."""
    lines: list[list[tuple[str, tuple[int, int, int], bool]]] = []
    for cmd, output in blocks:
        lines.append([("$ ", PROMPT, True), (cmd, (255, 255, 255), True)])
        for raw in output.rstrip("\n").split("\n"):
            raw = raw.expandtabs(4)
            lines.append(parse_ansi(raw))
        lines.append([])
    if lines and not lines[-1]:
        lines.pop()
    if len(lines) > max_rows:
        lines = lines[:max_rows] + [[("… (output truncated)", DIM_FG, False)]]

    width = int(PAD_X * 2 + CHAR_W * cols)
    height = TITLE_H + PAD_Y * 2 + LINE_H * len(lines)
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    # title bar with traffic lights
    d.rectangle([0, 0, width, TITLE_H], fill=TITLE_BG)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        x = 16 + i * 22
        d.ellipse([x, 11, x + 12, 23], fill=c)
    tw = FONT.getlength(title)
    d.text(((width - tw) / 2, 8), title, font=FONT, fill=TITLE_FG)

    y = TITLE_H + PAD_Y
    for runs in lines:
        x = float(PAD_X)
        for text, color, bold in runs:
            f = FONT_B if bold else FONT
            d.text((x, y), text, font=f, fill=color)
            x += f.getlength(text)
        y += LINE_H
    img.save(path, optimize=True)
    print(f"wrote {path.relative_to(ROOT)}  ({len(lines)} rows)")


# ------------------------------------------------------------ helpers


def run(cmd: list[str], cwd: Path, env_extra: dict[str, str] | None = None) -> str:
    env = {**os.environ, "COLUMNS": "100", **(env_extra or {})}
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    return proc.stdout + (proc.stderr if proc.returncode == 2 else "")


def shown(cmd: list[str]) -> str:
    return " ".join(cmd)


def atrain(*args: str, cwd: Path = DEMO) -> tuple[str, str]:
    cmd = ["atrain", *args]
    return shown(cmd), run(cmd, cwd)


# ------------------------------------------------------------ scenes


def scene_help() -> None:
    render_terminal(
        [("atrain --help", run(["atrain", "--help"], DEMO))],
        OUT / "help.png", "atrain --help", cols=84, max_rows=70,
    )


def scene_text() -> None:
    render_terminal(
        [atrain("app_v1.py", "app_v2.py", "--format", "color", "--color", "always")],
        OUT / "text-color.png", "text mode — colored output", cols=90,
    )
    render_terminal(
        [atrain("app_v1.py", "app_v2.py")],
        OUT / "text-unified.png", "text mode — patch-compatible unified diff", cols=90,
        max_rows=46,
    )
    render_terminal(
        [atrain("app_v1.py", "app_v2.py", "--format", "side", "--width", "110")],
        OUT / "text-side.png", "text mode — side by side", cols=112, max_rows=48,
    )


def scene_auto() -> None:
    render_terminal(
        [
            atrain("config_v1.json", "config_v2.json"),
            atrain("orders_jan.csv", "orders_feb.csv", "--key-col", "order_id"),
            atrain("firmware_v1.bin", "firmware_v2.bin"),
        ],
        OUT / "auto-modes.png", "auto-detected modes: JSON · CSV · binary", cols=96,
    )


def scene_dir() -> None:
    cmd, out = atrain("release-1.0", "release-2.0", "--format", "color", "--color", "always")
    render_terminal([(cmd, out)], OUT / "dir-mode.png", "directory tree comparison", cols=92,
                    max_rows=42)


def scene_json_output() -> None:
    cmd, out = atrain("config_v1.json", "config_v2.json", "--format", "json")
    render_terminal([(cmd + " | head -40", "\n".join(out.splitlines()[:40]))],
                    OUT / "json-output.png", "machine-readable JSON for CI", cols=90,
                    max_rows=44)


def scene_ignore() -> None:
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.txt"
        b = Path(td) / "b.txt"
        a.write_text("# header\nHello World\n  indented line\nstable\n")
        b.write_text("# HEADER changed\nhello world\nindented   line\nstable\n")
        blocks = [
            ("atrain a.txt b.txt", run(["atrain", "a.txt", "b.txt"], Path(td))),
            ("atrain a.txt b.txt --ignore-case --ignore-space --ignore-matching '^#'",
             run(["atrain", "a.txt", "b.txt", "--ignore-case", "--ignore-space",
                  "--ignore-matching", "^#"], Path(td)) or "(no output — exit code 0)"),
            ("echo $?", "0"),
        ]
    render_terminal(blocks, OUT / "ignore-options.png", "GNU-compatible ignore options",
                    cols=84)


def scene_git() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "shop"
        repo.mkdir()
        g = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
        g("init", "-q", "-b", "main")
        g("config", "user.email", "dev@example.com")
        g("config", "user.name", "dev")
        g("config", "commit.gpgsign", "false")
        shutil.copy(DEMO / "app_v1.py", repo / "app.py")
        shutil.copy(DEMO / "config_v1.json", repo / "config.json")
        g("add", ".")
        g("commit", "-qm", "release 1.0")
        g("tag", "v1.0")
        shutil.copy(DEMO / "app_v2.py", repo / "app.py")
        shutil.copy(DEMO / "config_v2.json", repo / "config.json")
        g("commit", "-qam", "release 2.0")
        g("tag", "v2.0")
        (repo / "app.py").write_text(
            (repo / "app.py").read_text().replace("4.90", "3.90"), encoding="utf-8"
        )
        blocks = [
            ("atrain --git HEAD app.py",
             run(["atrain", "--git", "HEAD", "app.py", "--format", "color", "--color",
                  "always"], repo)),
            ("atrain --git v1.0..v2.0 config.json",
             run(["atrain", "--git", "v1.0..v2.0", "config.json"], repo)),
        ]
        render_terminal(blocks, OUT / "git-revisions.png",
                        "git: compare against history", cols=88)

        # git never allocates a TTY for external diffs → force colour explicitly
        ext = run(["git", "-c", "diff.external=atrain --color always", "diff",
                   "v1.0", "v2.0", "--", "config.json", "app.py"], repo)
        blocks = [
            ("git config diff.external atrain", ""),
            ("git diff v1.0 v2.0 -- config.json app.py", ext),
        ]
        render_terminal(blocks, OUT / "git-external.png",
                        "git diff routed through A-Train", cols=88, max_rows=56)


def scene_watch() -> None:
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "service.yaml"
        b = Path(td) / "service.local.yaml"
        a.write_text("replicas: 2\nimage: shop:1.4\nport: 8080\n")
        b.write_text("replicas: 2\nimage: shop:1.4\nport: 8080\n")
        proc = subprocess.Popen(
            ["atrain", "--watch", "both", "--watch-interval", "0.2", str(a.name), str(b.name)],
            cwd=td, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**os.environ, "COLUMNS": "100"},
        )
        time.sleep(0.8)
        b.write_text("replicas: 3\nimage: shop:1.4\nport: 8080\n")
        time.sleep(0.8)
        b.write_text("replicas: 3\nimage: shop:1.5\nport: 8080\n")
        time.sleep(0.8)
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    out = out.replace(td + "/", "")
    render_terminal(
        [("atrain --watch both service.yaml service.local.yaml", out)],
        OUT / "watch-mode.png", "watch mode — live alerts on change", cols=88,
    )


def scene_tui() -> None:
    import asyncio

    from atrain.tui.app import DiffTui

    async def shoot() -> None:
        app = DiffTui(DEMO / "app_v1.py", DEMO / "app_v2.py")
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("n")
            await pilot.pause()
            app.save_screenshot(filename="tui.svg", path=str(OUT))

    asyncio.run(shoot())
    print("wrote Img/screenshots/tui.svg")


def scene_html() -> None:
    sample = ROOT / "docs" / "demo" / "report.html"
    run(["atrain", "app_v1.py", "app_v2.py", "--format", "html", "-o", str(sample)], DEMO)
    print(f"wrote {sample.relative_to(ROOT)}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = [scene_help, scene_text, scene_auto, scene_dir, scene_json_output,
              scene_ignore, scene_git, scene_watch, scene_tui, scene_html]
    only = set(sys.argv[1:])
    for scene in scenes:
        name = scene.__name__.removeprefix("scene_")
        if only and name not in only:
            continue
        scene()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
