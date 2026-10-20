"""Objective quality stats for the downloaded stacked JPEGs."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ROOT / "results" / "DeepSky" / "M31_20261019.jpg",
    ROOT / "results" / "DeepSky" / "IC1805_20261019.jpg",
]


def stats(p: Path):
    im = Image.open(p)
    arr = np.asarray(im.convert("RGB"), dtype=np.float32)
    gray = arr.mean(axis=2)

    print("=" * 78)
    print(f"{p.name}   {im.size[0]}x{im.size[1]}  mode={im.mode}  {p.stat().st_size/1024:.0f} KB")
    print("-" * 78)

    for name, ch in (("R", arr[:, :, 0]), ("G", arr[:, :, 1]), ("B", arr[:, :, 2])):
        med = np.median(ch)
        print(f"  {name}: mean={ch.mean():6.1f} median={med:6.1f} "
              f"p1={np.percentile(ch,1):5.1f} p99={np.percentile(ch,99):6.1f}")

    # background = median of the darkest 50% of pixels
    flat = gray.ravel()
    bg = np.median(flat[flat < np.percentile(flat, 50)])
    # robust noise = MAD of the darkest 60%
    dark = flat[flat < np.percentile(flat, 60)]
    mad = np.median(np.abs(dark - np.median(dark)))
    sigma = 1.4826 * mad

    print(f"  background level = {bg:.1f}/255   noise sigma = {sigma:.2f}")
    print(f"  dynamic range used = p99-bg = {np.percentile(gray,99)-bg:.0f}")
    print(f"  SNR(background) = {(np.percentile(gray,99)-bg)/max(sigma,1e-6):.1f}")
    print(f"  clipped black (<3) = {np.mean(gray < 3)*100:.1f}%   "
          f"near-white (>250) = {np.mean(gray > 250)*100:.2f}%")
    # how much of the histogram is unused
    print(f"  pixels in 0-40 range = {np.mean(gray < 40)*100:.1f}%  "
          f"(if >80%, the image is under-stretched / very dark)")
    # colour cast
    print(f"  channel medians R/G/B = {np.median(arr[:,:,0]):.1f} / "
          f"{np.median(arr[:,:,1]):.1f} / {np.median(arr[:,:,2]):.1f}")


for f in FILES:
    if f.exists():
        stats(f)
    else:
        print("missing:", f)
