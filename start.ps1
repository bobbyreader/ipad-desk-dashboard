$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pyCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        & py -3 --version | Out-Null
        $pyCmd = @("py", "-3")
    } catch {}
}
if (-not $pyCmd -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $pyCmd = @("python")
}
if (-not $pyCmd) {
    Write-Host "[错误] 未检测到 Python 3，请先安装 Python 3.10+ 并勾选 Add to PATH。" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "config.json") -and (Test-Path "config.example.json")) {
    Copy-Item "config.example.json" "config.json"
    Write-Host "已生成默认配置文件 config.json。"
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "正在创建虚拟环境 .venv ..."
    if ($pyCmd.Count -eq 2) {
        & $pyCmd[0] $pyCmd[1] -m venv .venv
    } else {
        & $pyCmd[0] -m venv .venv
    }
}

$venvPy = ".venv\Scripts\python.exe"
$venvPip = ".venv\Scripts\pip.exe"

& $venvPy -c "import maxminddb" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "正在安装依赖 requirements.txt ..."
    try {
        & $venvPip install -r requirements.txt
    } catch {
        Write-Host "[提示] 可选包 maxminddb 安装失败，不影响基础模式运行。" -ForegroundColor Yellow
    }
}

$port = & $venvPy -c "from settings import SETTINGS; print(SETTINGS['server']['port'])"
if (-not $port) { $port = "8788" }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  桌边控制屏正在启动（端口: $port）"
Write-Host "  请在 iPad Safari 打开以下局域网地址："
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    ForEach-Object { Write-Host "    -> http://$($_.IPAddress):$port" -ForegroundColor Green }
Write-Host "  本机预览: http://127.0.0.1:$port"
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

& $venvPy server.py
