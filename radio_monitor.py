"""Radio catalogue: allowlisted stations, health probes and ICY track titles.

The iPad plays the stream directly, so this module never relays audio. It only
answers two questions the browser cannot: "is this station reachable?" and
"what is playing right now?" (ICY metadata is invisible to <audio>).
"""
import http.client
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
import urllib.request

STATIONS_FILE = Path(__file__).resolve().parent / 'stations.json'
USER_AGENT = 'iPad-dashboard/1.0 (radio health check)'
HEALTH_INTERVAL = 600
TITLE_TTL = 20
PROBE_BYTES = 512

FALLBACK = [
    {"id": "cnr3", "name": "音乐之声", "group": "音乐",
     "url": "https://ngcdn001.cnr.cn/live/yyzs/index.m3u8"},
    {"id": "cnr1", "name": "中国之声", "group": "资讯",
     "url": "https://ngcdn001.cnr.cn/live/zgzs/index.m3u8"},
]

ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
PRIVATE_HOST_RE = re.compile(
    r'^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.0\.0\.0|\[?::1\]?|'
    r'172\.(1[6-9]|2\d|3[01])\.)', re.I)


def codec_of(url: str) -> str:
    """Guess the container so the UI can label HLS streams honestly."""
    path = urlsplit(url).path.lower()
    if path.endswith('.m3u8'):
        return 'hls'
    if path.endswith('.aac') or 'aac' in path:
        return 'aac'
    return 'mp3'


def valid_url(url: str) -> bool:
    """Accept only public http(s) audio endpoints, never LAN addresses."""
    if not url or len(url) > 500:
        return False
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return False
    if parts.username or parts.password:
        return False
    return not PRIVATE_HOST_RE.match(parts.hostname)


def normalise(raw) -> list:
    """Drop malformed rows instead of letting one typo break the whole list."""
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        sid = str(row.get('id') or '').strip()
        name = str(row.get('name') or '').strip()
        url = str(row.get('url') or '').strip()
        if not ID_RE.match(sid) or sid in seen:
            continue
        if not name or len(name) > 40 or not valid_url(url):
            continue
        seen.add(sid)
        group = str(row.get('group') or '其他').strip()[:8] or '其他'
        out.append({"id": sid, "name": name, "group": group,
                    "url": url, "codec": codec_of(url)})
    return out


def load_stations(path: Path = STATIONS_FILE) -> list:
    """Read stations.json; fall back to a minimal list rather than an empty UI."""
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return normalise(FALLBACK)
    return normalise(raw) or normalise(FALLBACK)


def probe(url: str, timeout: float = 6.0) -> dict:
    """Fetch a few bytes so we can report reachability and the real content type."""
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Icy-MetaData': '0'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(PROBE_BYTES)
            content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
            ok = response.status == 200 and (
                content_type.startswith('audio/') or 'mpegurl' in content_type)
            return {"status": "ok" if ok else "fail", "content_type": content_type,
                    "code": response.status, "at": int(time.time())}
    except Exception as error:  # noqa: BLE001 - every failure means "unreachable"
        return {"status": "fail", "content_type": "", "code": 0,
                "error": type(error).__name__, "at": int(time.time())}


def decode_meta(raw: bytes) -> str:
    """ICY is nominally Latin-1, but Chinese stations send UTF-8 or GBK."""
    for encoding in ('utf-8', 'gbk'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1', 'ignore')


def parse_icy_title(block: bytes, metaint: int) -> str:
    """Extract StreamTitle from one ICY metadata block."""
    if metaint <= 0 or len(block) <= metaint:
        return ''
    length = block[metaint] * 16
    if not length or len(block) < metaint + 1 + length:
        return ''
    text = decode_meta(block[metaint + 1: metaint + 1 + length])
    found = re.search(r"StreamTitle='(.*?)';", text, re.S)
    if not found:
        return ''
    return re.sub(r'\s+', ' ', found.group(1)).strip()[:120]


def fetch_icy_title(url: str, timeout: float = 6.0) -> str:
    """Open the stream just far enough to read the current track name."""
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return ''
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    target = (parts.path or '/') + (('?' + parts.query) if parts.query else '')
    make = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
    connection = make(parts.hostname, port, timeout=timeout)
    try:
        connection.request('GET', target, headers={
            'User-Agent': USER_AGENT, 'Icy-MetaData': '1', 'Connection': 'close'})
        response = connection.getresponse()
        if response.status != 200:
            return ''
        try:
            metaint = int(response.getheader('icy-metaint') or 0)
        except (TypeError, ValueError):
            return ''
        if metaint <= 0 or metaint > 65536:
            return ''
        return parse_icy_title(response.read(metaint + 4080), metaint)
    finally:
        connection.close()


class RadioMonitor:
    """Health and now-playing cache; audio itself never passes through here."""

    def __init__(self, station_loader=load_stations, prober=probe, title_fetcher=fetch_icy_title):
        self.loader = station_loader
        self.prober = prober
        self.title_fetcher = title_fetcher
        self.lock = threading.Lock()
        self.stations = []
        self.health = {}
        self.titles = {}
        self.started = False
        self.checked_at = 0

    def refresh(self) -> None:
        """Re-read the station file (edits apply without restarting the server)."""
        stations = self.loader()
        with self.lock:
            self.stations = stations
            self.health = {s['id']: self.health.get(s['id'], {"status": "unknown"})
                           for s in stations}

    def check_all(self) -> None:
        self.refresh()
        for station in self.stations:
            result = self.prober(station['url'])
            with self.lock:
                self.health[station['id']] = result
        self.checked_at = int(time.time())

    def loop(self) -> None:
        while True:
            try:
                self.check_all()
            except Exception:  # noqa: BLE001 - a probe failure must not kill the thread
                pass
            time.sleep(HEALTH_INTERVAL)

    def start(self) -> None:
        if self.started:
            return
        self.started = True
        thread = threading.Thread(target=self.loop, name='radio-health', daemon=True)
        thread.start()

    def snapshot(self) -> dict:
        self.start()
        if not self.stations:
            # First request must not wait for the health thread to finish its pass.
            self.refresh()
        with self.lock:
            stations = [dict(s, health=self.health.get(s['id'], {"status": "unknown"}))
                        for s in self.stations]
        return {"stations": stations, "checked_at": self.checked_at}

    def now(self, station_id: str) -> dict:
        """Return the cached track title, refreshing at most every TITLE_TTL seconds."""
        station = next((s for s in self.stations if s['id'] == station_id), None)
        if station is None:
            return {"id": "", "title": "", "source": "unknown"}
        with self.lock:
            cached = self.titles.get(station_id)
        if cached and time.time() - cached['at'] < TITLE_TTL:
            return dict(cached, id=station_id)
        title = ''
        try:
            title = self.title_fetcher(station['url'])
        except Exception:  # noqa: BLE001 - metadata is optional
            title = ''
        entry = {"id": station_id, "title": title, "at": int(time.time()),
                 "source": "icy" if title else "none"}
        with self.lock:
            self.titles[station_id] = entry
        return entry


radio_monitor = RadioMonitor()
