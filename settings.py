"""Central configuration loader with safe defaults, JSON file and env overrides.

Secrets and internal LAN addresses stay in config.json (gitignored) or
environment variables, and public_config() exposes only sanitized UI flags.
"""
import copy
import json
import os
from pathlib import Path
import platform
import socket

ROOT = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "site": {
        "title": "桌边控制屏",
        "subtitle": "",
        "greeting": "留一块屏，给日常。",
        "links_title": "常用入口",
        "links_lead": "快捷入口沿用各自站点的登录方式，这里只提供跳转卡片。",
        "links": [],
    },
    "server": {
        "host": "0.0.0.0",
        "port": 8788,
    },
    "features": {
        "host": True,
        "aihot": True,
        "readhub": True,
        "radio": True,
        "music_search": True,
        "docker": False,
        "router": False,
        "proxy": False,
        "library": False,
        "links": False,
    },
    "docker": {
        "mode": "local",
        "label": "Docker",
        "ssh_host": "",
        "admin_url": "",
    },
    "router": {
        "ssh_host": "",
        "interface": "eth0",
        "lan_cidr": "192.168.1.0/24",
        "aliases": {},
        "geoip_path": "data/geoip.metadb",
    },
    "proxy": {
        "mode": "ssh",
        "ssh_host": "",
        "label": "Mihomo",
        "mihomo_config": "/opt/1panel/apps/mihomo/mihomo/config.yaml",
        "mihomo_api": "http://127.0.0.1:9090/connections",
        "geoip_path": "data/geoip.metadb",
    },
    "library": {
        "url": "",
        "user": "",
        "password": "",
        "hint": "浏览本地 Navidrome 音乐库 · 点选专辑或搜索曲目。",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _default_subtitle() -> str:
    system = platform.system()
    os_name = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(system, system or "Host")
    host = socket.gethostname().split(".")[0]
    return f"{host} · {os_name}" if host else os_name


def _safe_links(raw_links) -> list:
    if not isinstance(raw_links, list):
        return []
    links = []
    for row in raw_links[:12]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()[:40]
        url = str(row.get("url") or "").strip()[:300]
        if not title or not url.startswith(("http://", "https://")):
            continue
        desc = str(row.get("desc") or "").strip()[:80]
        domain = url.split("://", 1)[1].split("/", 1)[0][:60]
        links.append({"title": title, "desc": desc, "url": url, "domain": domain})
    return links


def _env_bool(name: str):
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings(config_path: Path | str | None = None) -> dict:
    """Load merged settings from defaults, config.json and env vars."""
    target = Path(config_path) if config_path else Path(os.environ.get("DASHBOARD_CONFIG", ROOT / "config.json"))
    file_data = {}
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                file_data = loaded
        except (OSError, ValueError):
            file_data = {}

    cfg = _deep_merge(DEFAULT_CONFIG, file_data)

    if os.environ.get("DASHBOARD_HOST"):
        cfg["server"]["host"] = os.environ["DASHBOARD_HOST"].strip()
    if os.environ.get("DASHBOARD_PORT"):
        try:
            cfg["server"]["port"] = int(os.environ["DASHBOARD_PORT"])
        except ValueError:
            pass
    if os.environ.get("NAVIDROME_URL"):
        cfg["library"]["url"] = os.environ["NAVIDROME_URL"].strip().rstrip("/")
    if os.environ.get("NAVIDROME_USER"):
        cfg["library"]["user"] = os.environ["NAVIDROME_USER"].strip()
    if os.environ.get("NAVIDROME_PASSWORD"):
        cfg["library"]["password"] = os.environ["NAVIDROME_PASSWORD"]

    for feat in list(cfg["features"].keys()):
        override = _env_bool("DASHBOARD_FEATURE_" + feat.upper())
        if override is not None:
            cfg["features"][feat] = override

    # Normalize links and subtitle.
    if not str(cfg["site"].get("subtitle") or "").strip():
        cfg["site"]["subtitle"] = _default_subtitle()
    cfg["site"]["links"] = _safe_links(cfg["site"].get("links"))

    # Auto-disable network/docker/library backends if required credentials/targets are absent?
    # Keep explicit boolean flags so the UI can show clear configuration errors if enabled intentionally.
    return cfg


def public_config(cfg: dict) -> dict:
    """Return a strictly sanitized subset safe to expose to the browser."""
    features = {k: bool(v) for k, v in (cfg.get("features") or {}).items()}
    links = cfg.get("site", {}).get("links") or []
    # Hide the extra screen tab if links feature is disabled or empty.
    has_links = bool(features.get("links") and links)
    docker_cfg = cfg.get("docker") or {}
    admin_url = str(docker_cfg.get("admin_url") or "").strip()
    if not admin_url.startswith(("http://", "https://")):
        admin_url = ""
    return {
        "site": {
            "title": str(cfg.get("site", {}).get("title") or "桌边控制屏")[:40],
            "subtitle": str(cfg.get("site", {}).get("subtitle") or "")[:60],
            "greeting": str(cfg.get("site", {}).get("greeting") or "")[:80],
            "links_title": str(cfg.get("site", {}).get("links_title") or "常用入口")[:40],
            "links_lead": str(cfg.get("site", {}).get("links_lead") or "")[:140],
            "links": links if has_links else [],
        },
        "features": {
            "host": features.get("host", True),
            "aihot": features.get("aihot", True),
            "readhub": features.get("readhub", True),
            "radio": features.get("radio", True),
            "music_search": features.get("music_search", True),
            "docker": features.get("docker", False),
            "router": features.get("router", False),
            "proxy": features.get("proxy", False),
            "library": features.get("library", False),
            "links": has_links,
        },
        "docker": {
            "label": str(docker_cfg.get("label") or "Docker")[:30],
            "admin_url": admin_url,
        },
        "router": {
            "interface": str((cfg.get("router") or {}).get("interface") or "eth0")[:20],
            "source_label": str((cfg.get("router") or {}).get("ssh_host") or "旁路由").split("@")[-1][:40],
        },
        "proxy": {
            "label": str((cfg.get("proxy") or {}).get("label") or "Mihomo")[:30],
            "source_label": str((cfg.get("proxy") or {}).get("ssh_host") or "代理核心").split("@")[-1][:40],
        },
        "library": {
            "hint": str((cfg.get("library") or {}).get("hint") or "浏览本地音乐库 · 点选专辑或搜索曲目。")[:100],
        },
    }


SETTINGS = load_settings()


def reload_settings(config_path: Path | str | None = None) -> dict:
    """Reload SETTINGS in place."""
    global SETTINGS
    SETTINGS = load_settings(config_path)
    return SETTINGS
