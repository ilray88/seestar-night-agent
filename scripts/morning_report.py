"""Morning review: what got captured, and is the scope safely parked.

Run after the night finishes:
    python morning_report.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "scripts")
import night_runner as NR

BJT = NR.BJT


def main():
    print("=" * 62)
    print(" Seestar S30 Pro 观测结果")
    print("=" * 62)

    # --- device state ---
    st = NR.try_native("get_device_state") or {}
    mount = st.get("mount") or {}
    pi = st.get("pi_status") or {}
    storage = (st.get("storage") or {}).get("storage_volume") or [{}]
    print("\n[设备状态]")
    if NR.real_pointing() or mount:
        print(f"  在线: 是")
        print(f"  机械臂折叠(park): {'是 ✓' if mount.get('close') else '否 ← 注意'}")
        print(f"  电池: {pi.get('battery_capacity')}%  ({pi.get('charger_status')})")
        print(f"  温度: {pi.get('temp')}°C")
        print(f"  存储: 剩余 {storage[0].get('free_mb')} MB "
          if storage else "  存储: ?")

    # --- run state ---
    state_file = Path("./data/runner_state.json")
    if state_file.exists():
        rs = json.loads(state_file.read_text(encoding="utf-8"))
        print("\n[运行收尾]")
        print(f"  阶段: {rs.get('phase')}")
        print(f"  时间: {rs.get('updated_bjt')}")
        if rs.get("reason"):
            print(f"  原因: {rs.get('reason')}")

    # --- events summary ---
    ev = Path("./data/events.jsonl")
    if ev.exists():
        rows = [json.loads(l) for l in ev.read_text(encoding="utf-8").splitlines() if l.strip()]
        night = [r for r in rows if r.get("ts_bjt", "") >= "19:00"]
        print("\n[各目标执行情况]")
        for r in night:
            if r["kind"] in ("target_start", "slew_done", "stack_start",
                             "slot_end", "hard_stop", "cable_alert", "warn"):
                mark = {"target_start": "▶", "slew_done": "  ", "stack_start": "  ",
                        "slot_end": "  ", "hard_stop": "!!", "cable_alert": "!!",
                        "warn": " ?"}.get(r["kind"], "  ")
                print(f"  {mark} {r.get('ts_bjt')} {r.get('msg','')}")
        stops = [r for r in night if r["kind"] in ("hard_stop", "cable_alert")]
        if stops:
            print("\n  ⚠ 夜间触发过保护性停止：")
            for s in stops:
                print(f"    {s.get('ts_bjt')} {s.get('msg')}")
        else:
            print("\n  ✓ 夜间未触发保护性停止")

    # --- albums on device ---
    print("\n[设备上的作品]")
    try:
        albums = NR.try_native("get_albums") or {}
        for grp in (albums.get("list") or []):
            print(f"  · {grp.get('name')}")
            for item in (grp.get("list") or [])[:12]:
                files = item.get("files") or []
                print(f"      {item.get('name')}  ({len(files)} files)")
    except Exception as e:
        print(f"  读取失败: {e}")

    print("\n[下一步]")
    print("  拉取成品图:  python scripts/fetch_results.py")
    print("  查看日志:    data\\events.jsonl")
    print("=" * 62)


if __name__ == "__main__":
    main()
