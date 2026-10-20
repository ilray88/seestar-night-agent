"""Build a contact sheet of every processed target for one-glance review."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "results" / "processed"
OUT = SRC / "contact_sheet.jpg"

ITEMS = [
    ("M31", "broadband"), ("M45", "broadband"),
    ("M81", "broadband"), ("NGC2403", "broadband"),
    ("IC405", "emission"), ("IC443", "emission"),
    ("NGC1499", "emission"), ("IC1805", "emission"),
]

CELL_W, CELL_H = 520, 400
COLS, ROWS = 4, 2
PAD = 8
LABEL_H = 26


def font(size: int):
    for name in ("arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit(im: Image.Image, w: int, h: int) -> Image.Image:
    im = im.convert("RGB")
    s = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                     Image.LANCZOS)


def main():
    sheet = Image.new("RGB", (COLS * (CELL_W + PAD) + PAD,
                              ROWS * (CELL_H + LABEL_H + PAD) + PAD), (18, 18, 20))
    draw = ImageDraw.Draw(sheet)
    f = font(17)

    for i, (target, kind) in enumerate(ITEMS):
        r, c = divmod(i, COLS)
        x = PAD + c * (CELL_W + PAD)
        y = PAD + r * (CELL_H + LABEL_H + PAD)
        draw.rectangle([x, y, x + CELL_W, y + CELL_H], fill=(0, 0, 0))
        p = SRC / f"{target}_{kind}.jpg"
        if p.exists():
            im = fit(Image.open(p), CELL_W, CELL_H)
            sheet.paste(im, (x + (CELL_W - im.width) // 2,
                             y + (CELL_H - im.height) // 2))
            status = ""
        else:
            status = " (missing)"
        draw.text((x + 4, y + CELL_H + 3), f"{target} 【{kind}】{status}",
                  fill=(235, 235, 235), font=f)

    sheet.save(OUT, quality=92)
    print("saved", OUT, sheet.size)


if __name__ == "__main__":
    main()
