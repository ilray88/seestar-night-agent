"""诊断：确认 get_device_state 返回的是不是最新值。"""
import json
import re

LOG = r"C:\Users\BGSJIA\seestar-agent\seestar_alp\alpyca.log"

lines = []
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if "'method': 'get_device_state'" in line:
            lines.append(line)

print(f"get_device_state 出现次数: {len(lines)}")
for line in lines[-3:]:
    ts = re.search(r"'Timestamp':\s*'([\d.]+)'", line)
    ap = re.search(r"'auto_power_off':\s*(True|False)", line)
    print(f"  Timestamp={ts.group(1) if ts else '?'}  auto_power_off={ap.group(1) if ap else '?'}")

print()
print("=== 所有 set_setting 的响应 ===")
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if "'method': 'set_setting'" in line and "response:" in line:
            print("  " + line.strip()[:400])
