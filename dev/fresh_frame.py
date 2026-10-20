"""Grab a GUARANTEED-FRESH frame.

The seestar_alp MJPEG endpoint serves the last buffered image; if no view is
running it will happily replay a stale frame forever. So:
  1. start a continuous-exposure preview,
  2. watch the /1/vid/status SSE counter until it advances,
  3. then pull a frame.

Exports grab_fresh() for reuse by the scanner.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request


def _native(method, params=None, timeout=60, tx=[7000]):
    tx[0] += 1
    body = {
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": tx[0],
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:5555/api/v1/telescope/1/action"
        f"?ClientID=1&ClientTransactionID={tx[0]}",
        data=json.dumps(body).encode(),
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()).get("Value")


def frame_counter(timeout=8):
    """Read the newest 'Frame: N' from the SSE status stream."""
    try:
        s = socket.create_connection(("127.0.0.1", 7556), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(b"GET /1/vid/status HTTP/1.1\r\nHost: 127.0.0.1:7556\r\n"
                  b"Accept: text/event-stream\r\nConnection: close\r\n\r\n")
        buf = b""
        dl = time.time() + timeout
        while time.time() < dl:
            try:
                c = s.recv(4096)
            except socket.timeout:
                break
            if not c:
                break
            buf += c
            i = buf.find(b"Frame: ")
            if i >= 0:
                j = buf.find(b"\n", i)
                if j > 0:
                    s.close()
                    try:
                        return int(buf[i + 7:j].strip())
                    except ValueError:
                        return None
        s.close()
    except Exception:
        pass
    return None


def raw_frame(timeout=18):
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


def start_preview(gain=80):
    """Fire up continuous exposure so new frames are produced."""
    try:
        _native("iscope_stop_view", ["Stack"], timeout=30)
    except Exception:
        pass
    try:
        _native("iscope_stop_view", ["ContinuousExposure"], timeout=30)
    except Exception:
        pass
    time.sleep(1.0)
    try:
        _native("set_control_value", ["gain", gain], timeout=30)
    except Exception:
        pass
    # Start a live preview at the current pointing
    try:
        cur = _native("scope_get_equ_coord", timeout=30)
        res = (cur or {}).get("result") or {}
        ra, dec = res.get("ra"), res.get("dec")
        _native("iscope_start_view",
                {"mode": "star", "target_ra_dec": [ra, dec],
                 "target_name": "scan", "lp_filter": False}, timeout=60)
        return True
    except Exception:
        return False


def grab_fresh(need_new=2, timeout=40, gain=80):
    """Start preview, wait until the frame counter advances, return JPEG."""
    before = frame_counter()
    start_preview(gain=gain)
    t0 = time.time()
    seen = None
    while time.time() - t0 < timeout:
        c = frame_counter(timeout=6)
        if c is not None and (before is None or c > before + need_new):
            seen = c
            break
        time.sleep(1.0)
    img = raw_frame()
    return img, {"counter_before": before, "counter_after": seen,
                 "waited_s": round(time.time() - t0, 1)}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "_fresh.jpg"
    img, meta = grab_fresh()
    print(json.dumps(meta))
    if not img:
        print("NO FRAME")
        sys.exit(1)
    with open(out, "wb") as f:
        f.write(img)
    print(f"OK {len(img)} bytes -> {out}")
