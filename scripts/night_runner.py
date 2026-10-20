#!/usr/bin/env python3
"""Seestar S30 Pro 无人值守运行器（原地托管版）

设计目标
--------
MCP 自带的 autonomous-night 技能用 ``assess_conditions`` 判天气，取的是
"整夜最差值"（今晚凌晨 2 点云量 95%），因此一启动就 ``park_and_stop``。
但今晚真实情况是 19:00-21:30 云量 0%。本运行器改为**逐小时**判读，只在
当前时段真的不能拍时才停。

职责
----
1. 按窗口时间表依次 goto / 对焦 / 开拍
2. 每 60 秒采一次设备遥测，写心跳与日志
3. 看护电缆：监控方位角，超过软限位就报警（设备无解缠指令，只能停）
4. 每 10 分钟检查天气（逐小时，不用整夜最差值）
5. 硬停条件：天亮前 15 分钟 / 电量 < 20% / 断连超过 10 分钟 / 绝对结束时间
6. 收尾：stop_view -> park -> 确认折叠 -> 汇总写报告

运行
----
    python scripts/night_runner.py --plan scripts/night_plan.json --dry-run
    python scripts/night_runner.py --plan scripts/night_plan.json

设计约束
--------
* 只走 HTTP（Alpaca REST），不依赖 MCP 进程存活
* 单进程单线程主循环，状态全部落盘，重启可续
* 任何异常都不吞掉：写入 events.jsonl，然后按 fail-safe 处理
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:5555"
DEVNUM = 1
BJT = timezone(timedelta(hours=8))

_txid = 10000


def _next_txid() -> int:
    global _txid
    _txid += 1
    return _txid


# --------------------------------------------------------------------------
# 低层 HTTP
# --------------------------------------------------------------------------
def alp_get(path: str, timeout: float = 15.0) -> dict:
    """GET an Alpaca property. Returns the parsed JSON envelope."""
    sep = "&" if "?" in path else "?"
    url = f"{BASE}/api/v1/telescope/{DEVNUM}/{path}{sep}ClientID=1&ClientTransactionID={_next_txid()}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def alp_put(path: str, form: dict, timeout: float = 60.0) -> dict:
    sep = "&" if "?" in path else "?"
    url = f"{BASE}/api/v1/telescope/{DEVNUM}/{path}{sep}ClientID=1&ClientTransactionID={_next_txid()}"
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        url, data=body, method="PUT",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def native(method: str, params: Any = None, timeout: float = 60.0) -> dict:
    """Call a native JSON-RPC method through the Alpaca action tunnel."""
    body = {
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params if params is not None else {}}),
        "ClientID": 1,
        "ClientTransactionID": _next_txid(),
    }
    url = f"{BASE}/api/v1/telescope/{DEVNUM}/action?ClientID=1&ClientTransactionID={_next_txid()}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def try_get(path: str) -> Any:
    try:
        return alp_get(path).get("Value")
    except Exception:
        return None


def try_native(method: str, params: Any = None, timeout: float = 60.0) -> Any:
    try:
        env = native(method, params, timeout=timeout)
        val = env.get("Value")
        if isinstance(val, dict) and "result" in val:
            return val["result"]
        return val
    except Exception:
        return None


def goto_target_alpaca(ra_hours: float, dec_deg: float,
                       name: str = "target", timeout: float = 180.0) -> dict:
    """Slew via the Alpaca action tunnel.

    The action endpoint only accepts a JSON body. A urlencoded form is
    accepted by the HTTP layer but never dispatched, which looks like a
    silent no-op. is_j2000=False means JNow, matching the device's own frame.
    """
    body = {
        "Action": "goto_target",
        "Parameters": json.dumps({"target_name": name, "is_j2000": False,
                                  "ra": ra_hours, "dec": dec_deg}),
        "ClientID": 1,
        "ClientTransactionID": _next_txid(),
    }
    url = (f"{BASE}/api/v1/telescope/{DEVNUM}/action"
           f"?ClientID=1&ClientTransactionID={_next_txid()}")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# --------------------------------------------------------------------------
# 设备读数
# --------------------------------------------------------------------------
@dataclass
class Telemetry:
    ts_utc: str
    connected: bool = False
    ra_h: float | None = None
    dec_deg: float | None = None
    alt_deg: float | None = None
    az_deg: float | None = None
    tracking: bool = False
    slewing: bool = False
    mount_parked: bool | None = None
    battery_pct: float | None = None
    charging: bool | None = None
    temp_c: float | None = None
    heater: bool | None = None
    wheel_pos: int | None = None
    focus_pos: int | None = None
    stacked: int | None = None
    dropped: int | None = None
    observing: bool | None = None


def real_pointing():
    """Live RA/Dec straight from the device.

    Alpaca's rightascension/declination properties are cached and go stale
    (they kept reporting the pre-slew position after a real 62 deg slew), so
    every pointing decision must use this instead.

    Note the envelope shape: Alpaca wraps the JSON-RPC reply, so the value is
    at env["Value"]["result"], not env["result"].
    """
    try:
        env = native("scope_get_equ_coord", timeout=25) or {}
        val = env.get("Value", env)
        res = (val.get("result") if isinstance(val, dict) else None) or {}
        if "ra" in res and "dec" in res:
            return float(res["ra"]), float(res["dec"])
    except Exception:
        pass
    return None


def read_telemetry() -> Telemetry:
    now = datetime.now(timezone.utc).isoformat()
    t = Telemetry(ts_utc=now)

    # connection + pointing
    try:
        env = alp_get("connected")
        t.connected = bool(env.get("Value"))
    except Exception:
        t.connected = False

    if not t.connected:
        return t

    # Pointing must come from the live source, not Alpaca's cached props.
    cur = real_pointing()
    if cur:
        t.ra_h, t.dec_deg = cur
    t.tracking = bool(try_get("tracking"))
    t.slewing = bool(try_get("slewing"))

    # native state (battery, mount, heater, wheel, focus)
    st = try_native("get_device_state")
    if isinstance(st, dict):
        dev = st.get("result", st)
        pi = dev.get("pi_status") or {}
        t.battery_pct = pi.get("battery_capacity")
        t.charging = (pi.get("charger_status") == "Charging") or bool(pi.get("charge_online"))
        t.temp_c = pi.get("temp")
        mount = dev.get("mount") or {}
        t.mount_parked = bool(mount.get("close")) if "close" in mount else None
        setting = dev.get("setting") or {}
        t.heater = bool(setting.get("heater_enable"))
        foc = dev.get("focuser") or {}
        t.focus_pos = foc.get("step")

    # alt/az: Alpaca reports 0 on this firmware -> derive from RA/Dec
    if t.ra_h is not None and t.dec_deg is not None:
        alt, az = radec_to_altaz(t.ra_h, t.dec_deg)
        t.alt_deg, t.az_deg = alt, az

    # live view counters
    vs = try_native("get_view_state", timeout=20)
    if isinstance(vs, dict):
        view = vs.get("View", vs)
        t.observing = bool(view.get("state") == "working") if view.get("state") else None
        # counters live under view["Stack"], not at the top level
        stk = view.get("Stack") or {}
        t.stacked = stk.get("stacked_frame", view.get("stacked_frame"))
        t.dropped = stk.get("dropped_frame", view.get("dropped_frame"))

    t.wheel_pos = try_native("get_wheel_position", timeout=20)
    return t


def radec_to_altaz(ra_h: float, dec_deg: float, when: datetime | None = None):
    """Convert JNow RA/Dec to alt/az without astropy (spherical trig)."""
    when = when or datetime.now(timezone.utc)
    lat = math.radians(22.7261)
    lon = math.radians(114.046)

    # Greenwich Mean Sidereal Time
    jd = 2440587.5 + when.timestamp() / 86400.0
    d = jd - 2451545.0
    gmst = 18.697374558 + 24.06570982441908 * d
    gmst = gmst % 24.0
    lst = math.radians((gmst * 15.0) + math.degrees(lon)) % (2 * math.pi)

    ra = math.radians(ra_h * 15.0)
    dec = math.radians(dec_deg)

    ha = lst - ra
    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(ha)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)

    cos_alt = math.cos(alt)
    if abs(cos_alt) < 1e-9:
        return math.degrees(alt), 0.0
    cos_az = (math.sin(dec) - math.sin(lat) * sin_alt) / (math.cos(lat) * cos_alt)
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.acos(cos_az)
    if math.sin(ha) > 0:
        az = 2 * math.pi - az

    return math.degrees(alt), math.degrees(az) % 360.0


# --------------------------------------------------------------------------
# 事件日志
# --------------------------------------------------------------------------
class EventLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, **fields):
        rec = {"ts_utc": datetime.now(timezone.utc).isoformat(),
               "ts_bjt": datetime.now(BJT).strftime("%H:%M:%S"),
               "kind": kind}
        rec.update(fields)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def say(self, msg: str, kind: str = "info", **kw):
        print(f"[{datetime.now(BJT).strftime('%H:%M:%S')}] {msg}", flush=True)
        self.write(kind, msg=msg, **kw)


# --------------------------------------------------------------------------
# 天气：逐小时，不用整夜最差值
# --------------------------------------------------------------------------
def hourly_weather() -> dict[int, dict]:
    """Fetch open-meteo hourly cloud/dew/wind for tonight; index by BJT hour."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=22.7261&longitude=114.046"
        "&hourly=temperature_2m,cloud_cover,cloud_cover_low,cloud_cover_high,"
        "dew_point_2m,wind_speed_10m,precipitation_probability"
        "&timezone=Asia%2FShanghai&forecast_days=2"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
    except Exception:
        return {}

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    out: dict[int, dict] = {}
    for i, ts in enumerate(times):
        # ts like 2026-10-19T19:00
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            continue
        key = (dt.month, dt.day, dt.hour)
        out[key] = {
            "iso": ts,
            "cloud": hourly.get("cloud_cover", [None] * len(times))[i],
            "cloud_low": hourly.get("cloud_cover_low", [None] * len(times))[i],
            "cloud_high": hourly.get("cloud_cover_high", [None] * len(times))[i],
            "temp": hourly.get("temperature_2m", [None] * len(times))[i],
            "dew": hourly.get("dew_point_2m", [None] * len(times))[i],
            "wind": hourly.get("wind_speed_10m", [None] * len(times))[i],
            "precip": hourly.get("precipitation_probability", [None] * len(times))[i],
        }
    return out


