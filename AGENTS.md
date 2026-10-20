# AGENTS.md — Seestar 无人值守深空拍摄项目

> **给任何接手本项目的 AI Agent 的交接文档。**
> 读这一份即可掌握全部上下文，无需翻阅历史对话。
> 最后更新：2026-10-20

---

## 0. 一分钟速览

这个仓库用一套**进程链**托管一台 **ZWO Seestar S30 Pro** 智能望远镜，在深圳龙华市区一扇东北向窗外，整夜无人值守自动拍摄多个深空目标，然后把设备里的 **16-bit FITS 叠加原片**下载回本地、跑自研后期流水线出图。

**已完成的成果**：2026-10-19 夜，8 个目标全部拍完（391 分钟有效曝光），8 张后期成品 + 联系表 + 对比图 + 朋友圈文案 + 社群分享帖，代码已推送私有仓库。

**当前状态**：设备已收工收回，无运行中的任务。下一步由用户驱动。

---

## 1. 环境（必须先搞清，否则一定踩坑）

| 项目 | 值 |
|---|---|
| 工作目录 | `C:\Users\BGSJIA\seestar-agent` |
| 设备 | ZWO Seestar S30 Pro（30mm / f5 / 150mm，输出 2160×3840 竖幅，**无制冷**，CCD 常年 38–41°C） |
| 固件 | 9.75（≥7.18 需 RSA 互操作密钥） |
| 站点 | `lat=22.7261, lon=114.046`（深圳龙华；site_profile 必须与此一致，否则地平遮罩失效） |
| 设备 IP | `192.168.2.118`，电源线**从上方垂下留足余量** |
| 拍摄窗口 | 方位角 **az 330°→110°**（跨正北，宽 140°），最低高度 **20°** |
| 远程 | RDP 3389；ZeroTier `192.168.196.232` |

### 两套 Python 环境（**绝对不能混用**）

```powershell
# 图像/后期：有 numpy + PIL，无 astropy
.\seestar_alp\.venv\Scripts\python.exe

# 计划/扫描：有 numpy/scipy/astropy，无 pip、无 PIL
.\seestar-mcp\.venv\Scripts\python.exe

# PowerShell 通用前缀
cd C:\Users\BGSJIA\seestar-agent; $env:PYTHONIOENCODING='utf-8'; chcp 65001 | Out-Null
```

---

## 2. 系统架构

```
AI Agent
   ↓ seestar-mcp（34 个 MCP 工具）
Alpaca 127.0.0.1:5555   ← device_num = 1（不是 0！）
   ↓ seestar_alp 后端（WebUI :5432，imaging :7556）
设备 JSON-RPC :4700
```

### 无人值守进程链（与 AI 会话完全解耦）

```
svchost → powershell night_watchdog.ps1 → python night_runner.py
```

**关掉 AI 会话不影响拍摄。** 三层守护：

| 层 | 文件 | 职责 |
|---|---|---|
| 1 | `scripts/night_runner.py` | 主运行器：排程、goto、对焦、开拍、硬停判据 |
| 2 | `scripts/night_watchdog.ps1` | 进程守护：崩了无限重启（幂等，`_already_running()` 续拍不丢帧） |
| 3 | `scripts/night_monitor.py` | 每分钟独立巡检（Windows 计划任务 `SeestarMonitor`），82°C 兜底强制折叠 |

### 关键状态文件（`data/`）

`monitor_status.json`（当前状态快照）、`events.jsonl`（结构化事件流）、`runner_state.json`（心跳）、`ALERT.txt`（告警）、`STOPPED`（**正常收尾标记**，见 §4-A）

---

## 3. 设备协议陷阱清单（14 条，全是血泪）

