# CLAUDE.md

本项目的完整背景、环境约束、协议陷阱与工作守则全部写在 **`AGENTS.md`**，请先完整阅读该文件。

## 必读摘要

- 工作目录 `C:\Users\BGSJIA\seestar-agent`，Windows + PowerShell
- 两套 Python venv **不可混用**：`seestar_alp\.venv`（图像/后期，有 PIL 无 astropy）、`seestar-mcp\.venv`（计划/扫描，有 astropy 无 PIL）
- 设备 ZWO Seestar S30 Pro，Alpaca 在 `127.0.0.1:5555`，**device_num = 1**
- **任何「设备返回成功」都要读回校验** —— 本项目三个重大 bug 全是静默失败
- 改 `scripts/night_plan.json` 对已运行的 runner **无效**，必须重启进程链
- `.ps1` 必须带 UTF-8 BOM；Python 脚本写文件再执行，别塞 PowerShell 单行
- 用户偏好：保守策略、中文回复、简洁直接

完整细节见 `AGENTS.md`。
