"""Render the README's demo GIF and screenshots from real ``cos`` runs.

python docs/render_assets.py   # writes docs/images/{demo.gif,digest.png,eval.png}
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from rich.cells import cell_len
from rich.color import Color
from rich.console import Console
from rich.segment import Segment
from rich.style import Style
from rich.terminal_theme import TerminalTheme
from rich.text import Text

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
COLS, ROWS, PAD, BAR, LINE = 118, 36, 22, 38, 20
THEME = TerminalTheme(
    (13, 17, 23),
    (201, 209, 217),
    [
        (72, 79, 88),
        (255, 123, 114),
        (63, 185, 80),
        (210, 153, 34),
        (88, 166, 255),
        (188, 140, 255),
        (57, 197, 207),
        (177, 186, 196),
    ],
    [
        (110, 118, 129),
        (255, 161, 152),
        (86, 211, 100),
        (227, 179, 65),
        (121, 192, 255),
        (210, 168, 255),
        (86, 212, 221),
        (240, 246, 252),
    ],
)
REGULAR = ImageFont.truetype("DejaVuSansMono.ttf", 14)
BOLD = ImageFont.truetype("DejaVuSansMono-Bold.ttf", 14)
FALLBACK = ImageFont.truetype("DejaVuSans.ttf", 14)
CELL = REGULAR.getlength("M")
PROMPT = Style(color="green", bold=True)
COMMANDS = [
    "cos run --slack datasets/samples/slack.json --email datasets/samples/email.json "
    "--ledger .cos/ledger.sqlite",
    "cos ledger show --path .cos/ledger.sqlite --status all",
    "cos eval --split test --backend heuristic --bootstrap 300",
]

Screen = list[list[Segment]]
_BOX = {
    "─": "lr",
    "━": "LR",
    "│": "ud",
    "┃": "UD",
    "┌": "rd",
    "┐": "ld",
    "└": "ru",
    "┘": "lu",
    "├": "udr",
    "┤": "udl",
    "┬": "lrd",
    "┴": "lru",
    "┼": "lrud",
    "┏": "RD",
    "┓": "LD",
    "┗": "RU",
    "┛": "LU",
    "┳": "LRD",
    "┻": "LRU",
    "┣": "UDR",
    "┫": "UDL",
    "╋": "LRUD",
    "┡": "UdR",
    "┩": "UdL",
    "╇": "LRUd",
    "╈": "LRuD",
}
console = Console(width=COLS, color_system="truecolor", force_terminal=True)


def capture(command: str, cwd: Path) -> Text:
    env = {**os.environ, "FORCE_COLOR": "1", "COLUMNS": str(COLS), "TERM": "xterm-256color"}
    env.pop("NO_COLOR", None)
    result = subprocess.run(
        command, shell=True, cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    shown = [
        line
        for line in result.stdout.splitlines()
        if not Text.from_ansi(line).plain.strip().startswith("Extracting")
    ]
    while shown and not Text.from_ansi(shown[0]).plain.strip():
        shown.pop(0)
    return Text.from_ansi("\n".join(shown))


def lines(text: Text) -> Screen:
    return console.render_lines(text, console.options.update(width=COLS), pad=False)


def rgb(color: Color | None, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if color is None or color.is_default:
        return default
    triplet = color.get_truecolor(THEME)
    return (triplet.red, triplet.green, triplet.blue)


def draw_box(
    canvas: ImageDraw.ImageDraw, char: str, x: float, y: int, fill: tuple[int, ...]
) -> None:
    left, right = round(x), round(x + CELL)
    mid_x, mid_y = round(x + CELL / 2), y + LINE // 2
    for part in _BOX[char]:
        size = 2 if part.isupper() else 1
        spans = {
            "l": (left, mid_y, mid_x + size, mid_y + size),
            "r": (mid_x, mid_y, right, mid_y + size),
            "u": (mid_x, y, mid_x + size, mid_y + size),
            "d": (mid_x, mid_y, mid_x + size, y + LINE),
        }
        x0, y0, x1, y1 = spans[part.lower()]
        canvas.rectangle((x0, y0, x1 - 1, y1 - 1), fill=fill)


def draw(screen: Screen, title: str) -> Image.Image:
    width, height = int(PAD * 2 + COLS * CELL), BAR + PAD * 2 + ROWS * LINE
    image = Image.new("RGB", (width, height), (1, 4, 9))
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((0, 0, width - 1, height - 1), radius=12, fill=THEME.background_color)
    canvas.rounded_rectangle((0, 0, width - 1, BAR), radius=12, fill=(22, 27, 34))
    canvas.rectangle((0, BAR - 12, width - 1, BAR), fill=(22, 27, 34))
    for index, dot in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        canvas.ellipse((16 + index * 20, 13, 28 + index * 20, 25), fill=dot)
    canvas.text((width / 2, BAR / 2), title, fill=(139, 148, 158), font=REGULAR, anchor="mm")
    foreground = THEME.foreground_color
    for row, segments in enumerate(screen[-ROWS:]):
        column = 0
        y = BAR + PAD + row * LINE
        for segment in segments:
            style = segment.style or Style()
            fill = rgb(style.color, (foreground.red, foreground.green, foreground.blue))
            if style.dim:
                fill = tuple((c + b) // 2 for c, b in zip(fill, (13, 17, 23), strict=True))
            font = BOLD if style.bold else REGULAR
            for char in segment.text:
                x = PAD + column * CELL
                if style.bgcolor is not None:
                    canvas.rectangle(
                        (x, y, x + CELL * cell_len(char), y + LINE),
                        fill=rgb(style.bgcolor, (13, 17, 23)),
                    )
                if char in _BOX:
                    draw_box(canvas, char, x, y, fill)
                else:
                    known = font.getmask(char).getbbox() or char == " "
                    canvas.text((x, y + 2), char, fill=fill, font=font if known else FALLBACK)
                column += cell_len(char)
    return image


def session(outputs: list[Text]) -> Iterator[tuple[Screen, int]]:
    for command, output in zip(COMMANDS, outputs, strict=True):
        for typed in range(0, len(command) + 1, 3):
            prompt = Text("$ ", style=PROMPT) + Text(command[:typed]) + Text("▌")
            yield lines(prompt), 35
        header = lines(Text("$ ", style=PROMPT) + Text(command))
        body = lines(output)
        for shown in range(0, len(body) + 1, 3):
            yield header + body[:shown], 30
        yield header + body, 2600


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "datasets").symlink_to(ROOT / "datasets")
        outputs = [capture(command, work) for command in COMMANDS]
    frames: list[Image.Image] = []
    durations: list[int] = []
    for screen, duration in session(outputs):
        frames.append(draw(screen, "cos  ·  chief-of-staff"))
        durations.append(duration)
    finals = [frame for frame, duration in zip(frames, durations, strict=True) if duration > 1000]
    sheet = Image.new("RGB", (frames[0].width, frames[0].height * len(finals)))
    for index, frame in enumerate(finals):
        sheet.paste(frame, (0, index * frame.height))
    palette = sheet.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    gif = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    gif[0].save(
        OUT / "demo.gif",
        save_all=True,
        append_images=gif[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=1,
    )
    for command, output, name in (
        (COMMANDS[0], outputs[0], "digest"),
        (COMMANDS[2], outputs[2], "eval"),
    ):
        screen = lines(Text("$ ", style=PROMPT) + Text(command)) + lines(output)
        draw(screen[:ROWS], "cos  ·  chief-of-staff").save(OUT / f"{name}.png", optimize=True)
    print(f"{len(frames)} frames -> {OUT}")


if __name__ == "__main__":
    main()
