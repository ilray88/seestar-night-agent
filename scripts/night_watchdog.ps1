# Watchdog: keep the night runner alive, and make sure the scope ends up parked.
#
# Why this exists: the runner is a single Python process. If it dies from an
# unhandled exception at 21:30, nothing would stop the mount or park it and the
# scope would sit outside all night tracking a target with the arm extended.
#
# Strategy:
#   * launch the runner, wait for it
#   * if it exits non-zero BEFORE the absolute end time, restart it (max 3 tries)
#     - the runner is idempotent: slots whose end time already passed are skipped
#   * when we finally give up or the night is over, verify mount.close; if the
#     arm is still out, issue a park command ourselves
#
# Usage:
#   powershell -File scripts\night_watchdog.ps1
#   powershell -File scripts\night_watchdog.ps1 -DryRun

param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root 'seestar-mcp\.venv\Scripts\python.exe'
$runner = Join-Path $root 'scripts\night_runner.py'
$plan = Join-Path $root 'scripts\night_plan.json'
$logDir = Join-Path $root 'data'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$watchLog = Join-Path $logDir 'watchdog.log'

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -Path $watchLog -Value $line -Encoding UTF8
}

function Get-AbsoluteEnd {
    $p = Get-Content $plan -Raw -Encoding UTF8 | ConvertFrom-Json
    return [datetime]::ParseExact($p.absolute_end_bjt, 'yyyy-MM-dd HH:mm', $null)
}

function Test-Parked {
    # mount.close true means the arm is folded.
    $code = @'
import sys, json
sys.path.insert(0, 'scripts')
import night_runner as NR
st = NR.try_native('get_device_state') or {}
print('PARKED' if (st.get('mount') or {}).get('close') else 'OPEN')
'@
    try {
        $out = & $py -c $code 2>&1 | Out-String
        return $out.Trim()
    } catch {
        return "UNKNOWN ($($_.Exception.Message))"
    }
}

function Invoke-Park {
    $code = @'
import sys
sys.path.insert(0, 'scripts')
import night_runner as NR
NR.native('scope_park', timeout=120)
print('park sent')
'@
    & $py -c $code 2>&1 | Out-String | ForEach-Object { $_.Trim() }
}

$end = Get-AbsoluteEnd
$stopped = Join-Path $logDir 'STOPPED'
Write-Log "watchdog 启动；绝对结束时间 $($end.ToString('yyyy-MM-dd HH:mm'))"

if ($DryRun) {
    Write-Log "[DRY-RUN] 当前折叠状态: $(Test-Parked)"
    Write-Log "[DRY-RUN] 不做任何动作"
    exit 0
}

# 崩溃后无限重启，直到绝对结束时间。
# 原来的 maxAttempts=3 是个陷阱：整夜 10 小时里只要撞上 3 次偶发崩溃，
# watchdog 就会放弃，后面几个小时的拍摄全部作废。运行器本身是幂等的
# （已结束的时段跳过、已在叠加的目标直接续拍），所以重启是安全的。
$attempt = 0
$backoff = 60

while ($true) {
    if (Test-Path $stopped) {
        Write-Log "检测到 STOPPED 标记（运行器已正常收尾或保护性停止），不再重启"
        break
    }
    $attempt++
    Write-Log "启动运行器（第 $attempt 次）"
    & $py $runner --plan $plan
    $exit = $LASTEXITCODE
    Write-Log "运行器退出，代码 $exit"

    if ($exit -eq 0) {
        Write-Log "正常结束"
        break
    }

    if ((Get-Date) -ge $end) {
        Write-Log "已过绝对结束时间，不再重启"
        break
    }

    Write-Log "异常退出，$backoff 秒后重启（已过时段会被自动跳过）"
    Start-Sleep -Seconds $backoff
    # 连续崩溃时逐步拉长间隔，最多 5 分钟，避免设备离线时疯狂重试
    if ($backoff -lt 300) { $backoff = [Math]::Min($backoff * 2, 300) }
}

# --- 无论如何，确保收尾 ---
$parked = Test-Parked
Write-Log "收尾检查：$parked"

if ($parked -notmatch 'PARKED') {
    Write-Log "机械臂未折叠，主动执行 park"
    Invoke-Park | ForEach-Object { Write-Log $_ }
    Start-Sleep -Seconds 30
    Write-Log "复查：$(Test-Parked)"
} else {
    Write-Log "已确认折叠，无需干预"
}
