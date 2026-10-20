"""Batch post-process every stacked FITS from the 2026-10-19/20 session.

Two parameter sets are used, because the targets are physically different:

* broadband (galaxies, reflection nebula, clusters) -> neutral colour balance,
  deeper stretch, keep the blue/red star colours
* emission nebulae -> colour balance off (the p99.9 white balance actively
  suppresses H-alpha), shallower stretch, higher saturation, and a very low
  order background model so the large nebula is not fitted away as a gradient
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "seestar_alp" / ".venv" / "Scripts" / "python.exe"
SCRIPT = ROOT / "scripts" / "process_fits.py"
FITS_DIR = ROOT / "data" / "stacked_fits"

# target -> (fits file, kind)
TARGETS = {
    "M31":      ("M31_367.fit",      "broadband"),
    "M45":      ("M45_285.fit",      "broadband"),
    "M81":      ("M81_305.fit",      "broadband"),
    "NGC2403":  ("NGC2403_74.fit",   "broadband"),
    "IC405":    ("IC405_196.fit",    "emission"),
    "IC443":    ("IC443_178.fit",    "emission"),
    "NGC1499":  ("NGC1499_145.fit",  "emission"),
    "IC1805":   ("IC1805_281.fit",   "emission"),
}

COMMON = ["--predenoise", "0.6", "--denoise", "0.65",
          "--unsharp", "0.55", "--gamma", "2.2"]

PRESETS = {
    "broadband": ["--stretch", "0.035", "--cb", "0.5",
                  "--bg-deg", "3", "--bg-grid", "12",
                  "--saturation", "1.25"],
    "emission": ["--stretch", "0.10", "--cb", "0.0",
                 "--bg-deg", "1", "--bg-grid", "32",
                 "--saturation", "1.6"],
}

# Faint targets need a deeper stretch: their arms sit only ~2 sigma above the
# sky, so the default 0.035 sky level leaves the structure almost black.
# These overrides just replace the --stretch value of the preset.
STRETCH_OVERRIDE = {
    "M81": "0.06",
    "NGC2403": "0.06",
}


def main():
    only = sys.argv[1:] or list(TARGETS)
    results = []
    for target in only:
        fits_name, kind = TARGETS[target]
        fits = FITS_DIR / fits_name
        if not fits.exists():
            print("MISSING", fits)
            continue
        cmd = [str(PY), str(SCRIPT), str(fits), "--target", target,
               "--label", kind, *PRESETS[kind], *COMMON]
        if target in STRETCH_OVERRIDE:
            i = cmd.index("--stretch")
            cmd[i + 1] = STRETCH_OVERRIDE[target]
        print("=" * 78)
        print("PROCESSING", target, kind, fits.name)
        print("=" * 78)
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0:
            print("FAILED", target)
            print(p.stdout[-2000:])
            print(p.stderr[-2000:])
            continue
        try:
            st = json.loads(p.stdout[p.stdout.index("{"):])
        except Exception:
            print(p.stdout[-2000:])
            continue
        results.append(st)
        print(json.dumps(st, ensure_ascii=False, indent=2))

    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'target':<10}{'kind':<11}{'mtf_m':>9}{'p50':>6}{'p99':>6}"
          f"{'lt40':>8}{'sigma':>8}{'white':>9}")
    for st in results:
        name = st["out"].split("\\")[-1].replace(".jpg", "")
        print(f"{name:<10}{'':<11}{st.get('mtf_m', 0):>9.4f}"
              f"{st.get('hist_p50', 0):>6}{st.get('hist_p99', 0):>6}"
              f"{st.get('frac_lt40', 0):>8.4f}"
              f"{st.get('sigma', 0):>8.1f}{st.get('white', 0):>9.0f}")


if __name__ == "__main__":
    main()
