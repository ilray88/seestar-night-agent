"""Download last night's stacked FITS files from the Seestar over HTTP.

The device serves the album at http://<ip>/MyWorks/.  The listing from
`get_albums` gives a thumbnail path; stripping the `_thn` suffix yields the
full-size file, and swapping `.jpg` for `.fit` yields the 16-bit stack that
is actually worth post-processing.

Usage:
    python scripts/download_night.py --since 20261019 --out data/stacked_fits
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALPACA = "http://127.0.0.1:5555/api/v1/telescope/1/action"
DEVICE = "http://192.168.2.118"

# last night's targets
TARGETS = ["M31", "IC1805", "NGC1499", "M45", "IC405", "IC443", "M81", "NGC2403"]

_txid = [91000]


def _dates_in(stem: str) -> list[int]:
    """Pull the 8-digit date stamps out of a stack filename."""
    return [int(d) for d in re.findall(r"20\d{6}", stem)]


def native(method: str, params=None, timeout: float = 40.0):
    _txid[0] += 1
    body = json.dumps({
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": _txid[0],
    }).encode()
    req = urllib.request.Request(
        ALPACA, data=body,
        headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def albums() -> list[dict]:
    res = native("get_albums")["Value"]["result"]
    out = []
    for grp in res.get("list", []):
        out.extend(grp.get("files", []))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="20261019")
    ap.add_argument("--out", default=str(ROOT / "data" / "stacked_fits"))
    ap.add_argument("--targets", default=",".join(TARGETS))
    args = ap.parse_args()

    want = [t.strip() for t in args.targets.split(",") if t.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = {e["name"]: e for e in albums()}
    print(f"{'target':<12}{'stack frames':>13}  {'MB':>7}  file")
    print("-" * 78)

    for name in want:
        e = entries.get(name)
        if e is None:
            print(f"{name:<12}{'MISSING':>13}")
            continue
        thn = e.get("thn") or ""
        m = re.search(r"(Stacked_\d+_.*?)_thn\.jpg$", thn)
        if not m:
            print(f"{name:<12}{'no stacked entry':>13}  thn={thn}")
            continue
        stem = m.group(1)
        frames = int(re.search(r"Stacked_(\d+)_", stem).group(1))
        # skip a stack from an earlier night.  The night spans midnight, so the
        # device stamps pre-midnight targets 20261019 and post-midnight ones
        # 20261020; both belong to the same run.
        if args.since:
            try:
                night = int(args.since)
                dates = {d for d in _dates_in(stem)}
                if dates and min(dates) < night:
                    print(f"{name:<12}{frames:>13}  (skipped: not from {args.since})")
                    continue
            except ValueError:
                pass

        url = f"{DEVICE}/MyWorks/{urllib.parse.quote(f'{name}/{stem}.fit')}"
        dest = out_dir / f"{name}_{frames}.fit"
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"{name:<12}{frames:>13}  {dest.stat().st_size/1e6:7.1f}  {dest.name} (cached)")
            continue

        t0 = time.time()
        try:
            with urllib.request.urlopen(url, timeout=180) as r, \
                    dest.open("wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as exc:
            print(f"{name:<12}{frames:>13}  FAIL {exc}")
            continue
        mb = dest.stat().st_size / 1e6
        print(f"{name:<12}{frames:>13}  {mb:7.1f}  {dest.name}"
              f"  ({time.time()-t0:.1f}s)")

    print("\nfiles:")
    for p in sorted(out_dir.glob("*.fit")):
        print(f"  {p.name:<24}{p.stat().st_size/1e6:8.1f} MB")


if __name__ == "__main__":
    main()
