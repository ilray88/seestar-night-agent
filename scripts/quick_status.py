"""One-shot status snapshot for the night run.

Prints the runner heartbeat file, the live device state (target / stage /
frames / exposure / filter wheel), and the tail of the event log.  Used by the
20-minute check-ins so every report is built from the same fields.

Run with seestar_alp venv (needs only stdlib):
    python scripts/quick_status.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BJT = timezone(timedelta(hours=8))
BACKEND = "http://127.0.0.1:5555"
_tx = [90000]


def native(method: str, params=None, timeout: float = 30.0):
    _tx[0] += 1
    body = json.dumps({
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": _tx[0],
    }).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/v1/telescope/1/action", data=body,
        headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def res(env):
    v = (env or {}).get("Value") or {}
    if "error" in v:
        raise RuntimeError(f"{v.get('error')} (code {v.get('code')})")
    return v.get("result")


def main():
    now = datetime.now(BJT)
    print(f"===== quick status @ {now:%Y-%m-%d %H:%M:%S} =====")

    # runner heartbeat / monitor status
    for name in ("monitor_status.json", "runner_state.json"):
        p = ROOT / "data" / name
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                keys = ["checked_bjt", "target", "stage", "frames", "temp_c",
                        "battery", "parked", "heartbeat_age_s", "task_running"]
                bits = [f"{k}={d[k]}" for k in keys if k in d]
                print(f"  {name}: " + "  ".join(bits))
            except Exception as e:
                print(f"  {name}: unreadable ({e})")

    # live device
    try:
        view = res(native("get_view_state"))["View"]
        stk = view.get("Stack") or {}
        exp = (stk.get("Exposure") or {}).get("exp_ms")
        print(f"  DEVICE: target={view.get('target_name')} "
              f"state={view.get('state')} stage={view.get('stage')} "
              f"stacked={stk.get('stacked_frame')} "
              f"dropped={stk.get('dropped_frame')} exp_ms={exp}")
    except Exception as e:
        print(f"  DEVICE view: ERROR {e}")

    try:
        wheel = res(native("get_wheel_position"))
        names = {0: "DARK", 1: "IRCUT", 2: "LP"}
        print(f"  FILTER: wheel={wheel} ({names.get(wheel, '?')})")
    except Exception as e:
        print(f"  FILTER: ERROR {e}")

    try:
        dev = res(native("get_device_state"))
        pi = dev.get("pi_status") or {}
        print(f"  POWER: temp={pi.get('temp')}C batt={pi.get('battery_capacity')}% "
              f"chg={pi.get('charger_status')} overtemp={pi.get('is_overtemp')}")
        print(f"  EXP SETTING: {(dev.get('setting') or {}).get('exp_ms')}")
    except Exception as e:
        print(f"  POWER: ERROR {e}")

    # event tail
    ev = ROOT / "data" / "events.jsonl"
    if ev.exists():
        lines = ev.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]
        print("  --- recent events ---")
        for ln in lines:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            print(f"    {e.get('ts_bjt')} {e.get('kind'):<16} "
                  f"{(e.get('msg') or '')[:64]}")

    alert = ROOT / "data" / "ALERT.txt"
    if alert.exists():
        txt = alert.read_text(encoding="utf-8", errors="replace").strip()
        if txt:
            print("  --- ALERT ---")
            for ln in txt.splitlines()[-6:]:
                print(f"    {ln}")
    else:
        print("  ALERT: none")

    print(f"  STOPPED marker: {(ROOT / 'data' / 'STOPPED').exists()}")


if __name__ == "__main__":
    main()
