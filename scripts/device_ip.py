"""Resolve the telescope's IP from the single source of truth.

The backend reads ``seestar_alp/device/config.toml``; every helper script
reads the same file through here, so changing the scope's address (new WiFi,
new DHCP lease) is a one-line edit that reaches all of them at once.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "seestar_alp" / "device" / "config.toml"

# Only used when the config file is missing or malformed.
FALLBACK = "192.168.20.90"

_IP_RE = re.compile(r'^\s*ip_address\s*=\s*["\']([0-9]{1,3}(?:\.[0-9]{1,3}){3})["\']', re.M)


def device_ip() -> str:
    """Return the first non-loopback ``ip_address`` in the device config."""
    try:
        text = CONFIG.read_text(encoding="ascii")
    except OSError:
        return FALLBACK
    for m in _IP_RE.finditer(text):
        ip = m.group(1)
        if not ip.startswith("127."):
            return ip
    return FALLBACK


def device_base() -> str:
    return f"http://{device_ip()}"


if __name__ == "__main__":
    print(device_ip())
