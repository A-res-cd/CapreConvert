"""Generate the original CapreConvert CC icon from geometry, without external assets."""

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw_icon():
    scale = 32
    image = Image.new("RGBA", (40 * scale, 40 * scale))
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((0, 0, 40 * scale - 1, 40 * scale - 1), radius=8 * scale, fill="#2E3F92")
    radius, half_height = 9, 8
    horizontal = math.sqrt(radius**2 - half_height**2)
    start = math.atan2(half_height, horizontal)
    end = 2 * math.pi - start
    stroke = 4.5 * scale
    # Match the frontend's original SVG C arcs and round end caps. Draw the second
    # orange C last so its overlap follows the vector mark's stacking order.
    for endpoint, color in ((21, "#FDFCF7"), (30, "#F39C12")):
        center = endpoint - horizontal
        outer = radius * scale + stroke / 2
        canvas.arc(
            (
                center * scale - outer,
                20 * scale - outer,
                center * scale + outer,
                20 * scale + outer,
            ),
            start=math.degrees(start),
            end=math.degrees(end),
            fill=color,
            width=round(stroke),
        )
        endpoints = [
            (
                (center + radius * math.cos(angle)) * scale,
                (20 + radius * math.sin(angle)) * scale,
            )
            for angle in (start, end)
        ]
        for x, y in endpoints:
            canvas.ellipse((x - stroke / 2, y - stroke / 2, x + stroke / 2, y + stroke / 2), fill=color)
    return image


def main():
    parser = argparse.ArgumentParser(description="Generate the original CapreConvert Windows CC icon")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "packaging" / "assets" / "capreconvert.ico"
    )
    parser.add_argument("--preview", type=Path)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with draw_icon() as source:
        with source.resize((256, 256), Image.Resampling.LANCZOS) as image:
            image.save(arguments.output, format="ICO", sizes=[(size, size) for size in SIZES])
            if arguments.preview:
                arguments.preview.parent.mkdir(parents=True, exist_ok=True)
                image.save(arguments.preview, format="PNG")
    print(arguments.output)


if __name__ == "__main__":
    main()
