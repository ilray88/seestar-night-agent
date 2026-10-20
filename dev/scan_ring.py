"""Scan a ring of azimuths at a fixed altitude and report sky openness."""
from __future__ import annotations

import json
import sys
import time

import scan_sky as S


def main():
    alt = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
    step = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    out_tag = sys.argv[3] if len(sys.argv) > 3 else f"ring{int(alt)}"

    azs = [i * step for i in range(int(360 / step))]
    rows = []
    print(f"# ring alt={alt} step={step} n={len(azs)}", flush=True)
    print(f"{'az':>6} {'mean':>7} {'p99':>7} {'stars':>6} {'settle':>7} {'ok':>4}", flush=True)

    for az in azs:
        r = S.measure(az, alt, f"{int(az)}x{int(alt)}")
        r["open"] = bool(r.get("stars", 0) > 40)
        rows.append(r)
        print(f"{r['az']:>6.0f} {r['mean']:>7.1f} {r['p99']:>7.1f} "
              f"{r['stars']:>6d} {r.get('err_deg') or -1:>7.2f} "
              f"{'OPEN' if r['open'] else '----':>4}", flush=True)

    path = f"scripts/_{out_tag}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    opened = [r["az"] for r in rows if r["open"]]
    print(f"\nopen azimuths: {opened}")
    print(f"saved -> {path}")


if __name__ == "__main__":
    main()
