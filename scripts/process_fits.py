"""Post-process a Seestar stacked FITS into a properly stretched image.

Why this exists
---------------
The JPG the scope hands out is an 8-bit, weakly-stretched preview: on
2026-10-19 the M31 JPG used only 28 of 255 levels for the actual signal.
The `.fit` sitting next to it is the real thing -- 3x3840x2160 uint16,
already debayered/aligned/stacked, linear.  This script turns that into a
normal astrophotography result:

    background extraction -> colour balance -> asinh/MTF stretch
    -> saturation -> chroma denoise -> unsharp mask

Runs on the seestar_alp venv (numpy + PIL).  FITS is parsed by hand so we
do not need astropy here.

Usage
-----
    python scripts/process_fits.py data/stacked_fits/M31_367.fit \
        --target M31 --stretch 0.12 --saturation 1.25
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# minimal FITS reader (single HDU, BITPIX=16, BZERO=32768)
# --------------------------------------------------------------------------
def read_fits(path: str | Path) -> tuple[np.ndarray, dict]:
    raw = Path(path).read_bytes()
    cards: dict[str, object] = {}
    pos = 0
    while True:
        block = raw[pos:pos + 2880]
        if not block:
            raise ValueError("FITS header ended without END card")
        for i in range(0, len(block), 80):
            card = block[i:i + 80].decode("ascii", "replace")
            key = card[:8].strip()
            if key == "END":
                pos += 2880
                break
            if card[8:10] == "= ":
                val = card[10:].split("/")[0].strip()
                cards[key] = _fits_value(val)
        else:
            pos += 2880
            continue
        break

    bitpix = int(cards["BITPIX"])
    naxis = int(cards["NAXIS"])
    dims = [int(cards[f"NAXIS{i}"]) for i in range(naxis, 0, -1)]
    bzero = cards.get("BZERO", 0)
    bscale = cards.get("BSCALE", 1)
    dtype = {8: ">u1", 16: ">i2", 32: ">i4", -32: ">f4", -64: ">f8"}[bitpix]
    n = int(np.prod(dims))
    data = np.frombuffer(raw, dtype=dtype, count=n, offset=pos).astype(np.float32)
    data = data.reshape(dims) * float(bscale) + float(bzero)
    return data, cards


def _fits_value(v: str):
    if v.startswith("'"):
        return v.strip("' ").rstrip()
    if v in ("T", "F"):
        return v == "T"
    try:
        return float(v)
    except ValueError:
        return v


# --------------------------------------------------------------------------
# processing primitives
# --------------------------------------------------------------------------
def box_blur(a: np.ndarray, r: int) -> np.ndarray:
    """Separable box blur (two passes ~ gaussian) without scipy."""
    if r <= 0:
        return a
    k = 2 * r + 1
    out = a
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        c = np.cumsum(p, axis=axis, dtype=np.float32)
        # prepend a zero row/col so c has n+1 entries and out[i] = c[i+k] - c[i]
        c = np.concatenate(
            [np.zeros_like(np.take(c, [0], axis=axis)), c], axis=axis)
        sl_hi = [slice(None)] * out.ndim
        sl_lo = [slice(None)] * out.ndim
        sl_hi[axis] = slice(k, None)
        sl_lo[axis] = slice(None, -k)
        out = (c[tuple(sl_hi)] - c[tuple(sl_lo)]) / k
    return out


def block_median(a: np.ndarray, block: int = 64) -> np.ndarray:
    """Coarse median grid, then bilinearly upsampled -- cheap gradient model."""
    h, w = a.shape
    ny, nx = max(1, h // block), max(1, w // block)
    g = np.empty((ny, nx), dtype=np.float32)
    for y in range(ny):
        for x in range(nx):
            g[y, x] = np.median(a[y * block:(y + 1) * block,
                                   x * block:(x + 1) * block])
    # bilinear upsample back to full size
    ys = np.linspace(0, ny - 1, h).astype(np.float32)
    xs = np.linspace(0, nx - 1, w).astype(np.float32)
    y0 = np.floor(ys).astype(int).clip(0, ny - 1)
    x0 = np.floor(xs).astype(int).clip(0, nx - 1)
    y1 = (y0 + 1).clip(0, ny - 1)
    x1 = (x0 + 1).clip(0, nx - 1)
    wy = (ys - y0)[:, None]
    wx = (xs - x0)[None, :]
    top = g[y0][:, x0] * (1 - wx) + g[y0][:, x1] * wx
    bot = g[y1][:, x0] * (1 - wx) + g[y1][:, x1] * wx
    return top * (1 - wy) + bot * wy


def poly_background(ch: np.ndarray, deg: int = 3, grid: int = 12) -> np.ndarray:
    """Fit a smooth 2-D polynomial to the sky and return it at full res.

    Sampling a coarse grid of *medians* keeps stars out of the fit, so the
    model describes the light-pollution / vignetting gradient only.
    """
    h, w = ch.shape
    ys = np.linspace(0, h - 1, grid).astype(int)
    xs = np.linspace(0, w - 1, grid).astype(int)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    vals = np.empty((grid, grid), dtype=np.float64)
    for i, y in enumerate(ys):
        y0, y1 = max(0, y - 24), min(h, y + 24)
        for j, x in enumerate(xs):
            x0, x1 = max(0, x - 24), min(w, x + 24)
            vals[i, j] = np.median(ch[y0:y1, x0:x1])

    # normalised coordinates keep the Vandermonde well conditioned
    ny = (gy / max(h - 1, 1)) * 2 - 1
    nx = (gx / max(w - 1, 1)) * 2 - 1
    terms = [(i, j) for i in range(deg + 1) for j in range(deg + 1 - i)]
    A = np.stack([(ny ** i) * (nx ** j) for i, j in terms], axis=-1)
    A = A.reshape(-1, len(terms))
    coef, *_ = np.linalg.lstsq(A, vals.reshape(-1), rcond=None)

    yy = (np.linspace(0, 1, h) * 2 - 1)[:, None]
    xx = (np.linspace(0, 1, w) * 2 - 1)[None, :]
    model = np.zeros((h, w), dtype=np.float64)
    for (i, j), c in zip(terms, coef):
        model += c * (yy ** i) * (xx ** j)
    return model.astype(np.float32)


def mtf(x: np.ndarray, m: float) -> np.ndarray:
    """PixInsight midtone transfer function."""
    return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m)


def arcsinh(x: np.ndarray, k: float) -> np.ndarray:
    """Arcsinh stretch: lifts faint signal, compresses highlights smoothly.

    Far better than a hard MTF on this data because M31's core peaks at
    57434 while the galaxy arms sit near 3000 -- a linear normalise turns
    the core into a flat white disc.
    """
    return np.arcsinh(np.clip(x, 0, None) * k) / np.arcsinh(k)


def auto_mtf(x: np.ndarray, target: float) -> float:
    """Pick m so that median(mtf(x)) lands on `target` (bisection fallback)."""
    med = float(np.median(x))
    if med <= 0:
        return 0.5
    lo, hi = 1e-6, 0.999999
    for _ in range(70):
        mid = 0.5 * (lo + hi)
        if float(mtf(np.array([med]), mid)[0]) < target:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def mtf_m_for(x: float, target: float) -> float:
    """Solve the MTF midpoint analytically so that `x` maps to `target`.

    Inverting ``target = ((m-1)x) / ((2m-1)x - m)`` for m gives

        m = x (target - 1) / (2 target x - target - x)

    Bisection is avoided because it silently clamps when the input is
    already close to 1 (the mistake that produced the washed-out v2).
    """
    den = 2.0 * target * x - target - x
    if abs(den) < 1e-12:
        return 0.5
    m = x * (target - 1.0) / den
    return float(np.clip(m, 0.01, 0.99))


def srgb(x: np.ndarray, gamma: float = 2.2) -> np.ndarray:
    return np.clip(x, 0, 1) ** (1.0 / gamma)


# --------------------------------------------------------------------------
# main pipeline
# --------------------------------------------------------------------------
def process(fits_path: Path, target: str, out_dir: Path,
            stretch_target: float = 0.08, saturation: float = 1.25,
            gamma: float = 2.2, denoise: float = 0.65,
            unsharp: float = 0.55, asinh_k: float = 120.0,
            predenoise: float = 0.6, cb: float = 0.5,
            bg_deg: int = 3, bg_grid: int = 12, white_cap: float = 8.0,
            label: str = "v1") -> dict:
    data, cards = read_fits(fits_path)

    if data.ndim == 3 and data.shape[0] in (3, 4):
        img = np.transpose(data[:3], (1, 2, 0)).astype(np.float32)   # H,W,3
    elif data.ndim == 3:
        img = np.transpose(data, (1, 2, 0)).astype(np.float32)
    else:
        img = np.repeat(data[:, :, None], 3, axis=2).astype(np.float32)

    stats: dict[str, object] = {"fits": str(fits_path), "shape": list(img.shape)}

    # --- 1) background extraction, per channel -----------------------------
    #     A 2-D polynomial per channel removes both the pedestal and the
    #     light-pollution gradient (the green wash in the lower corners of the
    #     raw M31 stack).  Doing it per channel also neutralises the sky.
    bg_model = np.empty_like(img)
    for c in range(3):
        bg_model[:, :, c] = poly_background(img[:, :, c], deg=bg_deg, grid=bg_grid)
    img = img - bg_model
    # NOTE: deliberately NOT clipped here.  Half the sky pixels would become
    # exactly 0, the median would collapse to 0, and the MTF solver would
    # degenerate (that is what produced the washed-out v3).
    stats["bg_mean"] = [round(float(bg_model[:, :, c].mean()), 1) for c in range(3)]

    # --- 2) colour balance -------------------------------------------------
    #     Mild only: the background fit already neutralised the sky, so a
    #     gentle percentile balance corrects throughput without turning every
    #     star blue.
    p999 = np.array([np.percentile(np.clip(img[:, :, c], 0, None), 99.9)
                     for c in range(3)], dtype=np.float32)
    p999[p999 <= 0] = 1.0
    raw_scale = p999.mean() / p999
    scale = 1.0 + cb * (raw_scale - 1.0)
    img *= scale[None, None, :]
    stats["channel_scale"] = [round(float(s), 4) for s in scale]

    # --- 3) noise reduction while the data is still linear ----------------
    #     Sky sigma is ~31 counts and the galaxy arms sit only ~91 counts
    #     above it -- barely 3 sigma.  Stretching first turns that speckle
    #     into a snowstorm, so smooth it here, before the non-linear step.
    if predenoise > 0:
        lum = img.mean(axis=2, keepdims=True)
        smooth = np.empty_like(lum)
        smooth[:, :, 0] = box_blur(lum[:, :, 0], 1)
        img = img + (smooth - lum) * predenoise

    # --- 4) black/white points + Reinhard + analytic MTF -------------------
    #     a) black point from a robust noise estimate, so the sky lands on a
    #        known positive level instead of being clipped to exactly zero;
    #     b) white point at p99.9 was only 176 counts wide and blew the noise
    #        up (v3) -- use p99.99;
    #     c) Reinhard rolloff before the MTF, so M31's core (31x the arms) is
    #        compressed smoothly instead of becoming a flat white disc;
    #     d) MTF midtone solved analytically from the resulting sky level.
    med = float(np.median(img))
    mad = float(np.median(np.abs(img - med)))
    sigma = 1.4826 * mad
    black = med - 2.8 * sigma
    p9999 = float(np.percentile(img, 99.99))
    p999 = float(np.percentile(img, 99.9))
    # A handful of very bright stars (M45!) can drag p99.99 far above the real
    # signal level: on M45 it landed at 26312 while p99.9 was only ~500, which
    # crushed the reflection nebulosity to near-black.  Cap the white point so
    # the brightest few percent can only stretch it a bounded amount.
    white = min(p9999, p999 * white_cap)
    if white <= black + 1e-6:
        white = float(img.max()) or (black + 1.0)
    x = (img - black) / (white - black)
    np.clip(x, 0, None, out=x)
    x = x / (1.0 + x)                    # Reinhard: 1.0 -> 0.5, 31 -> 0.97
    sky_raw = float((0.0 - black) / (white - black))
    sky_x = float(np.clip(sky_raw / (1.0 + sky_raw), 1e-4, 0.9))
    m = mtf_m_for(sky_x, stretch_target)
    img = mtf(x, m)
    np.clip(img, 0, 1, out=img)
    stats["mtf_m"] = round(m, 6)
    stats["sky_x"] = round(sky_x, 5)
    stats["sigma"] = round(sigma, 2)
    stats["black"] = round(black, 1)
    stats["white"] = round(white, 1)

    # --- 4) saturation -----------------------------------------------------
    if saturation != 1.0:
        lum = img.mean(axis=2, keepdims=True)
        img = np.clip(lum + (img - lum) * saturation, 0, 1)

    # --- 5) chroma denoise -------------------------------------------------
    #     Averaging a/b in a blurred copy removes the coloured speckle that
    #     gets amplified by the stretch, while keeping luminance detail.
    if denoise > 0:
        lum = img.mean(axis=2, keepdims=True)
        chroma = img - lum
        s = max(1, int(min(img.shape[:2]) / 700))
        chroma_blur = np.empty_like(chroma)
        for c in range(3):
            chroma_blur[:, :, c] = box_blur(chroma[:, :, c], s)
        img = np.clip(lum + (1 - denoise) * chroma + denoise * chroma_blur, 0, 1)

    # --- 6) unsharp mask on luminance --------------------------------------
    if unsharp > 0:
        lum = img.mean(axis=2, keepdims=True)
        blurred = np.empty_like(lum)
        blurred[:, :, 0] = box_blur(lum[:, :, 0], 2)
        detail = lum - blurred
        img = np.clip(img + unsharp * detail, 0, 1)

    # --- 7) gamma + save ---------------------------------------------------
    out = srgb(img, gamma)
    u8 = (out * 255.0 + 0.5).clip(0, 255).astype(np.uint8)

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{target}_{label}"
    jpg = out_dir / f"{stem}.jpg"
    png = out_dir / f"{stem}.png"
    Image.fromarray(u8).save(png)
    Image.fromarray(u8).save(jpg, quality=95, subsampling=0)

    stats["out"] = str(jpg)
    stats["hist_p50"] = int(np.percentile(u8, 50))
    stats["hist_p99"] = int(np.percentile(u8, 99))
    stats["frac_lt40"] = round(float((u8.mean(axis=2) < 40).mean()), 4)
    stats["exptime"] = cards.get("EXPTIME")
    stats["gain"] = cards.get("GAIN")
    stats["filter"] = cards.get("FILTER")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fits")
    ap.add_argument("--target", default=None)
    ap.add_argument("--out", default=str(ROOT / "results" / "processed"))
    ap.add_argument("--stretch", type=float, default=0.08,
                    help="target level for the sky background after MTF (0.05-0.15)")
    ap.add_argument("--saturation", type=float, default=1.25)
    ap.add_argument("--gamma", type=float, default=2.2)
    ap.add_argument("--denoise", type=float, default=0.65)
    ap.add_argument("--predenoise", type=float, default=0.6,
                    help="luminance smoothing applied before the stretch (0-1)")
    ap.add_argument("--unsharp", type=float, default=0.55)
    ap.add_argument("--asinh-k", type=float, default=120.0,
                    help="arcsinh strength; higher = more highlight compression")
    ap.add_argument("--bg-deg", type=int, default=3,
                    help="polynomial degree of the background model; use 1 for large nebulae")
    ap.add_argument("--bg-grid", type=int, default=12,
                    help="background grid cells per axis; larger keeps large-scale nebulosity")
    ap.add_argument("--white-cap", type=float, default=8.0,
                    help="upper bound on the white point as a multiple of p99.9; "
                         "lower = brighter faint structure (try 3 for dim galaxies)")
    ap.add_argument("--label", default="v1")
    ap.add_argument("--cb", type=float, default=0.5,
                    help="colour-balance strength: 0 keeps emission-line colour, 1 fully neutralises")
    args = ap.parse_args()

    fp = Path(args.fits)
    target = args.target or fp.stem.split("_")[0]
    st = process(fp, target, Path(args.out),
                 stretch_target=args.stretch, saturation=args.saturation,
                 gamma=args.gamma, denoise=args.denoise,
                 unsharp=args.unsharp, asinh_k=args.asinh_k,
                 predenoise=args.predenoise, cb=args.cb,
                 bg_deg=args.bg_deg, bg_grid=args.bg_grid,
                 white_cap=args.white_cap, label=args.label)
    print(json.dumps(st, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