1. **Alpaca 属性不可信**：`rightascension/declination` 是缓存值；`slewing` 恒 false；`altitude/azimuth` 恒 0；`atpark` 与 `mount.close` 矛盾。**必须用原生** `scope_get_equ_coord` 与 `get_device_state` 的 `mount.close`
2. `native()` 返回 `{"Value": {"jsonrpc":…, "result": {…}}}`，取值必须走 `env["Value"]["result"]`
3. Alpaca `action` 端点**只接受 JSON body**，urlencoded 会被静默丢弃
4. `gain` 用 `set_control_value ["gain", N]` 单独设；曝光用 `set_setting {exp_ms:{stack_l: ms}}`；`iscope_start_stack` 只接受 `{restart: bool}`
5. 设备只允许**单一 TCP 连接**，后端在线时直接探测 4700 必然超时（正常现象）
6. 取图：SMB 不可用（guest 拒绝），**HTTP 可用** → `http://192.168.2.118/MyWorks/...`
7. `get_img_file_list` 在 9.75 上不存在（code 103），须用 `get_albums`
8. `get_albums` 返回 `{"path":"MyWorks","list":[{"group_name":"DeepSky","files":[{"name":…,"thn":…,"count":N}]}]}`；**`thn` 字段含真实滤镜名**，是验证滤镜生效最快途径
9. 成品 FITS 扩展名只有三个字母 **`.fit`**（`.fits` 会 404）；成品 47.5 MB/个，子帧 16.6 MB/张
10. `.ps1` 必须 **UTF-8 BOM（239,187,191）**，否则中文乱码；`seestar_alp\device\config.toml` 必须**纯 ASCII**（`config.py` 用 GBK 读）
11. **PowerShell 自杀陷阱**：`Get-CimInstance | Where { $_.CommandLine -like '*night_*' } | Stop-Process` 会匹配到执行该命令的 powershell 自身，**必须加 `-and $_.ProcessId -ne $PID`**
12. `Stop-ScheduledTask` **不杀子进程**，必须显式 `Stop-Process` 整条进程链
13. 用 `Get-Content -Encoding UTF8` 读含中文日志时筛选常失败（控制台 GBK 显示层问题），**改用 `scripts/quick_status.py`**
14. 内联 Python 单行易被 PowerShell 引号破坏，**改为写 .py 文件再执行**

---

## 4. 三个已修复的重大 bug（核心经验）

共同特征：**设备返回成功，但实际没生效。**

### A. 天气停止 → 监工无限重启 → 机械臂反复起落
- **根因**：天气停止使 runner 正常退出（码 0），watchdog 正确结束；但 `night_monitor.py` 见「心跳中断 + 任务未运行」就 `schtasks /End + /Run` 重启 → 循环（一晚无谓起落 3 次，每次转 120°）
- **修复**：
  - runner 收尾写 `data/STOPPED`；watchdog 与 monitor 见到即**不重启**
  - 天气不佳改为 `weather_hold`（停叠 + 折叠 + 每 5 分钟复查 + 转好续拍），而非终止整晚
  - `run_slot()` 新增 **goto 前天气预检**，避免「先转 120° 再停拍」

### B. 曝光 `set_setting` 静默失败（code 259）
- **现象**：日志写「曝光 → 20s」，FITS 头却 `EXPTIME=10.0`
- **根因**：叠加运行中改曝光会返回 `{"error":"stack is already running","code":259}`，**错误藏在 `Value.error` 里，外层 `result` 与 `ErrorNumber` 都是 0**
- **修复**：停叠 → 轮询等 `state` 离开 working → `set_setting` → **读回 `get_device_state.setting.exp_ms.stack_l` 校验**（最多 4 次重试）

### C. 滤镜被 `iscope_start_stack` 重置（最隐蔽）
- **现象**：整晚 8 个目标文件名全是 `IRCUT`，包括本该用 LP 的发射星云
- **实验结论**：`iscope_start_stack`（restart True/False 都一样）**一定把轮位重置为 1**
- **唯一有效顺序**：**先开拍 → 等 `state=working` → 再设滤镜**
- **修复**：原「1) 滤镜」块废弃；「5) 开拍」之后新增「5b) 滤镜」：`set_wheel_position(want)` → sleep 2 → `get_wheel_position` 读回校验

