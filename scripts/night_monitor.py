# -*- coding: utf-8 -*-
"""Independent night supervisor - one check pass per invocation.

Why this exists
---------------
`night_watchdog.ps1` only handles "the runner process exited". It cannot see:

  * the runner being alive but wedged (no new frames for 20 minutes)
  * the seestar_alp backend having died while the runner keeps retrying
  * the whole task chain being gone

This script is deliberately STATELESS between runs and designed to be driven by
a 2-minute scheduled task, so there is no long-lived process that can itself die.
Cross-pass memory lives in data/monitor_state.json.

Remediation is conservative: it only acts when the normal chain is clearly broken,
so it never fights the runner for the device (the scope accepts a single TCP client).
"""
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

BJT = timezone(timedelta(hours=8))
STATE = ROOT / "data" / "monitor_state.json"
STATUS = ROOT / "data" / "monitor_status.json"
LOG = ROOT / "data" / "monitor.log"
ALERT = ROOT / "data" / "ALERT.txt"
STOPPED = ROOT / "data" / "STOPPED"
PLAN = ROOT / "scripts" / "night_plan.json"

BACKEND = "http://127.0.0.1:5555"
TASK = "SeestarNightRun"

_txid = [70000]


def _next_id():
    _txid[0] += 1
    return _txid[0]


