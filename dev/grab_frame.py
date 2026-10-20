"""Grab a single frame from the seestar_alp MJPEG stream (port 7556).

Usage:
    python grab_frame.py <outfile.jpg> [device_num] [timeout_s]

The stream is multipart/x-mixed-replace. We read raw bytes until we have a
complete JPEG (SOI .. EOI) and write it out. No third-party deps.
"""
from __future__ import annotations

import socket
import sys
import time


def grab(host: str, port: int, dev: int, timeout: float) -> bytes | None:
    s = socket.create_connection((host, port), timeout=10)
    s.settimeout(timeout)
    req = (
        f"GET /{dev}/vid HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Accept: multipart/x-mixed-replace\r\n"
        "Connection: close\r\n\r\n"
    )
    s.sendall(req.encode())

    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        # Look for a complete JPEG
        start = buf.find(b"\xff\xd8\xff")
        if start >= 0:
            end = buf.find(b"\xff\xd9", start)
            if end > 0:
                s.close()
                return buf[start:end + 2]
    s.close()
    return None


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "frame.jpg"
    dev = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    tmo = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
    img = grab("127.0.0.1", 7556, dev, tmo)
    if not img:
        print("NO FRAME")
        sys.exit(1)
    with open(out, "wb") as f:
        f.write(img)
    print(f"OK {len(img)} bytes -> {out}")
