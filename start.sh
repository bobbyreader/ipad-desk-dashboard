#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3.10+。"
  exit 1
fi

if [ ! -f config.json ] && [ -f config.example.json ]; then
  cp config.example.json config.json
  echo "已生成默认配置文件 config.json（可按需修改）。"
fi

if [ ! -d .venv ]; then
  echo "正在创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi

if [ "${SKIP_PIP:-0}" != "1" ]; then
  .venv/bin/python - <<'PY' || .venv/bin/pip install -r requirements.txt
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("maxminddb") else 1)
PY
fi

PORT="$(.venv/bin/python -c "from settings import SETTINGS; print(SETTINGS['server']['port'])")"

echo ""
echo "=========================================="
echo "  桌边控制屏正在启动（端口: ${PORT}）"
echo "  请在 iPad Safari 打开以下任一局域网地址："
if command -v ipconfig >/dev/null 2>&1; then
  for iface in en0 en1 en2 en3 en4 en5; do
    ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    if [ -n "$ip" ]; then
      echo "    -> http://${ip}:${PORT}"
    fi
  done
elif command -v hostname >/dev/null 2>&1; then
  for ip in $(hostname -I 2>/dev/null || true); do
    case "$ip" in
      *.*) echo "    -> http://${ip}:${PORT}" ;;
    esac
  done
fi
echo "  本机预览: http://127.0.0.1:${PORT}"
echo "=========================================="
echo ""

exec .venv/bin/python server.py