def log(msg, level="info"):
    line = "[%s] %-8s %s" % (datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S"), level, msg)
    print(line)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def alert(msg):
    """Leave a loud breadcrumb the human will see in the morning."""
    try:
        with ALERT.open("a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass
    log(msg, "CRITICAL")


def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def alp_get(path, timeout=20):
    i = _next_id()
    url = "%s/api/v1/telescope/1/%s?ClientID=1&ClientTransactionID=%d" % (BACKEND, path, i)
    return http_json(url, timeout)


def native(method, params=None, timeout=30):
    """Raw native call through the Alpaca action tunnel."""
    i = _next_id()
    url = "%s/api/v1/telescope/1/action?ClientID=1&ClientTransactionID=%d" % (BACKEND, i)
    body = json.dumps({
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": i,
    }).encode()
    req = urllib.request.Request(url, data=body, method="PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        env = json.loads(r.read().decode("utf-8", "replace"))
    return env.get("Value")


def native_result(method, params=None, timeout=30):
    env = native(method, params, timeout)
    if isinstance(env, dict):
        return env.get("result")
    return None


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    st["updated_bjt"] = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def heartbeat_age_s():
    p = ROOT / "data" / "runner_state.json"
    if not p.exists():
        return None
    return time.time() - p.stat().st_mtime


def task_running():
    try:
        out = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK, "/FO", "LIST"],
            capture_output=True, text=True, timeout=30,
            encoding="mbcs", errors="replace",
        ).stdout
    except Exception as e:
        return None, "query failed: %s" % e
    low = out.lower()
    if "running" in low or "正在运行" in out:
        return True, out.strip().splitlines()[-1][:80] if out.strip() else ""
    return False, out.strip().splitlines()[-1][:80] if out.strip() else "unknown"


def start_backend():
    exe = ROOT / "seestar_alp" / ".venv" / "Scripts" / "python.exe"
    if not exe.exists():
        return False, "venv python missing"
    try:
        subprocess.Popen(
            [str(exe), "root_app.py"],
            cwd=str(ROOT / "seestar_alp"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
        )
        return True, "spawned root_app.py"
    except Exception as e:
        return False, str(e)


def restart_task():
    try:
        subprocess.run(["schtasks", "/End", "/TN", TASK], capture_output=True, timeout=30)
        time.sleep(2)
        subprocess.run(["schtasks", "/Run", "/TN", TASK], capture_output=True, timeout=30)
        return True
    except Exception as e:
        log("restart task failed: %s" % e, "ERROR")
        return False


def main():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    now = datetime.now(BJT)
    end = datetime.strptime(plan["absolute_end_bjt"], "%Y-%m-%d %H:%M").replace(tzinfo=BJT)

    if now >= end:
        log("已过绝对结束时间 %s，监工退出" % plan["absolute_end_bjt"])
        try:
            subprocess.run(["schtasks", "/Delete", "/TN", "SeestarMonitor", "/F"],
                           capture_output=True, timeout=30)
        except Exception:
            pass
        return 0

    st = load_state()
    prev_frames = st.get("frames")
    stall_since = st.get("stall_since")
    backend_down = int(st.get("backend_down", 0))
    dev_down = int(st.get("dev_down", 0))
    restarts = int(st.get("task_restarts", 0))

    now_ts = time.time()
    health = {"checked_bjt": now.strftime("%H:%M:%S")}

    # --- 1) backend reachable ---
    be_ok = False
    connected = None
    try:
        v = alp_get("connected")
        connected = v.get("Value")
        be_ok = v.get("ErrorNumber", 1) == 0
    except Exception as e:
        health["backend_error"] = str(e)[:80]

    if not be_ok:
        backend_down += 1
        health["backend"] = "down x%d" % backend_down
        log("后端 5555 不可达（第 %d 次）" % backend_down, "WARN")
        if backend_down >= 2:
            ok, why = start_backend()
            if ok:
                log("已拉起 seestar_alp 后端：%s" % why, "WARN")
                alert("后端 5555 掉线，监工已自动重启 seestar_alp")
                backend_down = 0
                time.sleep(25)
                try:
                    be_ok = alp_get("connected").get("ErrorNumber", 1) == 0
                except Exception:
                    pass
            else:
                alert("后端 5555 掉线且自动拉起失败：%s" % why)
        # 后端不在时，其余检查没有意义
        st.update({"frames": prev_frames, "stall_since": stall_since,
                   "backend_down": backend_down, "task_restarts": restarts,
                   "health": health})
        save_state(st)
        return 1

    backend_down = 0
    health["backend"] = "ok"

    # --- 2) device + telemetry ---
    dev = native_result("get_device_state") or {}
    pi = dev.get("pi_status") or {}
    mount = dev.get("mount") or {}
    health.update({
        "connected": connected,
        "battery": pi.get("battery_capacity"),
        "charging": pi.get("charger_status"),
        "temp_c": pi.get("temp"),
        "overtemp": pi.get("is_overtemp"),
        "parked": mount.get("close"),
        "tracking": mount.get("tracking"),
    })
    if not dev:
        dev_down += 1
        health["device"] = "no telemetry x%d" % dev_down
        log("设备无遥测（第 %d 次）" % dev_down, "WARN")
        if dev_down >= 5:
            alert("设备连续 %d 次无遥测（约 10 分钟），可能已离线" % dev_down)
    else:
        dev_down = 0
        health["device"] = "ok"

    # --- 3) imaging progress ---
    vs = native_result("get_view_state") or {}
    view = vs.get("View") or {}
    stk = view.get("Stack") or {}
    frames = stk.get("stacked_frame")
    scope_stage = stk.get("stage") or view.get("stage")
    target = view.get("target_name")
    health.update({"target": target, "stage": scope_stage, "frames": frames})

    if frames is None:
        frames = view.get("stacked_frame")

    STALL_S = 1200  # 20 min with no new frames = wedged
    if isinstance(frames, int) and isinstance(prev_frames, int):
        if frames > prev_frames:
            if stall_since:
                log("恢复推进：%d -> %d 帧" % (prev_frames, frames), "OK")
            stall_since = None
        else:
            if stall_since is None:
                stall_since = now_ts
            stalled_for = now_ts - stall_since
            health["stalled_s"] = int(stalled_for)
            if stalled_for >= STALL_S and scope_stage == "Stack":
                alert("叠加停止推进已 %d 分钟（停在 %d 帧，目标 %s）"
                      % (stalled_for // 60, frames, target))
    else:
        if scope_stage is None:
            health["note"] = "无活动 view"

    # --- 4) runner heartbeat ---
    age = heartbeat_age_s()
    health["heartbeat_age_s"] = None if age is None else int(age)
    running, detail = task_running()
    health["task_running"] = running

    if age is None or age > 240:
        # heartbeat stale: the runner may be dead or wedged
        if STOPPED.exists():
            # 运行器已正常收尾或保护性停止（写了 STOPPED 标记）——这是预期行为，
            # 绝不重启。否则会形成「重启 → 重新 goto → 天气不佳 → 再停」的
            # 机械臂反复展开/大幅转向循环（2026-10-19 22:08–22:19 实测发生）。
            log("运行器已正常收尾（STOPPED 标记存在），不重启", "OK")
            health["note"] = "runner stopped cleanly"
        elif not running:
            if restarts < 12:
                log("心跳 %s 秒未更新且任务未运行，重启任务（第 %d 次）"
                    % ("?" if age is None else int(age), restarts + 1), "WARN")
                if restart_task():
                    restarts += 1
                    alert("运行器心跳中断，监工已重启计划任务（第 %d 次）" % restarts)
            else:
                alert("心跳中断但重启次数已达上限 12 次，请人工介入")
        else:
            log("心跳 %s 秒未更新，但任务显示运行中"
                % ("?" if age is None else int(age)), "WARN")

    # --- 5) over-temperature escalation (runner stops at 80C, we escalate at 82C) ---
    temp = pi.get("temp")
    if isinstance(temp, (int, float)) and temp >= 82 and not mount.get("close"):
        alert("机身温度 %.1f°C 超过 82°C，监工直接执行 park 保护" % temp)
        try:
            native("scope_park", timeout=120)
            time.sleep(20)
            d2 = native_result("get_device_state") or {}
            if (d2.get("mount") or {}).get("close"):
                log("已确认折叠停泊", "OK")
            else:
                alert("park 已下发但 20 秒内未确认折叠")
        except Exception as e:
            alert("park 下发失败：%s" % e)

    st.update({
        "frames": frames if isinstance(frames, int) else prev_frames,
        "stall_since": stall_since,
        "backend_down": backend_down,
        "dev_down": dev_down,
        "task_restarts": restarts,
        "health": health,
    })
    save_state(st)
    STATUS.write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")

    log("检查完成 目标=%s 帧=%s 阶段=%s 温度=%s 电量=%s 心跳=%ss 任务=%s"
        % (target, frames, scope_stage, temp, pi.get("battery_capacity"),
           "?" if age is None else int(age), running))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log("监工崩溃:\n" + traceback.format_exc(), "ERROR")
        sys.exit(1)
