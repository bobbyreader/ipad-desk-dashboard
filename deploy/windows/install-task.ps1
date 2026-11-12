<#
.SYNOPSIS
  在 Windows 上为“桌边控制屏”配置防火墙放行与登录后静默自启任务。
.USAGE
  以管理员身份在 PowerShell 中运行（仅防火墙规则需要管理员权限；自启任务可单独运行）：
  powershell -ExecutionPolicy Bypass -File .\deploy\windows\install-task.ps1
#>

$ErrorActionPreference = "Stop"
$rootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonw = Join-Path $rootDir ".venv\Scripts\pythonw.exe"
$serverPy = Join-Path $rootDir "server.py"

if (-not (Test-Path $pythonw)) {
    Write-Error "未找到 $pythonw ，请先运行一次 start.bat 创建虚拟环境。"
}

$port = & (Join-Path $rootDir ".venv\Scripts\python.exe") -c "from settings import SETTINGS; print(SETTINGS['server']['port'])"
if (-not $port) { $port = 8788 }

# 1. 注册登录后静默自启（无黑框）
$taskName = "iPadDeskDashboard"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$serverPy`"" -WorkingDirectory $rootDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "iPad 桌边控制屏后台服务" -Force | Out-Null
Write-Host "[完成] 已注册开机/登录自启任务: $taskName" -ForegroundColor Green

# 2. 尝试放行专用网络入站端口（需要管理员权限）
try {
    $ruleName = "iPad Desk Dashboard ($port)"
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -LocalPort $port -Protocol TCP -Action Allow -Profile Private | Out-Null
        Write-Host "[完成] 已添加 Windows 防火墙专用网络入站规则（TCP $port）" -ForegroundColor Green
    } else {
        Write-Host "[跳过] 防火墙规则已存在: $ruleName"
    }
} catch {
    Write-Host "[提示] 添加防火墙规则需要管理员权限。如未用管理员打开 PowerShell，请手动在防火墙放行端口 $port。" -ForegroundColor Yellow
}
