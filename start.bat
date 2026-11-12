@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>&1 && (
  py -3 --version >nul 2>&1 && set "PY_CMD=py -3"
)
if not defined PY_CMD (
  where python >nul 2>&1 && set "PY_CMD=python"
)
if not defined PY_CMD (
  echo [错误] 未检测到 Python 3。请前往 https://www.python.org/downloads/ 安装，并勾选 "Add Python to PATH"。
  pause
  exit /b 1
)

if not exist "config.json" (
  if exist "config.example.json" (
    copy /Y "config.example.json" "config.json" >nul
    echo 已生成默认配置文件 config.json（可按需修改）。
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境 .venv ...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [错误] 创建虚拟环境失败。
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import maxminddb" >nul 2>&1
if errorlevel 1 (
  echo 正在安装可选依赖（requirements.txt）...
  ".venv\Scripts\pip.exe" install -r requirements.txt
  if errorlevel 1 (
    echo [提示] maxminddb 安装失败，不影响基础模式运行（仅影响离线 GeoIP 地图定位）。
  )
)

for /f %%i in ('".venv\Scripts\python.exe" -c "from settings import SETTINGS; print(SETTINGS['server']['port'])"') do set "PORT=%%i"
if not defined PORT set "PORT=8788"

echo.
echo ==========================================
echo   桌边控制屏正在启动（端口: %PORT%）
echo   请在 iPad Safari 打开以下局域网地址：
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | ForEach-Object { Write-Host ('    -> http://' + $_.IPAddress + ':%PORT%') }" 2>nul
echo   本机预览: http://127.0.0.1:%PORT%
echo.
echo   [提示] 若 iPad 无法访问，请在 Windows 防火墙弹出提示时
echo          勾选“专用网络”并点击允许访问；或查看 README 放行 %PORT% 端口。
echo ==========================================
echo.

".venv\Scripts\python.exe" server.py
pause
