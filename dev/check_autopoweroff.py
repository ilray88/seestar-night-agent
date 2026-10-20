"""验证 Seestar 的 auto_power_off 当前真实值（读取设备原生状态）。"""
import json
import re
import sys

LOG = r"C:\Users\BGSJIA\seestar-agent\seestar_alp\alpyca.log"


def latest_device_state():
    last = None
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "'method': 'get_device_state'" in line and "'setting':" in line:
                last = line
    if not last:
        return None
    m = re.search(r"'auto_power_off':\s*(True|False)", last)
    ap = re.search(r"'alpaca_enable':\s*(True|False)", last)
    bat = re.search(r"'battery_capacity':\s*(\d+)", last)
    return {
        "auto_power_off": m.group(1) if m else "?",
        "alpaca_enable": ap.group(1) if ap else "?",
        "battery": bat.group(1) if bat else "?",
        "line_len": len(last),
    }


if __name__ == "__main__":
    print(json.dumps(latest_device_state(), indent=2))