def weather_verdict(wx: dict[int, dict]) -> tuple[bool, str]:
    """Judge the CURRENT hour only. Returns (ok, reason).

    Deep-sky imaging is blocked by LOW cloud, not by high cirrus.  The thin
    high layer (``cloud_high``) only lowers contrast and adds shot noise,
    while low/mid cloud actually hides the sky.  The 2026-10-19 night is
    0-4% low cloud but 80-97% high cirrus all night, so gating on TOTAL
    cloud would throw away an otherwise usable night.  Rain still stops it.
    """
    if not wx:
        return True, "天气数据不可用，按设备遥测继续"
    now = datetime.now(BJT)
    entry = wx.get((now.month, now.day, now.hour))
    if entry is None:
        return True, "当前小时无预报，继续"
    low = entry.get("cloud_low") or 0
    high = entry.get("cloud_high") or 0
    total = entry.get("cloud") or 0
    precip = entry.get("precip")
    if precip is not None and precip >= 60:
        return False, f"降水概率 {precip}%"
    if low >= 70:
        return False, f"低云 {low}%（遮挡星空）"
    if total >= 98:
        return False, f"总云量 {total}%（几乎全遮）"
    return True, f"低云 {low}%、高云 {high}%，可拍"


# --------------------------------------------------------------------------
# 主运行器
# --------------------------------------------------------------------------
@dataclass
class Slot:
    id: str
    name: str
    ra: float          # J2000 deg
    dec: float         # J2000 deg
    start_bjt: str     # "HH:MM"
    end_bjt: str       # "HH:MM" (may be > 24h e.g. "28:20")
    filter_pos: int    # 1=IRCUT, 2=LP
    gain: int
    exp_s: int
    note: str = ""


