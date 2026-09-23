"""Render the short illustrated README demo.

Run with: uv run --no-project --with pillow python scripts/build_demo.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
SCALE = 2
WIDTH, HEIGHT = 960, 530
FONT = next(
    (str(path) for path in (
        Path("/System/Library/Fonts/HelveticaNeue.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ) if path.exists()),
    "DejaVuSans.ttf",
)
MONO = next(
    (str(path) for path in (
        Path("/System/Library/Fonts/Menlo.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("C:/Windows/Fonts/consola.ttf"),
    ) if path.exists()),
    "DejaVuSansMono.ttf",
)

BG = "#0C1020"
PANEL = "#171D30"
BORDER = "#34405B"
TEXT = "#F5F6FF"
MUTED = "#A9B3D0"
VIOLET = "#AAA9FF"
CORAL = "#FA6869"


def font(size: int, *, mono: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO if mono else FONT, size * SCALE)


def box(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], fill: str,
        outline: str | None = None, radius: int = 16, width: int = 1) -> None:
    draw.rounded_rectangle(
        tuple(value * SCALE for value in bounds),
        radius=radius * SCALE,
        fill=fill,
        outline=outline,
        width=width * SCALE,
    )


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
          color: str = TEXT, *, mono: bool = False, stroke: int = 0) -> None:
    draw.text((xy[0] * SCALE, xy[1] * SCALE), value, font=font(size, mono=mono),
              fill=color, stroke_width=stroke * SCALE, stroke_fill=color)


def frame(stage: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
    draw = ImageDraw.Draw(image)

    # A restrained app frame keeps the example distinct from an actual screenshot.
    box(draw, (8, 8, WIDTH - 8, HEIGHT - 8), BG, BORDER, 24)
    draw.line((8 * SCALE, 60 * SCALE, (WIDTH - 8) * SCALE, 60 * SCALE),
              fill=BORDER, width=SCALE)
    for x, color in ((35, CORAL), (55, "#F6B84A"), (75, "#53CA89")):
        draw.ellipse(((x - 5) * SCALE, 29 * SCALE, (x + 5) * SCALE, 39 * SCALE),
                     fill=color)
    label(draw, (104, 21), "YouTube Transcript MCP", 19, TEXT)
    label(draw, (748, 25), "ILLUSTRATED EXAMPLE", 12, MUTED, mono=True)

    box(draw, (52, 86, 908, 207), PANEL, BORDER)
    box(draw, (72, 107, 103, 138), "#303B59", radius=9)
    label(draw, (81, 109), "Y", 19, TEXT)
    label(draw, (119, 105), "YOU", 12, MUTED, mono=True)
    label(draw, (119, 130), "What is a language model? Show me the exact moment.",
          23, TEXT)
    box(draw, (119, 169, 139, 183), CORAL, radius=4)
    draw.polygon([(127 * SCALE, 172 * SCALE), (127 * SCALE, 180 * SCALE),
                  (134 * SCALE, 176 * SCALE)], fill=TEXT)
    label(draw, (149, 166), "Let's build GPT · Andrej Karpathy", 16, MUTED)

    draw.line((87 * SCALE, 208 * SCALE, 87 * SCALE, 391 * SCALE),
              fill="#384466", width=2 * SCALE)

    if stage >= 1:
        box(draw, (52, 225, 908, 295), PANEL, BORDER)
        box(draw, (72, 243, 104, 275), "#454573", radius=10)
        label(draw, (83, 246), "1", 18, TEXT)
        label(draw, (120, 236), "youtube_video_info", 18, VIOLET, mono=True)
        label(draw, (120, 263), "Title, chapters and captions found", 17, MUTED)
        label(draw, (824, 247), "READY", 12, "#70D9AA", mono=True)

    if stage >= 2:
        box(draw, (52, 312, 908, 382), PANEL, BORDER)
        box(draw, (72, 330, 104, 362), "#454573", radius=10)
        label(draw, (82, 333), "2", 18, TEXT)
        label(draw, (120, 323), "youtube_transcript", 18, VIOLET, mono=True)
        label(draw, (120, 350), 'Search: "language model"  ·  passage at 01:38',
              17, MUTED)
        label(draw, (824, 334), "READY", 12, "#70D9AA", mono=True)

    if stage >= 3:
        box(draw, (52, 399, 908, 500), "#222842", "#7777C4", 17)
        label(draw, (74, 410), "ANSWER", 12, VIOLET, mono=True)
        label(draw, (74, 436), "It models how words or tokens follow one another.",
              22, TEXT)
        box(draw, (665, 409, 887, 443), "#393D73", "#7777C4", 9)
        label(draw, (692, 415), "Watch at 01:38", 16, "#DAD9FF")

    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def main() -> None:
    stages = [frame(stage) for stage in range(4)]
    stages[-1].save(OUT / "demo.png")
    stages[0].save(
        OUT / "demo.gif",
        save_all=True,
        append_images=stages[1:],
        duration=[1000, 1100, 1100, 3000],
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUT / 'demo.gif'} and {OUT / 'demo.png'}")


if __name__ == "__main__":
    main()
