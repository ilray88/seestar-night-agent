"""反复检查日志里最新的 auto_power_off 值，等待新的 get_device_state。"""
import re
import time

LOG = r"C:\Users\BGSJIA\seestar-agent\seestar_alp\alpyca.log"


def latest():
    last = None
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "'method': 'get_device_state'" in line and "'setting':" in line:
                last = line
    if not last:
        return None
    ts = re.search(r"'Timestamp':\s*'([\d.]+)'", last)
    ap = re.search(r"'auto_power_off':\s*(True|False)", last)
    return (ts.group(1) if ts else "?", ap.group(1) if ap else "?")


first = latest()
print("起始:", first)
for i in range(12):
    time.sleep(5)
    cur = latest()
    if cur != first:
        print(f"  检测到更新 -> Timestamp={cur[0]}  auto_power_off={cur[1]}")
        if cur[1] == "False":
            print("SUCCESS: auto_power_off 已变为 False")
            break
        first = cur
    else:
        print(f"  [{i*5+5}s] 无新轮询 (仍是 {cur[0]})")
