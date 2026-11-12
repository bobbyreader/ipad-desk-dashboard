"""Cached, read-only Mihomo sampler with offline destination geolocation."""
import copy
import ipaddress
import json
from pathlib import Path
import subprocess
import threading
import time

from geo_places import PLACES
from settings import SETTINGS

ROOT = Path(__file__).resolve().parent


def open_geoip_reader(geoip_path: str | Path | None):
    """Open an optional local MaxMind/Meta GeoIP database; degrade cleanly if absent."""
    if not geoip_path:
        return None
    target = Path(geoip_path)
    if not target.is_absolute():
        target = ROOT / target
    if not target.is_file():
        return None
    try:
        import maxminddb
        return maxminddb.open_database(str(target))
    except (ImportError, OSError, ValueError):
        return None


class ProxyMonitor:
    """Sample once for all viewers, withholding raw IPs and connection identifiers."""

    def __init__(self, geoip_path: str | Path | None = None) -> None:
        """Initialize an empty snapshot and optional local GeoIP reader."""
        self.lock = threading.Lock()
        self.data = {'available': False, 'message': '正在连接代理核心', 'updated': None}
        self.previous = None
        self.history = []
        configured_path = geoip_path or (SETTINGS.get('proxy') or {}).get('geoip_path', 'data/geoip.metadb')
        self.reader = open_geoip_reader(configured_path)
        self._started = False

    def country(self, row: dict) -> str:
        """Resolve a public destination locally; unsupported locations stay unknown."""
        try:
            if not ipaddress.ip_address(row.get('ip', '')).is_global:
                return ''
        except ValueError:
            return ''
        candidates = row.get('geo', [])
        if isinstance(candidates, str):
            candidates = [candidates]
        if not candidates and self.reader:
            result = self.reader.get(row['ip'])
            if isinstance(result, list):
                candidates = result
            elif isinstance(result, dict):
                candidates = [result.get('country', {}).get('iso_code', '')]
        return next((str(c).upper() for c in candidates if str(c).upper() in PLACES), '')

    def ingest(self, raw: dict, now: float) -> dict:
        """Calculate interval rates and aggregate active connections by country."""
        before = self.previous
        elapsed = now - before['time'] if before else 0
        valid = bool(before and 0 < elapsed < 20 and
                     raw['download'] >= before['download'] and
                     raw['upload'] >= before['upload'])
        down = (raw['download'] - before['download']) / elapsed if valid else None
        up = (raw['upload'] - before['upload']) / elapsed if valid else None
        regions = {}
        unknown = direct = 0
        previous_bytes = before['bytes'] if valid else {}
        current_bytes = {}
        for row in raw['connections']:
            current_bytes[row['id']] = row['bytes']
            direct += bool(row.get('direct'))
            code = self.country(row)
            if not code:
                unknown += 1
                continue
            name, lon, lat = PLACES[code]
            region = regions.setdefault(code, {'code': code, 'name': name, 'lon': lon,
                                                'lat': lat, 'count': 0, 'bytes_per_sec': 0})
            region['count'] += 1
            if valid and row['id'] in previous_bytes:
                region['bytes_per_sec'] += max(0, row['bytes'] - previous_bytes[row['id']]) / elapsed
        self.previous = {'time': now, 'download': raw['download'], 'upload': raw['upload'],
                         'bytes': current_bytes}
        self.history.append({'down': down, 'up': up})
        self.history = self.history[-60:]
        return {'available': True, 'updated': time.time(), 'download_rate': down,
                'upload_rate': up, 'download_total': raw['download'],
                'upload_total': raw['upload'], 'connections': len(raw['connections']),
                'direct': direct, 'unknown': unknown, 'countries': list(regions.values()),
                'history': list(self.history), 'geo_available': self.reader is not None}

    def poll(self) -> None:
        """Fetch a sanitized remote snapshot, preserving failure as an explicit state."""
        cfg = SETTINGS.get('proxy') or {}
        ssh_host = str(cfg.get('ssh_host') or '').strip()
        if not ssh_host:
            self.previous = None
            self.history = []
            with self.lock:
                self.data = {'available': False, 'message': '代理监控未配置（请设置 proxy.ssh_host）',
                             'updated': time.time()}
            return
        config_path = str(cfg.get('mihomo_config') or '/opt/1panel/apps/mihomo/mihomo/config.yaml').strip()
        api_url = str(cfg.get('mihomo_api') or 'http://127.0.0.1:9090/connections').strip()
        if not api_url.startswith(('http://', 'https://')):
            api_url = 'http://127.0.0.1:9090/connections'
        preamble = f"CONFIG_PATH = {json.dumps(config_path)}\nAPI_URL = {json.dumps(api_url)}\n"
        script = preamble + (ROOT / 'remote_proxy.py').read_text(encoding='utf-8')
        try:
            result = subprocess.run(
                ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
                 '-o', 'StrictHostKeyChecking=yes', ssh_host, 'python3 -'],
                input=script, capture_output=True,
                text=True, timeout=7, check=True,
            )
            raw = json.loads(result.stdout)
            data = self.ingest(raw, time.monotonic())
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            self.previous = None
            self.history = []
            data = {'available': False, 'message': '代理核心暂不可达', 'updated': time.time()}
        with self.lock:
            self.data = data

    def snapshot(self) -> dict:
        """Return a detached snapshot, marking stalled sampling unavailable."""
        with self.lock:
            data = copy.deepcopy(self.data)
        if data.get('updated') and time.time() - data['updated'] > 15:
            return {'available': False, 'message': '代理数据已过期', 'updated': data['updated']}
        return data

    def run(self) -> None:
        """Continuously sample every three seconds, including fetch duration."""
        while True:
            started = time.monotonic()
            self.poll()
            time.sleep(max(0.2, 3 - (time.monotonic() - started)))

    def start(self) -> None:
        """Start one daemon collector independent of browser polling."""
        if self._started:
            return
        self._started = True
        threading.Thread(target=self.run, daemon=True, name='mihomo-monitor').start()


monitor = ProxyMonitor()
