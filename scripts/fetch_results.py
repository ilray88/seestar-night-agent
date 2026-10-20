"""Collect stacked full-size JPEG results from the Seestar over plain HTTP.

Why HTTP and not SMB: on firmware 9.75 guest SMB logins are rejected
("signing/encryption required"), but the device serves MyWorks over HTTP/80
with Range support.

How the album tree works (firmware 9.75):
  get_albums returns only the ROOT: {path: "MyWorks", list: [group, ...]}
  each group = {"group_name": "DeepSky", "files": [target, ...]}
  each target = {"name": "M 31", "thn": "M 31/Stacked_41_..._thn.jpg", "count": 6}

There is no directory-listing endpoint (both HTTP dirs and get_albums?path=
return the root). But the thumbnail path is the full-size path with a
`_thn` suffix, so we recover the real filename from it. Verified:
  M 31/Stacked_41_M 31_20.0s_IRCUT_20261018-200814_thn.jpg   10.6 KB thumb
  M 31/Stacked_41_M 31_20.0s_IRCUT_20261018-200814.jpg      1.0 MB  real

Usage:
    python fetch_results.py --dry-run          # list only
    python fetch_results.py                    # download stacked JPEGs
    python fetch_results.py --since 20261019   # only tonight
    python fetch_results.py --all-jpg          # also grab sub-frame thumbnails
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from device_ip import device_base  # sibling module; scripts are run from this dir

HOST = device_base().removeprefix("http://")
BASE = device_base()
ALPACA = "http://127.0.0.1:5555"
_tx = [8000]

# Date stamp looks like 20261018-200814
_DATE_RE = re.compile(r"(\d{8})-\d{6}")


def native(method, params=None, timeout=60):
    _tx[0] += 1
    body = {
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": _tx[0],
    }
    req = urllib.request.Request(
        f"{ALPACA}/api/v1/telescope/1/action"
        f"?ClientID=1&ClientTransactionID={_tx[0]}",
        data=json.dumps(body).encode(), method="PUT",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()).get("Value")


def albums():
    v = native("get_albums", timeout=60) or {}
    return v.get("result") or {}


def iter_targets(root):
    """Yield (group_name, target_name, thumb_path, count)."""
    for grp in root.get("list") or []:
        gname = grp.get("group_name") or "?"
        for t in grp.get("files") or []:
            yield gname, t.get("name") or "?", t.get("thn") or "", t.get("count", 0)


def full_size_path(thumb: str) -> str:
    """`M 31/Stacked_41_..._thn.jpg` -> `M 31/Stacked_41_....jpg`"""
    if thumb.endswith("_thn.jpg"):
        return thumb[: -len("_thn.jpg")] + ".jpg"
    return thumb


def http_get(remote: str, timeout=120):
    url = f"{BASE}/MyWorks/{urllib.parse.quote(remote)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def download(remote: str, out: Path):
    data = http_get(remote)
    if not data[:3] == b"\xff\xd8\xff":
        return f"ERR not JPEG ({len(data)} bytes)"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return f"{len(data)/1e6:.2f} MB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./results")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since", default=None,
                    help="only targets whose thumbnail date stamp >= this (YYYYMMDD)")
    ap.add_argument("--all-jpg", action="store_true",
                    help="also fetch sub-frame/preview JPEGs, not just stacks")
    args = ap.parse_args()

    root = albums()
    print(f"album root: {root.get('path')}")
    outdir = Path(args.out)

    plan = []
    for gname, tname, thumb, count in iter_targets(root):
        if not thumb:
            continue
        if not args.all_jpg and "_sub/" in thumb:
            continue
        m = _DATE_RE.search(thumb)
        stamp = m.group(1) if m else ""
        if args.since and stamp and stamp < args.since:
            continue
        plan.append({
            "group": gname,
            "target": tname,
            "remote": full_size_path(thumb),
            "count": count,
            "stamp": stamp,
        })

    print(f"\nfound {len(plan)} stacked result(s)")
    total = 0
    for e in plan:
        label = f"{e['group']:<12} {e['target']:<22} {e['stamp']}"
        if args.dry_run:
            print(f"  [DRY] {label}  -> {e['remote']}")
            continue
        dest = outdir / e["group"] / f"{e['target'].strip().replace(' ', '_')}_{e['stamp']}.jpg"
        if dest.exists():
            print(f"  skip {label} (exists)")
            continue
        try:
            r = download(e["remote"], dest)
            if r.startswith("ERR"):
                print(f"  FAIL {label}: {r}")
            else:
                total += 1
                print(f"  ok   {label} -> {r}")
        except Exception as ex:
            print(f"  FAIL {label}: {str(ex)[:80]}")
        time.sleep(0.2)

    if args.dry_run:
        print("\n(dry run - nothing written)")
    else:
        print(f"\ndone. {total} file(s) under {outdir.resolve()}")


if __name__ == "__main__":
    main()
