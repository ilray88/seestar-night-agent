# Seestar Agent 部署体检（只读，不改动任何东西）
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Item([string]$label, [bool]$ok, [string]$hint) {
    if ($ok) { Write-Host ("  [OK]   " + $label) -ForegroundColor Green }
    else {
        Write-Host ("  [缺失] " + $label) -ForegroundColor Yellow
        if ($hint) { Write-Host ("         " + $hint) -ForegroundColor DarkGray }
    }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Seestar Agent 部署体检" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/6] Python 运行环境"
Item "seestar_alp .venv（设备控制后端）" (Test-Path "$root\seestar_alp\.venv\Scripts\python.exe") "请在 seestar_alp 目录运行 uv sync"
Item "seestar-mcp .venv（Agent 层）"    (Test-Path "$root\seestar-mcp\.venv\Scripts\python.exe") "请在 seestar-mcp 目录运行 uv sync"
Write-Host ""

Write-Host "[2/6] RSA 互操作密钥（固件 7.18+ 必需）"
$pem = "$root\seestar_alp\seestar_client_key.pem"
Item "seestar_client_key.pem" (Test-Path $pem) "缺此文件会表现为「连上了但所有命令无响应」"
if (Test-Path $pem) {
    $txt = Get-Content -Raw $pem
    if ($txt -match 'BEGIN (RSA )?PRIVATE KEY') { Write-Host "         内容格式检查：通过" -ForegroundColor DarkGray }
    else { Write-Host "         内容格式检查：失败（不是有效 PEM 私钥）" -ForegroundColor Red }
}
Write-Host ""

Write-Host "[3/6] opencode MCP 注册"
$cfg = "C:\Users\BGSJIA\.config\opencode\opencode.jsonc"
$raw = Get-Content -Raw $cfg
Item "opencode.jsonc 中存在 seestar-mcp 条目" ($raw -match 'seestar_mcp\.server') "请把 seestar 加到 mcp.servers"
Write-Host ""

Write-Host "[4/6] 后端端口状态（5555 / 5432 / 7556）"
foreach ($p in 5555, 5432, 7556) {
    $busy = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    if ($busy) { Write-Host ("  [监听中] " + $p) -ForegroundColor Green }
    else { Write-Host ("  [未启动] " + $p) -ForegroundColor DarkGray }
}
Write-Host ""

Write-Host "[5/6] 望远镜连接状态"
# 从 config.toml 动态读取当前配置的望远镜 IP，避免脚本里硬编码
$scopeIp = '192.168.2.118'
$cfgPath = Join-Path $PSScriptRoot '..\seestar_alp\device\config.toml'
if (Test-Path $cfgPath) {
    $m = Select-String -Path $cfgPath -Pattern '^\s*ip_address\s*=\s*["'']([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)["'']' |
         Where-Object { $_.Line -notmatch '127\.0\.0\.1' } | Select-Object -First 1
    if ($m) { $scopeIp = $m.Matches[0].Groups[1].Value }
}
$anyOnline = $false
# 优先问本机后端：它是否已与望远镜建立并保持连接（设备只允许单一 TCP 连接，
# 后端在线时直接探测 4700 反而会超时，因此这里以 Alpaca 状态为准）。
$alpacaOk = $false
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5555/api/v1/telescope/1/connected?ClientID=1&ClientTransactionID=1' -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    $j = $r.Content | ConvertFrom-Json
    if ($j.ErrorNumber -eq 0) { $alpacaOk = $true; $anyOnline = [bool]$j.Value }
} catch { }

if ($alpacaOk) {
    if ($anyOnline) {
        Write-Host ("  [在线] 后端已连接望远镜（" + $scopeIp + "）") -ForegroundColor Green
        try {
            $r2 = Invoke-WebRequest -Uri 'http://127.0.0.1:5555/api/v1/telescope/1/rightascension?ClientID=1&ClientTransactionID=2' -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $ra = ($r2.Content | ConvertFrom-Json).Value
            $r3 = Invoke-WebRequest -Uri 'http://127.0.0.1:5555/api/v1/telescope/1/declination?ClientID=1&ClientTransactionID=3' -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $dec = ($r3.Content | ConvertFrom-Json).Value
            Write-Host ("         当前指向：RA {0:N3}h  Dec {1:N3}°" -f $ra, $dec) -ForegroundColor DarkGray
        } catch {}
    } else {
        Write-Host "  [待连] 后端在运行，但望远镜未连接" -ForegroundColor Yellow
        Write-Host ("         检查望远镜是否开机、IP 是否为 " + $scopeIp + "。") -ForegroundColor DarkGray
    }
} else {
    # 后端没启动时，才直接探测端口
    $targets = @($scopeIp, 'seestar.local', '192.168.1.1')
    foreach ($h in $targets) {
        $ok = $false
        try {
            $c = New-Object System.Net.Sockets.TcpClient
            $iar = $c.BeginConnect($h, 4700, $null, $null)
            if ($iar.AsyncWaitHandle.WaitOne(1500)) { $c.EndConnect($iar); $ok = $c.Connected }
            $c.Close()
        } catch { $ok = $false }
        if ($ok) { $anyOnline = $true; Write-Host ("  [在线] " + $h + ":4700（后端未启动）") -ForegroundColor Green }
        else { Write-Host ("  [离线] " + $h + ":4700") -ForegroundColor DarkGray }
    }
}
Write-Host ""
if (-not $anyOnline) {
    Write-Host "  → 未发现望远镜。请确认：望远镜已开机；电脑与望远镜处于同一 WiFi。" -ForegroundColor Yellow
    Write-Host "    · 站模式：望远镜连家里 WiFi，电脑连同一路由器，查路由器分配到的 IP。" -ForegroundColor DarkGray
    Write-Host "    · AP  模式：电脑直连 Seestar_xxxx 热点，望远镜通常是 192.168.1.1。" -ForegroundColor DarkGray
    Write-Host "    · 本机扫描：python scripts\scan_net.py 192.168.2" -ForegroundColor DarkGray
}
Write-Host ""

Write-Host "[6/6] 系统代理冲突（会让 MCP 连不上本机后端）"
$proxyOn = $false
try {
    $reg = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
    if ($reg.ProxyEnable -eq 1 -and $reg.ProxyServer) {
        $proxyOn = $true
        Write-Host ("  [注意] 系统代理已开启：" + $reg.ProxyServer) -ForegroundColor Yellow
        Write-Host "         本方案已用 trust_env=False 绕过，正常使用无需关闭代理。" -ForegroundColor DarkGray
        Write-Host "         若 MCP 报 HTTP 502，请重启 opencode 让 MCP 进程重新加载。" -ForegroundColor DarkGray
    }
} catch { }
if (-not $proxyOn) { Write-Host "  [OK]   未检测到系统代理" -ForegroundColor Green }
Write-Host ""

Write-Host "==========================================================" -ForegroundColor Cyan
if ((Test-Path "$root\seestar_alp\.venv\Scripts\python.exe") -and
    (Test-Path "$root\seestar-mcp\.venv\Scripts\python.exe") -and
    (Test-Path $pem) -and
    ($raw -match 'seestar_mcp\.server')) {
    Write-Host "  软件部署：全部就绪 ✓" -ForegroundColor Green
} else {
    Write-Host "  软件部署：尚有项目未完成（见上方黄色提示）" -ForegroundColor Yellow
}
Write-Host "==========================================================" -ForegroundColor Cyan
