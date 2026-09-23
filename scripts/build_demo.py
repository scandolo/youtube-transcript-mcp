"""Render an illustrated Claude-style conversation for the README.

Run with: uv run --no-project --with pillow python scripts/build_demo.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
SCALE = 2
WIDTH, HEIGHT = 1000, 760


def first_font(*paths: str) -> str:
    return next((path for path in paths if Path(path).exists()), paths[-1])


SANS = first_font(
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "DejaVuSans.ttf",
)
SERIF = first_font(
    "/System/Library/Fonts/Times.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "C:/Windows/Fonts/georgia.ttf",
    "DejaVuSerif.ttf",
)
MONO = first_font(
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "DejaVuSansMono.ttf",
)

WHITE = "#FFFFFF"
INK = "#25231F"
MUTED = "#777673"
LINE = "#E7E3DF"
USER = "#F3F3F2"
TOOL = "#FAF9F7"
ORANGE = "#D97757"
BLUE = "#2E61A7"
GREEN = "#34835B"


def font(size: int, family: str = SANS) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(family, size * SCALE)


def text(draw: ImageDraw.ImageDraw, x: int, y: int, value: str, size: int,
         color: str = INK, family: str = SANS) -> None:
    draw.text((x * SCALE, y * SCALE), value, fill=color, font=font(size, family))


def rounded(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], fill: str,
            radius: int = 13, outline: str | None = None) -> None:
    draw.rounded_rectangle(tuple(n * SCALE for n in bounds), radius=radius * SCALE,
                           fill=fill, outline=outline, width=SCALE)


def tool_card(draw: ImageDraw.ImageDraw, top: int, name: str, detail: str,
              *, running: bool) -> None:
    rounded(draw, (102, top, 923, top + 81), TOOL, radius=12, outline=LINE)
    draw.line((102 * SCALE, (top + 39) * SCALE, 923 * SCALE, (top + 39) * SCALE),
              fill=LINE, width=SCALE)
    text(draw, 121, top + 9, "Called", 15, MUTED)
    rounded(draw, (178, top + 8, 178 + len(name) * 10 + 18, top + 32), "#E8F4EF", 5)
    text(draw, 187, top + 10, name, 14, "#2A7355", MONO)
    text(draw, 844 if running else 861, top + 10,
         "running" if running else "done", 14, MUTED if running else GREEN)
    text(draw, 121, top + 49, detail, 15, "#585854", MONO)


def frame(stage: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), WHITE)
    draw = ImageDraw.Draw(image)

    # App chrome and composer are kept still while the conversation progresses.
    draw.rectangle((0, 0, WIDTH * SCALE, 55 * SCALE), fill="#FBFAF8")
    draw.line((0, 55 * SCALE, WIDTH * SCALE, 55 * SCALE), fill=LINE, width=SCALE)
    for x, color in ((26, "#FF625C"), (47, "#FFBE31"), (68, "#2FC64E")):
        draw.ellipse(((x - 5) * SCALE, 22 * SCALE, (x + 5) * SCALE, 32 * SCALE),
                     fill=color)
    text(draw, 101, 16, "Claude", 18, INK, SERIF)
    text(draw, 725, 19, "Illustrated example · local MCP", 13, MUTED)

    rounded(draw, (221, 77, 934, 174), USER, radius=17)
    text(draw, 243, 91, "Use YouTube Transcript to explain what a", 20)
    text(draw, 243, 119, "language model is in this video:", 20)
    text(draw, 243, 146, "youtube.com/watch?v=kCc8FmEb1nY", 17, BLUE)
    draw.line((243 * SCALE, 170 * SCALE, 591 * SCALE, 170 * SCALE),
              fill=BLUE, width=SCALE)

    if stage >= 1:
        text(draw, 85, 203, "Claude", 15, MUTED)
        text(draw, 85, 228, "I’ll check the video and find the exact passage.",
             22, INK, SERIF)
        if stage == 1:
            text(draw, 102, 278, "Thinking...", 16, MUTED)
        else:
            text(draw, 102, 278, "Thought for a moment · locating the definition", 15, MUTED)

    if stage >= 2:
        tool_card(draw, 315, "youtube_video_info",
                  "video: Let's build GPT  ·  captions available", running=stage == 2)

    if stage >= 3:
        tool_card(draw, 409, "youtube_transcript",
                  'query: "language model"  ·  block starts at 01:21', running=stage == 3)

    if stage >= 4:
        text(draw, 85, 524, "Claude", 15, MUTED)
        text(draw, 85, 552,
             "Karpathy describes a language model as a system that models",
             22, INK, SERIF)
        if stage == 4:
            text(draw, 85, 584, "how words or tokens follow one another...", 22, INK, SERIF)
        else:
            text(draw, 85, 584, "how words or tokens follow one another.", 22, INK, SERIF)
            text(draw, 85, 622, "Watch the explanation at 01:38", 18, BLUE)
            draw.line((85 * SCALE, 648 * SCALE, 363 * SCALE, 648 * SCALE),
                      fill=BLUE, width=SCALE)

    rounded(draw, (167, 670, 833, 737), WHITE, radius=19, outline="#D8D7D4")
    text(draw, 188, 685, "Write a message...", 18, "#969593")
    text(draw, 188, 715, "+", 22, MUTED)
    text(draw, 691, 714, "Sonnet 5", 13, INK)
    text(draw, 759, 714, "Medium", 13, MUTED)

    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def main() -> None:
    stages = [frame(stage) for stage in range(6)]
    stages[-1].save(OUT / "demo.png")
    stages[0].save(
        OUT / "demo.gif",
        save_all=True,
        append_images=stages[1:],
        duration=[900, 800, 950, 1050, 700, 3100],
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUT / 'demo.gif'} and {OUT / 'demo.png'}")


if __name__ == "__main__":
    main()
