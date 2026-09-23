"""Animate the GPT-generated Claude mock in assets/demo.png.

This script reveals sections of the finished image. It does not draw UI or text.
Run with: uv run --no-project --with pillow python scripts/build_demo.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/demo.png"
OUTPUT = ROOT / "assets/demo.gif"

# Bottom edges of each section in the generated 1536 x 1024 image.
REVEAL_EDGES = (250, 425, 545, 670, 792, 850)
HIDE_AREA = (80, 0, 1460, 855)


def frame(source: Image.Image, visible_to: int) -> Image.Image:
    image = source.copy()
    if visible_to < HIDE_AREA[3]:
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (HIDE_AREA[0], visible_to, HIDE_AREA[2], HIDE_AREA[3]),
            fill="white",
        )
    return image.resize((960, 640), Image.Resampling.LANCZOS)


def main() -> None:
    with Image.open(SOURCE) as original:
        source = original.convert("RGB")
    if source.size != (1536, 1024):
        raise SystemExit("Expected a 1536 x 1024 generated source image")

    stages = [frame(source, edge) for edge in REVEAL_EDGES]
    stages[0].save(
        OUTPUT,
        save_all=True,
        append_images=stages[1:],
        duration=[850, 900, 950, 1000, 850, 3200],
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
