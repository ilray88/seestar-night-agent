# 无人值守运行器启动脚本。
# 参数：
#   -DryRun          只打印时间表，不动设备
#   -Rehearse 300    只跑第一个时段 300 秒，然后收尾
# 不带参数 = 今晚完整计划。
param(
    [switch]$DryRun,
    [int]$Rehearse = 0
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root 'seestar-mcp\.venv\Scripts\python.exe'
$runner = Join-Path $root 'scripts\night_runner.py'
$plan = Join-Path $root 'scripts\night_plan.json'

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ' Seestar S30 Pro 无人值守观测' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

# 前置检查：后端必须在线
$backend = $false
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5555/management/v1/configureddevices' -TimeoutSec 5 -UseBasicParsing
    $backend = ($r.StatusCode -eq 200)
} catch { $backend = $false }

if (-not $backend) {
    Write-Host '[错误] 后端未运行。请先双击 1-启动Seestar后端.bat，' -ForegroundColor Red
    Write-Host '       等出现 Authentication successful 后再运行本脚本。' -ForegroundColor Red
    exit 1
}
Write-Host '[OK] 后端在线 (127.0.0.1:5555)' -ForegroundColor Green

# 前置检查：望远镜连接
try {
    $c = Invoke-WebRequest -Uri 'http://127.0.0.1:5555/api/v1/telescope/1/connected?ClientID=1&ClientTransactionID=1' -TimeoutSec 8 -UseBasicParsing
    $j = $c.Content | ConvertFrom-Json
    if ($j.Value -eq $true) {
        Write-Host '[OK] 望远镜已连接' -ForegroundColor Green
    } else {
        Write-Host '[警告] 望远镜未连接，运行器会持续重试' -ForegroundColor Yellow
    }
} catch {
    Write-Host '[警告] 无法读取连接状态' -ForegroundColor Yellow
}

# 电源计划：跑一夜不能被休眠打断
powercfg /change standby-timeout-ac 0 2>$null
powercfg /change hibernate-timeout-ac 0 2>$null
powercfg /change monitor-timeout-ac 0 2>$null
Write-Host '[OK] 已禁止交流电下自动休眠' -ForegroundColor Green

Write-Host ''
$env:PYTHONIOENCODING = 'utf-8'
chcp 65001 | Out-Null

$args2 = @($runner, '--plan', $plan)
if ($DryRun) { $args2 += '--dry-run' }
if ($Rehearse -gt 0) { $args2 += @('--rehearse', $Rehearse) }

Write-Host "执行: $py $($args2 -join ' ')" -ForegroundColor DarkGray
Write-Host ''
& $py @args2
