"""Build side-by-side "as shot vs post-processed" sheets for the night.

Left  = the JPG the scope's firmware produced (8-bit, weakly stretched).
Right = our 16-bit FITS reduction from process_fits.py.

The point is to show *why* the in-camera preview looks flat: it only uses a
small slice of the 0-255 range, while the FITS keeps the full 16-bit data.

Usage:
    python scripts/make_compare.py            # all targets
    python scripts/make_compare.py M31 IC405  # a subset
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "results" / "processed"
SHOT = ROOT / "results" / "DeepSky"
OUT = PROC / "compare"

# target -> (in-camera jpg stem, processed stem, kind)
TARGETS = {
    "M31":     ("M31_20261019.jpg",     "M31_broadband.jpg",     "broadband"),
    "M45":     ("M45_20261020.jpg",     "M45_broadband.jpg",     "broadband"),
    "M81":     ("M81_20261020.jpg",     "M81_broadband.jpg",     "broadband"),
    "NGC2403": ("NGC2403_20261020.jpg", "NGC2403_broadband.jpg", "broadband"),
    "IC405":   ("IC405_20261020.jpg",   "IC405_emission.jpg",    "emission"),
    "IC443":   ("IC443_20261020.jpg",   "IC443_emission.jpg",    "emission"),
    "NGC1499": ("NGC1499_20261019.jpg", "NGC1499_emission.jpg",  "emission"),
    "IC1805":  ("IC1805_20261019.jpg",  "IC1805_emission.jpg",   "emission"),
}

CELL_W, CELL_H = 760, 620
LABEL_H = 44
GAP = 10


def dynamic_range(path: Path) -> int:
    """p99 - median of the luminance, i.e. how many levels carry the signal."""
    a = np.asarray(Image.open(path).convert("L"), dtype=np.float32)
    return int(np.percentile(a, 99) - np.median(a))


def fit(im: Image.Image, w: int, h: int) -> Image.Image:
    s = min(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                   Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), (0, 0, 0))
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return canvas


def font(size: int):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build(target: str) -> Path | None:
    shot_name, proc_name, kind = TARGETS[target]
    shot, proc = SHOT / shot_name, PROC / proc_name
    if not shot.exists():
        print(f"  {target}: missing in-camera jpg ({shot})")
        return None
    if not proc.exists():
        print(f"  {target}: missing processed image ({proc})")
        return None

    dr_shot = dynamic_range(shot)
    dr_proc = dynamic_range(proc)

    a = fit(Image.open(shot).convert("RGB"), CELL_W, CELL_H)
    b = fit(Image.open(proc).convert("RGB"), CELL_W, CELL_H)

    W = CELL_W * 2 + GAP
    H = CELL_H + LABEL_H
    sheet = Image.new("RGB", (W, H), (12, 12, 14))
    sheet.paste(a, (0, LABEL_H))
    sheet.paste(b, (CELL_W + GAP, LABEL_H))

    d = ImageDraw.Draw(sheet)
    f_big, f_sm = font(24), font(18)
    d.text((10, 10), f"AS SHOT (in-camera JPG)   {dr_shot}/255 dynamic range",
           fill=(235, 160, 120), font=f_sm)
    d.text((CELL_W + GAP + 10, 10),
           f"POST-PROCESSED (16-bit FITS)   {dr_proc}/255",
           fill=(140, 220, 160), font=f_sm)

    tag = "emission nebula - LP filter" if kind == "emission" else "broadband - IRCUT"
    d.text((10, H - 30), f"{target}   {tag}", fill=(210, 210, 215), font=f_big)
    d.text((W - 300, H - 26), "seestar-agent", fill=(90, 90, 95), font=f_sm)

    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{target}_compare.jpg"
    sheet.save(dest, quality=93, subsampling=0)
    print(f"  {target}: jpg DR {dr_shot}/255 -> post DR {dr_proc}/255  -> {dest.name}")
    return dest


def main():
    wanted = sys.argv[1:] or list(TARGETS)
    print(f"building {len(wanted)} comparison sheet(s) into {OUT}")
    for t in wanted:
        if t not in TARGETS:
            print(f"  unknown target {t}")
            continue
        build(t)
    print("done")


if __name__ == "__main__":
    main()