---

## 5. 天气判据（低云优先）

```python
precip >= 60  -> 停
low    >= 70  -> 停（低云遮挡星空）
total  >= 98  -> 停（几乎全遮）
否则           -> 可拍
```

**为什么不用总云量**：华南秋冬常见高云卷云，总云量能到 90%+ 但低云 0%，只降对比度不遮星。用总云量会白白放弃整晚。抓取失败时 **fail-open**（按设备遥测继续）。

---

## 6. 后期处理流水线

**为什么必须用 FITS**：设备机内 JPG 只用了 13–31/255 的动态范围，90% 信息被压掉；`.fit` 是 16-bit（65536 级）无损。

`scripts/process_fits.py` 流程：
背景多项式相减（**不 clip 负值**）→ 颜色平衡（`cb`）→ 亮度降噪 → 鲁棒黑白点 → Reinhard + MTF 拉伸（解析解 `mtf_m_for`）→ 饱和度 → 色度降噪 → unsharp → sRGB → PNG + JPG(q95)

### 参数口径（直接复用）

| 类型 | 参数 |
|---|---|
| 宽带（M31/M45/M81/NGC2403） | `--stretch 0.035 --cb 0.5 --bg-deg 3 --bg-grid 12 --saturation 1.25` |
| 暗弱星系（M81/NGC2403） | 同上但 `--stretch 0.06` |
| 发射星云（IC405/IC443/NGC1499/IC1805） | `--stretch 0.10 --cb 0.0 --bg-deg 1 --bg-grid 32 --saturation 1.6` |
| 公共 | `--predenoise 0.6 --denoise 0.65 --unsharp 0.55 --gamma 2.2` |

### 三条铁律
1. **不能 clip 负值** —— 背景减除后立即 clip 会让 median 塌成 0，MTF 求解退化
2. **发射星云必须 `bg-deg 1, bg-grid 32`** —— 3 阶 12×12 会把跨度 1000px 的大星云当梯度减掉
3. **发射星云必须 `cb 0`** —— 否则白平衡把 R 通道乘 0.845，压掉 Hα

---

## 7. 常用命令

```powershell
# 巡检（最可靠）
.\seestar_alp\.venv\Scripts\python.exe scripts\quick_status.py

# 单目标后期
.\seestar_alp\.venv\Scripts\python.exe scripts\process_fits.py data\stacked_fits\M81_305.fit --target M81 --stretch 0.06 --label broadband

# 批量后期 8 个 + 联系表 + 对比图
.\seestar_alp\.venv\Scripts\python.exe scripts\process_all.py
.\seestar_alp\.venv\Scripts\python.exe scripts\contact_sheet.py
.\seestar_alp\.venv\Scripts\python.exe scripts\make_compare.py

# 从设备拉成品 FITS / 机内 JPG
.\seestar_alp\.venv\Scripts\python.exe scripts\download_night.py --since 20261019
.\seestar_alp\.venv\Scripts\python.exe scripts\fetch_results.py --since 20261019

# 按窗口扫可拍目标（必须用 seestar-mcp venv）
.\seestar-mcp\.venv\Scripts\python.exe scripts\replan_gap.py
```

### 停止 / 重启夜间运行

```powershell
Stop-ScheduledTask -TaskName SeestarNightRun
# Stop-ScheduledTask 不杀子进程，必须显式清理
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='powershell.exe'" |
  Where-Object { ($_.CommandLine -like '*night_runner*' -or $_.CommandLine -like '*night_watchdog*') -and $_.ProcessId -ne $PID } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 重启前删除正常收尾标记，否则 watchdog 不会启动
Remove-Item data\STOPPED -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName SeestarNightRun
```

