"""Read-only LAN dashboard for older iPads; cross-platform (macOS/Windows/Linux)."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import parse_qs, urlsplit

from aihot_monitor import aihot_monitor
from host_monitor import host_snapshot
from music_library import library
from music_search import music_search
from proxy_monitor import monitor
from radio_monitor import radio_monitor
from readhub_monitor import readhub_monitor
from router_monitor import router_monitor
from settings import SETTINGS, public_config

ROOT = Path(__file__).resolve().parent
ASSETS = {
    "index.html": "text/html",
    "app.js": "application/javascript",
    "theme.css": "text/css",
    "style.css": "text/css",
    "theme-init.js": "application/javascript",
    "network.js": "application/javascript",
    "network.css": "text/css",
    "news.js": "application/javascript",
    "ticker.js": "application/javascript",
    "readhub.js": "application/javascript",
    "library-ui.js": "application/javascript",
    "radio.js": "application/javascript",
}


def feature_enabled(name: str) -> bool:
    """Return whether a dashboard feature is enabled in SETTINGS."""
    return bool((SETTINGS.get("features") or {}).get(name))


class _UnixHTTPConnection(http.client.HTTPConnection):
    """Minimal HTTP-over-Unix-socket client for /var/run/docker.sock."""

    def __init__(self, socket_path: str, timeout: float = 4.0) -> None:
        super().__init__('localhost', timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def docker_socket_status(socket_path: str = '/var/run/docker.sock') -> dict:
    """Query Docker Engine API directly over Unix socket without docker CLI."""
    conn = _UnixHTTPConnection(socket_path, timeout=4.0)
    try:
        conn.request('GET', '/containers/json?all=true')
        resp = conn.getresponse()
        if resp.status != 200:
            return {"available": False, "message": "Docker Socket 返回异常", "containers": []}
        rows = json.loads(resp.read(2097152).decode('utf-8', 'replace'))
        containers = []
        for row in rows:
            names = row.get('Names') or []
            name = str(names[0]).lstrip('/') if names else str(row.get('Id', ''))[:12]
            containers.append({
                "name": name,
                "status": str(row.get('Status') or ''),
                "state": str(row.get('State') or ''),
            })
        return {"available": True, "containers": containers}
    except (OSError, http.client.HTTPException, ValueError, KeyError):
        return {"available": False, "message": "Docker Socket 不可用", "containers": []}
    finally:
        conn.close()


def docker_status() -> dict:
    """Return container summaries from local Docker/socket or remote SSH, or disabled."""
    if not feature_enabled("docker"):
        return {"available": False, "disabled": True, "message": "Docker 监控未启用", "containers": []}
    docker_cfg = SETTINGS.get("docker") or {}
    mode = str(docker_cfg.get("mode") or "local").strip().lower()
    sock_path = str(docker_cfg.get("socket_path") or "/var/run/docker.sock").strip()
    if mode == "off":
        return {"available": False, "disabled": True, "message": "Docker 监控已关闭", "containers": []}
    if mode == "socket":
        return docker_socket_status(sock_path)
    if mode == "ssh":
        ssh_host = str(docker_cfg.get("ssh_host") or "").strip()
        if not ssh_host:
            return {"available": False, "message": "未配置 docker.ssh_host", "containers": []}
        cmd = [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3",
            "-o", "StrictHostKeyChecking=yes", ssh_host,
            "docker ps --all --format '{{json .}}'",
        ]
        fail_msg = "远程 Docker 连接失败（SSH 或 Docker 不可用）"
    else:
        cmd = ["docker", "ps", "--all", "--format", "{{json .}}"]
        fail_msg = "本机 Docker 不可用（请确认 Docker 已启动）"

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=6, check=False)
        if result.returncode:
            return {"available": False, "message": fail_msg, "containers": []}
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        return {
            "available": True,
            "containers": [
                {"name": row["Names"], "status": row["Status"], "state": row.get("State", "")}
                for row in rows
            ],
        }
    except FileNotFoundError:
        if mode == "local" and Path(sock_path).exists():
            return docker_socket_status(sock_path)
        return {"available": False, "message": fail_msg, "containers": []}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
        return {"available": False, "message": fail_msg, "containers": []}


def snapshot() -> dict:
    """Collect host capacity/memory/load and optional Docker status."""
    host_data = host_snapshot() if feature_enabled("host") else None
    return {
        "updated": int(time.time()),
        "host": host_data,
        "docker": docker_status(),
    }


def _disabled_payload(message: str = "该模块未启用") -> bytes:
    return json.dumps({"available": False, "disabled": True, "message": message}, ensure_ascii=False).encode()


class Handler(BaseHTTPRequestHandler):
    """Serve only allowlisted dashboard assets and read-only status endpoints."""

    def serve_audio(self, song_id: str) -> None:
        """Pipe one library song, honouring Range so the iPad can seek."""
        if not feature_enabled("library"):
            message = _disabled_payload("音乐库未启用")
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(message)
            return
        try:
            upstream = library.open_stream(song_id, self.headers.get("Range"))
        except Exception as error:  # noqa: BLE001 - report, never crash the server
            message = json.dumps({"available": False, "message": "取音频失败（%s）" % type(error).__name__},
                                 ensure_ascii=False).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(message)
            return
        status = getattr(upstream, "status", 200)
        headers = upstream.headers
        content_type = headers.get("Content-Type", "")
        if not content_type.startswith("audio/"):
            upstream.close()
            message = json.dumps({"available": False, "message": "这首歌不存在或已从库中移除"},
                                 ensure_ascii=False).encode()
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(message)
            return
        self.send_response(206 if status == 206 else 200)
        self.send_header("Content-Type", content_type)
        for name in ("Content-Length", "Content-Range"):
            if headers.get(name):
                self.send_header(name, headers[name])
        if headers.get("Accept-Ranges"):
            self.send_header("Accept-Ranges", headers["Accept-Ranges"])
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()

    def do_GET(self) -> None:
        """Serve an allowlisted resource without exposing local files or secrets."""
        route = urlsplit(self.path).path
        query_all = parse_qs(urlsplit(self.path).query)
        if route == "/api/library/cover":
            if not feature_enabled("library"):
                self.send_error(404)
                return
            try:
                mime, body = library.cover(query_all.get("id", [""])[0])
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "/api/library/audio":
            self.serve_audio(query_all.get("id", [""])[0])
            return

        if route == "/config.js":
            payload = json.dumps(public_config(SETTINGS), ensure_ascii=False)
            body = ("window.DASHBOARD_CONFIG=" + payload + ";").encode("utf-8")
            mime = "application/javascript; charset=utf-8"
        elif route == "/api/config":
            body = json.dumps(public_config(SETTINGS), ensure_ascii=False).encode("utf-8")
            mime = "application/json; charset=utf-8"
        elif route == "/api/library/albums":
            body = json.dumps(library.albums(), ensure_ascii=False).encode() if feature_enabled("library") else _disabled_payload("音乐库未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/library/album":
            body = json.dumps(library.album(query_all.get("id", [""])[0]), ensure_ascii=False).encode() if feature_enabled("library") else _disabled_payload("音乐库未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/library/search":
            body = json.dumps(library.search(query_all.get("q", [""])[0]), ensure_ascii=False).encode() if feature_enabled("library") else _disabled_payload("音乐库未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/music/search":
            query = query_all.get("q", [""])[0]
            body = json.dumps(music_search.search(query), ensure_ascii=False).encode() if feature_enabled("music_search") else _disabled_payload("在线搜歌未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/music/url":
            song = query_all.get("id", [""])[0]
            body = json.dumps(music_search.resolve(song), ensure_ascii=False).encode() if feature_enabled("music_search") else _disabled_payload("在线搜歌未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/radio":
            body = json.dumps(radio_monitor.snapshot(), ensure_ascii=False).encode() if feature_enabled("radio") else _disabled_payload("电台未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/radio/now":
            station_id = query_all.get("id", [""])[0]
            body = json.dumps(radio_monitor.now(station_id), ensure_ascii=False).encode() if feature_enabled("radio") else _disabled_payload("电台未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/readhub":
            body = json.dumps(readhub_monitor.snapshot(), ensure_ascii=False).encode() if feature_enabled("readhub") else _disabled_payload("Readhub 未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/aihot":
            body = json.dumps(aihot_monitor.snapshot(), ensure_ascii=False).encode() if feature_enabled("aihot") else _disabled_payload("AIHOT 未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/router":
            body = json.dumps(router_monitor.snapshot(), ensure_ascii=False).encode() if feature_enabled("router") else _disabled_payload("旁路由监控未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/proxy":
            body = json.dumps(monitor.snapshot(), ensure_ascii=False).encode() if feature_enabled("proxy") else _disabled_payload("代理监控未启用")
            mime = "application/json; charset=utf-8"
        elif route == "/api/status":
            body = json.dumps(snapshot(), ensure_ascii=False).encode()
            mime = "application/json; charset=utf-8"
        elif route == "/" or (route.startswith("/") and route[1:] in ASSETS):
            filename = "index.html" if route == "/" else route[1:]
            body = (ROOT / filename).read_bytes()
            mime = ASSETS[filename] + "; charset=utf-8"
        else:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "media-src http: https:; img-src 'self' data:; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)


def start_collectors() -> None:
    """Start only background threads for features enabled in SETTINGS."""
    if feature_enabled("proxy"):
        monitor.start()
    if feature_enabled("router"):
        router_monitor.start()
    if feature_enabled("aihot"):
        aihot_monitor.start()
    if feature_enabled("readhub"):
        readhub_monitor.start()
    if feature_enabled("radio"):
        radio_monitor.start()


if __name__ == "__main__":
    srv_cfg = SETTINGS.get("server") or {}
    host = str(srv_cfg.get("host") or "0.0.0.0")
    port = int(srv_cfg.get("port") or 8788)
    print(f"Dashboard: http://{host}:{port}", flush=True)
    start_collectors()
    ThreadingHTTPServer((host, port), Handler).serve_forever()