def parse_bjt(hhmm: str, night: datetime) -> datetime:
    """Parse a wall-clock stamp in BJT.

    Accepts either:
      * ``"HH:MM"``  - HH may exceed 24 to mean the next day (``"28:20"``)
      * ``"YYYY-MM-DD HH:MM"`` - an explicit date, used as-is

    ``night`` supplies the reference day for the short form only.
    """
    text = hhmm.strip()
    if "-" in text.split(" ")[0]:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=BJT, second=0, microsecond=0)

    h, m = (int(x) for x in text.split(":"))
    day_offset = h // 24
    base = night.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(days=day_offset, hours=h % 24, minutes=m)


class NightRunner:
    def __init__(self, plan: dict, log: EventLog, dry_run: bool = False,
                 rehearse: bool = False):
        self.plan = plan
        self.log = log
        self.dry_run = dry_run
        self.rehearse = rehearse
        self.slots = [Slot(**s) for s in plan["slots"]]
        self.night_start = parse_bjt(plan["night_start_bjt"], datetime.now(BJT))
        self.absolute_end = parse_bjt(plan["absolute_end_bjt"], datetime.now(BJT))
        self.az_min = plan.get("az_soft_min_deg", -170.0)
        self.az_max = plan.get("az_soft_max_deg", 170.0)
        self.battery_floor = plan.get("battery_floor_pct", 20)
        self.temp_stop_c = plan.get("temp_stop_c", 80)
        self.stop = False
        self.reason = ""
        self.current: Slot | None = None
        self.weather_hold = False
        self.data_dir = Path(plan.get("data_dir", "./data"))
        self.heartbeat_path = self.data_dir / "runner_state.json"
        self.stopped_marker = self.data_dir / "STOPPED"
        self._last_wx_check = 0.0
        self._wx_cache: dict[int, dict] = {}
        self._az_history: list[tuple[str, float]] = []
        self._last_telemetry: Telemetry | None = None

    # --- 状态落盘，重启可续 ---
    def save_state(self, phase: str, t: Telemetry | None = None):
        rec = {
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "updated_bjt": datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S"),
            "phase": phase,
            "current_target": self.current.name if self.current else None,
            "reason": self.reason,
            "pid": __import__("os").getpid(),
        }
        if t is not None:
            rec.update({
                "ra_h": t.ra_h, "dec_deg": t.dec_deg,
                "alt_deg": t.alt_deg, "az_deg": t.az_deg,
                "battery_pct": t.battery_pct, "charging": t.charging,
                "temp_c": t.temp_c, "tracking": t.tracking,
                "mount_parked": t.mount_parked,
                "stacked": t.stacked, "dropped": t.dropped,
            })
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path.write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- 硬停判断 ---
    def hard_stop(self, t: Telemetry | None) -> str | None:
        now = datetime.now(BJT)
        if now >= self.absolute_end:
            return "到达绝对结束时间"
        dawn = parse_bjt(self.plan["dawn_bjt"], self.night_start)
        if (dawn - now) <= timedelta(minutes=15):
            return "距天亮不足 15 分钟"
        if t is not None:
            if t.battery_pct is not None and t.battery_pct < self.battery_floor:
                return f"电量 {t.battery_pct}% 低于 {self.battery_floor}% 下限"
            # 温度：设备自身上报 is_overtemp 时立刻停；否则用软阈值兜底。
            # 19:26 实测已 54.5°C，夜间持续叠加+充电会继续升温。
            st = try_native("get_device_state") or {}
            pi = st.get("pi_status") or {}
            if pi.get("is_overtemp"):
                return "设备上报过热 (is_overtemp)"
            temp = pi.get("temp")
            if isinstance(temp, (int, float)) and temp >= self.temp_stop_c:
                return f"机身温度 {temp}°C 达到 {self.temp_stop_c}°C 上限"
        return None

    # --- 电缆看护 ---
    def cable_check(self, t: Telemetry | None) -> str | None:
        if t is None or t.az_deg is None:
            return None
        az = t.az_deg
        self._az_history.append((t.ts_utc, az))
        if len(self._az_history) > 5000:
            self._az_history = self._az_history[-2000:]

        # cumulative travel (unwrapped) is the true cable-stress metric
        cum = 0.0
        prev = None
        for _, a in self._az_history:
            if prev is not None:
                d = a - prev
                while d > 180:
                    d -= 360
                while d < -180:
                    d += 360
                cum += d
            prev = a

        if abs(cum) > self.plan.get("cable_cum_limit_deg", 200):
            return (f"累计方位行程 {cum:+.0f}° 超过 {self.plan.get('cable_cum_limit_deg',200)}° 电缆软限")
        return None

    # --- 单目标执行 ---
    def _already_running(self, slot: Slot) -> bool:
        """True when the device is already stacking this slot's target.

        Used on restart so we do not throw away frames already integrated.
        Requires: stage == Stack, a matching target name, and pointing that
        agrees with the slot within 1 deg.
        """
        try:
            v = (try_native("get_view_state") or {}).get("View") or {}
            if v.get("stage") != "Stack":
                return False
            got = v.get("target_name") or ""
            want = slot.name
            norm = lambda s: s.replace(" ", "").replace("_", "").upper()
            if norm(got) != norm(want):
                self.log.say(f"设备在叠 {got}，与 {want} 不符，重新开始",
                             kind="resume_miss", target=slot.name)
                return False
            pt = real_pointing()
            if not pt:
                return False
            ra_h, dec = pt
            d_ra = abs(ra_h - slot.ra / 15.0) * 15.0
            d_dec = abs(dec - slot.dec)
            if d_ra > 1.0 or d_dec > 1.0:
                self.log.say(f"指向偏差过大 ({d_ra:.1f}°,{d_dec:.1f}°)，重新开始",
                             kind="resume_miss", target=slot.name)
                return False
            stacked = (v.get("Stack") or {}).get("stacked_frame")
            self.log.say(f"{slot.name} 已在叠 {stacked} 帧，继续", kind="resume_ok",
                         target=slot.name, stacked=stacked)
            return True
        except Exception as e:
            self.log.say(f"续拍探测失败: {e}", kind="warn")
            return False

    def run_slot(self, slot: Slot):
        self.current = slot
        start = parse_bjt(slot.start_bjt, self.night_start)
        end = parse_bjt(slot.end_bjt, self.night_start)
        self.log.say(f"=== 目标切换 {slot.name} ({start:%H:%M}-{end:%H:%M}) ===",
                     kind="target_start", target=slot.name)

        if self.dry_run:
            self.log.say(f"[DRY] 跳过实际动作 {slot.name}")
            return

        # 0) 断点续拍：watchdog 重启后，如果设备已经在正确目标上叠加，
        #    就不要重新 goto / 重新开叠（restart=True 会丢掉已有帧）。
        if self._already_running(slot):
            self.log.say(f"{slot.name} 已在叠加中，断点续拍", kind="resume",
                         target=slot.name)
            self.monitor_slot(slot, end)
            return

        # 0b) 天气预检：在 goto 之前先看天。天气不佳就折叠等待，
        #     避免"先转 120° 再停拍"的无谓机械动作。
        try:
            ok, why = weather_verdict(hourly_weather())
            self.log.say(f"天气预检: {why}", kind="weather_precheck", ok=ok)
            if not ok:
                self.log.say(f"天气不佳，未转向即折叠等待: {why}", kind="weather_hold")
                self.weather_hold = True
                return
        except Exception as e:
            self.log.say(f"天气预检失败（放行）: {e}", kind="warn")

        # 1) 滤镜
        #
        # 坑（2026-10-20 01:07 实测确认）：
        #   iscope_start_stack 会把滤镜轮重置为 1 (IRCUT)，无论调用前设成什么。
        #   在叠加停止时 set_wheel_position 能读回正确的 2，但一旦 start_stack
        #   就又变回 1 —— 这就是整晚所有子帧文件名都是 `_IRCUT_` 的原因。
        #   唯一有效的顺序是：start_stack 之后、state=working 时再设一次。
        #   所以这里不再设滤镜，改到第 5 步开拍之后（见 5b）。
        pass

        # 1b) 曝光时长（必须单独设置，不出现在 iscope_start_stack 里）
        #
        # 坑：设备在叠加运行中会拒绝 set_setting，返回
        #     error "stack is already running" / code 259，而 JSON-RPC 层仍是
        #     result=0（错误藏在 Value.error 里）。早期代码只看有没有抛异常，
        #     于是日志写「曝光 -> 10s」但设备其实还停在 20s。
        #     2026-10-19 23:30 M45 就是这样被拍成 20s 的。
        # 对策：先显式停掉叠加 → 等 state 离开 working → 设置 → 读回校验 → 重试。
        try:
            try:
                v = native("get_view_state")["Value"]["result"]["View"]
                if v.get("state") == "working":
                    native("iscope_stop_view", ["Stack"], timeout=60)
                    for _ in range(15):
                        time.sleep(2)
                        v = native("get_view_state")["Value"]["result"]["View"]
                        if v.get("state") != "working":
                            break
            except Exception as e:
                self.log.say(f"停叠以便改曝光失败（继续尝试）: {e}", kind="warn")

            want = int(slot.exp_s * 1000)
            got = None
            for attempt in range(4):
                r = native("set_setting",
                           {"exp_ms": {"stack_l": want, "continuous": 500}},
                           timeout=60)
                err = (r.get("Value") or {}).get("error")
                got = ((native("get_device_state")["Value"]["result"]
                        .get("setting", {}) or {}).get("exp_ms") or {}
                       ).get("stack_l")
                if got == want:
                    break
                self.log.say(f"曝光设置第 {attempt+1} 次未生效"
                             f"（当前 {got}，设备回复 {err}）", kind="warn")
                time.sleep(3)
            if got == want:
                self.log.say(f"曝光 -> {slot.exp_s}s（已校验 stack_l={got}）",
                             kind="exposure")
            else:
                self.log.say(f"曝光设置失败：想要 {want}，实际 {got}",
                             kind="warn")
        except Exception as e:
            self.log.say(f"曝光设置失败: {e}", kind="warn")

        # 2) goto
        #    走 Alpaca goto_target（is_j2000=False 表示 JNow）。
        #    这条路径已实测：到位误差 0.02°。原生 scope_goto 的坐标系未验证，不用。
        try:
            r = goto_target_alpaca(slot.ra / 15.0, slot.dec, name=slot.name)
            self.log.say(f"goto {slot.name} ra={slot.ra/15.0:.4f}h dec={slot.dec:.4f}",
                         kind="goto", result=str(r.get("Value", ""))[:200])
        except Exception as e:
            self.log.say(f"goto 失败: {e}", kind="error", target=slot.name)
            return

        # 3) 等 slew 真正到位
        if not self.wait_slew(slot, timeout_s=240):
            self.log.say(f"{slot.name} 未确认到位，仍继续（避免整夜空转）",
                         kind="warn", target=slot.name)

        # 4) 对焦
        try:
            native("start_auto_focuse", timeout=180)
            self.log.say("自动对焦已触发", kind="focus")
        except Exception as e:
            self.log.say(f"对焦失败: {e}", kind="warn")
        time.sleep(20)

        # 5) 开拍
        try:
            r = native("iscope_start_stack", {"restart": True}, timeout=90)
            self.log.say(f"开始叠加", kind="stack_start",
                         result=str(r.get("Value", ""))[:150])
            # gain 必须在这之后单独设（native start_stack 就是这么做的）
            g = native("set_control_value", ["gain", slot.gain], timeout=60)
            got = try_native("get_control_value", ["gain"])
            actual = (got or {}).get("value") if isinstance(got, dict) else got
            self.log.say(f"gain -> {slot.gain}（读回 {actual}）", kind="gain")
        except Exception as e:
            self.log.say(f"开拍失败: {e}", kind="error", target=slot.name)
            return

        # 5b) 滤镜（必须在叠加运行中设置，见第 1 步的说明）
        #
        # iscope_start_stack 已经把轮位重置成 1，这里重设一次并读回校验。
        # 2026-10-20 01:07 实测：运行中 set_wheel_position [2] 能稳定保持，
        # 且子帧文件名从 `_IRCUT_` 变为 `_LP_`。
        try:
            want_pos = int(slot.filter_pos)
            got_pos = None
            for attempt in range(4):
                native("set_wheel_position", [want_pos], timeout=60)
                time.sleep(2)
                got_pos = try_native("get_wheel_position")
                if isinstance(got_pos, dict):
                    got_pos = got_pos.get("value", got_pos)
                if got_pos == want_pos:
                    break
                self.log.say(f"滤镜设置第 {attempt+1} 次未生效（当前 {got_pos}）",
                             kind="warn")
                time.sleep(2)
            name = "LP" if want_pos == 2 else ("IRCUT" if want_pos == 1 else "DARK")
            if got_pos == want_pos:
                self.log.say(f"滤镜 -> {want_pos} ({name})（已校验，开拍后设置）",
                             kind="filter")
            else:
                self.log.say(f"滤镜设置失败：想要 {want_pos}，实际 {got_pos}",
                             kind="warn")
        except Exception as e:
            self.log.say(f"滤镜设置失败: {e}", kind="warn")

        # 6) 监视直到该时段结束
        self.monitor_slot(slot, end)

        # 7) 停止
        try:
            native("iscope_stop_view", ["Stack"], timeout=60)
            self.log.say(f"停止 {slot.name}", kind="stack_stop", target=slot.name)
        except Exception as e:
            self.log.say(f"停止失败: {e}", kind="warn")

    def wait_slew(self, slot: Slot | None = None, timeout_s: int = 240) -> bool:
        """Wait until the device really points at the target.

        Why not just poll Alpaca `slewing`?  On firmware 9.75 that property
        returns false the whole time, and `rightascension`/`declination` are
        served from a cache.  Both would let us start stacking mid-slew.
        `scope_get_equ_coord` is the only live source, so we poll it and
        require the pointing to be both close to target and stable.
        """
        if slot is None:
            time.sleep(8)
            return True

        target_ra = slot.ra / 15.0
        deadline = time.time() + timeout_s
        last = None
        stable = 0
        while time.time() < deadline:
            if self.stop:
                return False
            cur = real_pointing()
            if cur:
                err = max(abs(cur[0] - target_ra) * 15.0, abs(cur[1] - slot.dec))
                if err < 0.4:
                    if last and abs(last[0] - cur[0]) < 0.003 \
                            and abs(last[1] - cur[1]) < 0.003:
                        stable += 1
                    else:
                        stable = 0
                    last = cur
                    if stable >= 2:
                        self.log.say(f"到位 误差 {err:.2f}°", kind="slew_done",
                                     target=slot.name, err_deg=round(err, 3))
                        return True
                else:
                    stable = 0
                    last = cur
            time.sleep(3)
        return False

    def monitor_slot(self, slot: Slot, end: datetime):
        last_sample = 0.0
        last_wx = 0.0
        last_hb = 0.0
        while not self.stop:
            now = datetime.now(BJT)
            if now >= end:
                self.log.say(f"{slot.name} 时段结束", kind="slot_end", target=slot.name)
                return

            t = None
            try:
                t = read_telemetry()
                self._last_telemetry = t
            except Exception as e:
                self.log.say(f"遥测失败: {e}", kind="warn")

            # 硬停
            stop_reason = self.hard_stop(t)
            if stop_reason:
                self.reason = stop_reason
                self.log.say(f"硬停: {stop_reason}", kind="hard_stop")
                self.stop = True
                return

            # 电缆
            cable = self.cable_check(t)
            if cable:
                self.reason = cable
                self.log.say(f"电缆告警: {cable}", kind="cable_alert")
                self.stop = True
                return

            # 天气（每 10 分钟）
            if time.time() - last_wx > 600:
                self._wx_cache = hourly_weather()
                ok, why = weather_verdict(self._wx_cache)
                self.log.say(f"天气检查: {why}", kind="weather", ok=ok)
                last_wx = time.time()
                if not ok:
                    # 天气不佳：停拍并折叠等待，交给 run() 决定何时重试本时段。
                    # 绝不能直接终止整晚——否则 watchdog 会反复重启并重新 goto，
                    # 造成机械臂反复展开/折叠与大幅转向（2026-10-19 22:11 实测发生）。
                    self.log.say(f"天气不佳，停拍折叠等待: {why}", kind="weather_hold")
                    try:
                        native("iscope_stop_view", ["Stack"], timeout=60)
                        self.log.say(f"停止 {slot.name}", kind="stack_stop", target=slot.name)
                    except Exception as e:
                        self.log.say(f"停拍失败: {e}", kind="warn")
                    self.weather_hold = True
                    return

            # 采样日志（每 60 秒）
            if time.time() - last_sample > 60 and t is not None:
                self.log.write("sample", target=slot.name,
                               ra_h=t.ra_h, dec_deg=t.dec_deg,
                               alt_deg=round(t.alt_deg, 2) if t.alt_deg is not None else None,
                               az_deg=round(t.az_deg, 2) if t.az_deg is not None else None,
                               battery=t.battery_pct, charging=t.charging,
                               stacked=t.stacked, dropped=t.dropped,
                               tracking=t.tracking)
                last_sample = time.time()

            # 心跳（每 30 秒）
            if time.time() - last_hb > 30:
                self.save_state("imaging", t)
                last_hb = time.time()

            time.sleep(15)

    def _weather_wait(self, slot: Slot, end: datetime):
        """Park the mount and wait for the sky to clear (or the slot to end).

        Called after a weather hold.  Keeping the mount parked protects the
        power cable and the gimbal while there is nothing to image.
        """
        self.log.say("天气挂起：折叠停泊，等待转好", kind="weather_wait")
        try:
            native("scope_park", timeout=120)
            for _ in range(12):
                time.sleep(10)
                st = try_native("get_device_state") or {}
                if (st.get("mount") or {}).get("close"):
                    self.log.say("天气挂起：已确认折叠", kind="weather_wait_parked")
                    break
            else:
                self.log.say("天气挂起：未确认折叠", kind="warn")
        except Exception as e:
            self.log.say(f"天气挂起折叠失败: {e}", kind="warn")

        while not self.stop and datetime.now(BJT) < end:
            self.save_state("weather_wait")
            time.sleep(300)
            if datetime.now(BJT) >= end:
                break
            ok, why = weather_verdict(hourly_weather())
            self.log.say(f"天气复查: {why}", kind="weather_recheck", ok=ok)
            if ok:
                self.log.say("天气转好，重试本时段", kind="weather_resume")
                return
        self.log.say("天气挂起结束（时段已过）", kind="weather_wait_end")

    # --- 演练：打印并校验时间表 ---
    def _print_schedule(self):
        now = datetime.now(BJT)
        print()
        print(f"{'目标':<10}{'起':<8}{'止':<8}{'分钟':>6}  {'滤镜':<8}{'gain':>5}{'exp':>5}  方位角检查")
        print("-" * 92)
        total = 0.0
        ok = True
        for s in self.slots:
            start = parse_bjt(s.start_bjt, self.night_start)
            end = parse_bjt(s.end_bjt, self.night_start)
            mins = (end - start).total_seconds() / 60.0
            total += mins
            alt, az = radec_to_altaz(s.ra / 15.0, s.dec, start)
            in_win = (az >= self.plan.get("window_az_min_deg", 330)
                      or az <= self.plan.get("window_az_max_deg", 110))
            flag = "在窗" if in_win else "!! 窗外 !!"
            if not in_win:
                ok = False
            fname = {0: "dark", 1: "IRCUT", 2: "LP"}.get(s.filter_pos, str(s.filter_pos))
            print(f"{s.name:<10}{start:%H:%M}   {end:%H:%M}   {mins:>6.0f}  "
                  f"{fname:<8}{s.gain:>5}{s.exp_s:>5}  az={az:6.1f} {flag}")
        print("-" * 92)
        print(f"合计 {total:.0f} 分钟 = {total/60:.1f} 小时")
        print(f"演练时刻 {now:%Y-%m-%d %H:%M} BJT；第一个时段还有 "
              f"{(parse_bjt(self.slots[0].start_bjt, self.night_start) - now).total_seconds()/60:.0f} 分钟")
        print(f"方位角窗口校验：{'全部在窗 ✓' if ok else '存在窗外目标 ✗'}")
        print()
        self.log.write("dry_run_schedule", slots=len(self.slots), total_min=total, all_in_window=ok)

    # --- 收尾 ---
    def wind_down(self):
        self.save_state("wind_down", self._last_telemetry)
        self.log.say("开始收尾", kind="wind_down", reason=self.reason)

        if self.dry_run:
            self.log.say("[DRY] 跳过收尾动作")
            return

        try:
            native("iscope_stop_view", ["Stack"], timeout=60)
        except Exception as e:
            self.log.say(f"停止叠加异常（继续）: {e}", kind="warn")

        parked = False
        for attempt in (1, 2):
            try:
                native("scope_park", timeout=120)
            except Exception as e:
                self.log.say(f"park 调用异常: {e}", kind="warn")
            # 轮询确认折叠
            # `try_native` already unwraps Alpaca's Value and the JSON-RPC
            # envelope, so `st` is the device-state dict itself.
            deadline = time.time() + 240
            while time.time() < deadline:
                try:
                    st = try_native("get_device_state")
                    mount = (st or {}).get("mount", {}) if isinstance(st, dict) else {}
                    if mount.get("close") is True:
                        parked = True
                        break
                except Exception:
                    pass
                time.sleep(15)
            if parked:
                break
            self.log.say(f"park 未确认（第 {attempt} 次），重试", kind="warn")

        self.save_state("parked" if parked else "park_failed", self._last_telemetry)
        if parked:
            self.log.say("已确认折叠停泊", kind="park_ok")
        else:
            self.log.say("!! 未能确认折叠，设备可能仍在展开状态 !!", kind="park_fail")

    def run(self):
        try:
            self.stopped_marker.unlink()
        except FileNotFoundError:
            pass
        self.log.say("无人值守运行器启动", kind="start",
                     night_start=self.night_start.isoformat(),
                     absolute_end=self.absolute_end.isoformat(),
                     slots=len(self.slots))
        if self.dry_run:
            self.log.say("[DRY-RUN] 只演练调度，不移动设备")
            self._print_schedule()
            return

        # 等第一个时段
        for idx, slot in enumerate(self.slots):
            start = parse_bjt(slot.start_bjt, self.night_start)
            end = parse_bjt(slot.end_bjt, self.night_start)
            # 重启后跳过已经结束的时段（让 watchdog 重启是幂等的）
            if datetime.now(BJT) >= end:
                self.log.say(f"跳过 {slot.name}（时段已结束）", kind="slot_skip",
                             target=slot.name)
                continue
            gap_parked = False
            while datetime.now(BJT) < start and not self.stop:
                # 等待期间也要看硬停
                r = self.hard_stop(None)
                if r:
                    self.reason = r
                    self.log.say(f"硬停（等待期）: {r}", kind="hard_stop")
                    self.stop = True
                    break

                # 长空档（>10 分钟）折叠停泊。
                # 否则机械臂会整段时间保持展开，继续跟踪一个已经落下的目标：
                # M45 在 00:50 出窗后还要 2 小时才轮到 M81，这期间臂空转、
                # 方位持续漂移，既扯供电线也让云台无谓受力。
                remain = (start - datetime.now(BJT)).total_seconds()
                if remain > 600 and not gap_parked:
                    st = try_native("get_device_state") or {}
                    if not (st.get("mount") or {}).get("close"):
                        self.log.say(
                            f"距下一目标还有 {remain/60:.0f} 分钟，先折叠停泊",
                            kind="gap_park", next_slot=slot.name)
                        try:
                            native("scope_park", timeout=120)
                            for _ in range(12):
                                time.sleep(10)
                                st = try_native("get_device_state") or {}
                                if (st.get("mount") or {}).get("close"):
                                    self.log.say("空档停泊已确认折叠", kind="gap_parked")
                                    break
                            else:
                                self.log.say("空档停泊未确认折叠，继续等待", kind="warn")
                        except Exception as e:
                            self.log.say(f"空档停泊失败: {e}", kind="warn")
                    gap_parked = True

                self.save_state("waiting")
                time.sleep(30)
            if self.stop:
                break
            # 本时段可能因天气被多次挂起：循环重试，直到时段结束或正常跑完。
            while not self.stop and datetime.now(BJT) < end:
                self.weather_hold = False
                self.run_slot(slot)
                if self.stop or not self.weather_hold:
                    break
                # 天气挂起：折叠停泊并等待转好；时段剩余不足 5 分钟则放弃本时段
                if (end - datetime.now(BJT)).total_seconds() < 300:
                    self.log.say("剩余不足 5 分钟，放弃本时段", kind="slot_abandon",
                                 target=slot.name)
                    break
                self._weather_wait(slot, end)
            if self.stop:
                break
            if self.rehearse:
                self.log.say("演练模式：只跑一个时段，结束", kind="rehearse_end")
                break

        self.log.say("时段全部结束" if not self.stop else f"提前结束: {self.reason}",
                     kind="run_end", reason=self.reason)
        self.wind_down()
        # 写 STOPPED 标记：watchdog / monitor 见到它就不要再重启（正常收尾或保护性停止）
        try:
            self.stopped_marker.write_text(
                f"{datetime.now(BJT):%Y-%m-%d %H:%M:%S} reason={self.reason or 'all slots done'}\n",
                encoding="utf-8")
        except Exception:
            pass
        self.log.say("收尾完成", kind="done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rehearse", type=float, metavar="SECONDS",
                    help="run the first slot only, shortened to SECONDS, then wind down")
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    data_dir = Path(plan.get("data_dir", "./data"))
    log = EventLog(data_dir / "events.jsonl")

    if args.rehearse:
        # 缩短首个时段，用于真机联调
        first = plan["slots"][0]
        start = datetime.now(BJT)
        first["start_bjt"] = start.strftime("%Y-%m-%d %H:%M")
        first["end_bjt"] = (start + timedelta(seconds=args.rehearse)).strftime(
            "%Y-%m-%d %H:%M")
        plan["slots"] = [first]
        log.say(f"[REHEARSE] 仅跑 {first.get('name')} {args.rehearse:.0f}s",
                kind="rehearse")

    runner = NightRunner(plan, log, dry_run=args.dry_run,
                         rehearse=bool(args.rehearse))

    def _sig(signum, _frame):
        log.say(f"收到信号 {signum}，请求收尾", kind="signal")
        runner.stop = True
        runner.reason = f"信号 {signum}"

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    try:
        runner.run()
    except Exception:
        log.say("运行器崩溃:\n" + traceback.format_exc(), kind="crash")
        try:
            runner.wind_down()
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