> 计划任务是 **`SeestarNightRun`**（拍摄）和 **`SeestarMonitor`**（每分钟巡检）。

---

## 8. 目录结构

```
seestar-agent/
├── AGENTS.md              ← 本文件（agent 交接）
├── README.md              主文档
├── scripts/   17 个       核心脚本（见 §7）
├── vendor/    654 个      上游源码快照 seestar_alp + seestar-mcp
├── config/                 config.toml（纯 ASCII）
├── docs/       4 份中文文档
├── dev/       38 个       一次性调试脚本（留档）
├── results/
│   ├── DeepSky/           8 张机内 JPG
│   ├── processed/         8 张后期成品 + contact_sheet.jpg
│   └── compare/           8 张机内 vs 后期对比
├── data/
│   └── stacked_fits/      8 个成品 FITS（各 49.8 MB）
└── *.bat       4 个       一键启动（相对路径）
```

---

## 9. 2026-10-19 夜拍摄结果

| 目标 | 帧数 | 参数 | 累积 | 评价 |
|---|---|---|---|---|
| M31 仙女座大星系 | 367 | 10s / 80 / IRCUT | 61 min | ✅ 最优 |
| IC1805 心脏星云 | 281 | 10s / 200 / IRCUT | 47 min | ❌ 滤镜错，需重拍 |
| NGC1499 加州星云 | 145 | 20s / 80 / IRCUT | 48 min | ⚠️ 应用 LP，需重拍 |
| M45 昴星团 | 285 | 10s / 200 / IRCUT | 48 min | ✅ 良好 |
| IC405 火焰星云 | 196 | 20s / 200 / LP | 65 min | ✅ |
| IC443 水母星云 | 178 | 20s / 80 / LP | 59 min | ✅ 参数最标准 |
| M81 波德星系 | 305 | 10s / 80 / IRCUT | 51 min | ✅ |
| NGC2403 | 74 | 10s / 80 / IRCUT | 12 min | ⚠️ 帧数少 |

合计 **391 分钟**有效曝光。**以 FITS 头的 `GAIN`/`FILTER` 为准**（日志可能记录不实）。

---

## 10. 待办 / 下次改进

1. **重拍 IC1805 与 NGC1499**：LP + 20s + gain **80**，各 75 分钟（这两个是滤镜 bug 的受害者）
2. **物理调平三脚架**（实测倾斜 4.1°）+ **校准罗盘**（`cali:0, stable:0`，方向值乱跳）
3. 参数校验前置：开拍后读回「曝光 / 增益 / 滤镜」三项与计划比对
4. 把计划值写入 FITS 头作为断言
5. NGC2403 单独给一晚或至少 60 分钟
6. `scripts/install.py` 尚未运行验证（会重建 venv，谨慎）

---

## 11. 给接手 Agent 的工作守则

1. **先跑 `quick_status.py`**，不要凭猜测判断设备状态
2. **任何「设备返回成功」都要读回校验** —— 本项目三个大 bug 全是静默失败
3. **改 `night_plan.json` 对已在运行的 runner 无效**（启动时读入内存），必须重启进程链
4. **Python 脚本要写文件再执行**，不要塞进 PowerShell 单行
5. **`.ps1` 编辑后检查 BOM**（239,187,191）；`.py` 编辑后跑 `py_compile`
6. **不要碰 `_Seestar_3.4.0.xapk`**（1.5 GB，已 gitignore）
7. 用户偏好：**保守策略**（异常即停拍折叠）、**中文回复**、**简洁直接**

---

## 12. 相关链接

- 仓库：https://github.com/ilray88/seestar-night-agent （PRIVATE）
- 详细文档：`docs/部署与使用.md`、`docs/今晚操作卡.md`、`docs/观测计划-东北窗.md`、`docs/社群分享帖.md`
- 成品文案：`results/朋友圈文案.md`、`results/社群分享帖.md`、`results/社群分享帖-纯文本版.txt`
