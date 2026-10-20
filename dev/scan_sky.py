"""Empirically map the visible sky window by pointing the scope at a grid of
azimuth/elevation targets and measuring the captured frame.

Dark frame  -> that direction is blocked (wall / window frame / sill)
Star field  -> open sky

Run with the seestar_alp venv (needs astropy).
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone

import cv2
import numpy as np
from astropy.coordinates import AltAz, EarthLocation, FK5, SkyCoord
from astropy.time import Time
import astropy.units as u

BASE = "http://127.0.0.1:5555"
DEV = 1
LAT, LON, ELEV = 22.7261, 114.046, 40.0
SITE = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ELEV * u.m)

_tx = [5000]


def _req(path, body=None, timeout=120):
    _tx[0] += 1
    url = f"{BASE}/api/v1/telescope/{DEV}/{path}"
    sep = "&" if "?" in path else "?"
    url += f"{sep}ClientID=1&ClientTransactionID={_tx[0]}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PUT" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def native(method, params=None, timeout=120):
    body = {
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": _tx[0] + 1,
    }
    rep = _req("action", body, timeout=timeout)
    return rep.get("Value")


def altaz_to_radec(az, alt, when=None):
    when = when or datetime.now(timezone.utc)
    t = Time(when)
    frame = AltAz(obstime=t, location=SITE, pressure=0 * u.hPa)
    c = SkyCoord(az=az * u.deg, alt=alt * u.deg, frame=frame)
    fk5 = c.transform_to(FK5(equinox=t))
    return fk5.ra.hour, fk5.dec.deg


def radec_to_altaz(ra_h, dec_deg, when=None):
    when = when or datetime.now(timezone.utc)
    t = Time(when)
    c = SkyCoord(ra=ra_h * u.hour, dec=dec_deg * u.deg, frame=FK5(equinox=t))
    aa = c.transform_to(AltAz(obstime=t, location=SITE, pressure=0 * u.hPa))
    return float(aa.az.deg), float(aa.alt.deg)


def goto(ra_h, dec_deg, name="scan"):
    body = {"Action": "goto_target",
            "Parameters": json.dumps({"target_name": name, "is_j2000": False,
                                      "ra": ra_h, "dec": dec_deg}),
            "ClientID": 1, "ClientTransactionID": _tx[0] + 1}
    return _req("action", body, timeout=180)


def equ_coord():
    """Real-time pointing from the device (Alpaca's RA/Dec props are stale)."""
    try:
        r = native("scope_get_equ_coord", timeout=30)
        res = (r or {}).get("result") or {}
        if "ra" in res:
            return float(res["ra"]), float(res["dec"])
    except Exception:
        pass
    return None


def wait_settled(target_ra, target_dec, timeout=120, tol=0.25):
    """Poll the real pointing until it is close to the target and stays put."""
    t0 = time.time()
    last = None
    stable = 0
    while time.time() - t0 < timeout:
        cur = equ_coord()
        if cur:
            dra = abs(cur[0] - target_ra) * 15.0
            ddec = abs(cur[1] - target_dec)
            err = max(dra, ddec)
            if err < tol:
                if last is not None and abs(last[0] - cur[0]) < 0.002 \
                        and abs(last[1] - cur[1]) < 0.002:
                    stable += 1
                else:
                    stable = 0
                last = cur
                if stable >= 2:
                    return True, err
            else:
                stable = 0
                last = cur
        time.sleep(1.5)
    return False, None


def wait_slew(timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if not _req("slewing", timeout=20).get("Value", False):
                return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


def grab(timeout=18):
    try:
        s = socket.create_connection(("127.0.0.1", 7556), timeout=10)
        s.settimeout(timeout)
        s.sendall(b"GET /1/vid HTTP/1.1\r\nHost: 127.0.0.1:7556\r\n"
                  b"Accept: multipart/x-mixed-replace\r\nConnection: close\r\n\r\n")
        buf = b""
        dl = time.time() + timeout
        while time.time() < dl:
            try:
                c = s.recv(65536)
            except socket.timeout:
                break
            if not c:
                break
            buf += c
            a = buf.find(b"\xff\xd8\xff")
            if a >= 0:
                b = buf.find(b"\xff\xd9", a)
                if b > 0:
                    s.close()
                    return buf[a:b + 2]
        s.close()
    except Exception:
        pass
    return None


def analyse(jpg):
    if not jpg:
        return None
    arr = np.frombuffer(jpg, np.uint8)
    im = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if im is None:
        return None
    g = im.astype(np.float32)
    # downscale for speed
    small = cv2.resize(g, (480, 270), interpolation=cv2.INTER_AREA)
    mean = float(small.mean())
    p50 = float(np.percentile(small, 50))
    p99 = float(np.percentile(small, 99))
    p999 = float(np.percentile(small, 99.9))
    # star blobs: local peaks well above local background
    bg = cv2.medianBlur(small.astype(np.uint8), 15).astype(np.float32)
    d = small - bg
    stars = int((d > 12).sum())
    return {"mean": round(mean, 1), "p50": round(p50, 1), "p99": round(p99, 1),
            "p999": round(p999, 1), "stars": stars}


def measure(az, alt, label=""):
    ra, dec = altaz_to_radec(az, alt)
    t0 = time.time()
    goto(ra, dec, name=f"scan{label}")
    ok, err = wait_settled(ra, dec, timeout=150)
    time.sleep(2.0)
    stats = analyse(grab())
    stats = stats or {"mean": -1, "stars": -1}
    stats.update({"az": round(az, 1), "alt": round(alt, 1),
                  "settled": bool(ok), "err_deg": round(err, 3) if err else None,
                  "sec": round(time.time() - t0, 1)})
    return stats


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    out = []
    if mode == "probe":
        # where does it think it points right now?
        ra = _req("rightascension").get("Value")
        dec = _req("declination").get("Value")
        az, alt = radec_to_altaz(ra, dec)
        print(f"reported RA={ra:.4f}h Dec={dec:.4f}  ->  az={az:.1f} alt={alt:.1f}")
        st = native("get_device_state") or {}
        data = (st.get("result") or {})
        cs = (data.get("compass_sensor") or {}).get("data") or {}
        bs = (data.get("balance_sensor") or {}).get("data") or {}
        print(f"compass heading={cs.get('direction_true')}  tilt={bs.get('angle')}")
        print("frame:", analyse(grab()))
    else:
        grid = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
        for az, alt in grid:
            r = measure(az, alt, f"{int(az)}x{int(alt)}")
            out.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
        with open("scripts/_scan_result.json", "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
