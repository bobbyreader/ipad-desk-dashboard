"""Online music search: a thin server-side proxy to third-party catalogues.

Only metadata passes through here; audio is always played by the iPad straight
from the CDN (Range requests, no Mac bandwidth). Keywords do leave the LAN for
these upstreams - the panel labels that explicitly.

Two upstreams, tried in order:
  1. tang         -> QQ Music (m4a; two-step search then mid detail)
  2. Meting proxy -> NetEase (mp3; answers [] for long stretches, so second)
Both are unofficial; when they fail the panel says so instead of pretending.
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request

# The proxy rejects long browser-style UAs; this is the shortest form it accepts.
USER_AGENT = 'Mozilla/5.0'
NETEASE_SEARCH = 'https://api.qijieya.cn/meting/?server=netease&type=search&id='
NETEASE_URL = 'https://api.qijieya.cn/meting/?server=netease&type=url&id='
QQ_SEARCH = 'https://tang.api.s01s.cn/music_open_api.php?msg={query}&type=json'
QQ_DETAIL = 'https://tang.api.s01s.cn/music_open_api.php?msg={query}&type=json&mid={mid}'
ALLOWED_AUDIO_HOSTS = ('music.126.net', 'qqmusic.qq.com')

TIMEOUT = 8
SEARCH_TTL = 300
URL_TTL = 900
MAX_QUERY = 40
MAX_ITEMS = 20

QUERY_RE = re.compile(r"^[\w\s\u3400-\u9fff·\-&.,!'()（）]+$")


def clean_query(value: str) -> str:
    """Reject anything that is not a short, printable search phrase."""
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text or len(text) > MAX_QUERY or not QUERY_RE.match(text):
        return ''
    return text


def fetch_json(url: str, timeout: float = TIMEOUT):
    request = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(524288).decode('utf-8', 'replace'))


def host_allowed(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or '').lower()
    return any(host == allowed or host.endswith('.' + allowed) for allowed in ALLOWED_AUDIO_HOSTS)


def song_id(url: str) -> str:
    """The Meting proxy carries the catalogue id in its own query string."""
    try:
        return (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('id') or [''])[0]
    except ValueError:
        return ''


def parse_netease(raw) -> list:
    if not isinstance(raw, list):
        return []
    items, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get('name') or '').strip()[:80]
        sid = song_id(str(row.get('url') or ''))
        if not name or not re.match(r'^\d{1,20}$', sid) or sid in seen:
            continue
        seen.add(sid)
        items.append({"source": "netease", "ref": sid, "name": name,
                      "artist": str(row.get('artist') or '').strip()[:80],
                      "album": str(row.get('album') or '')[:60]})
        if len(items) >= MAX_ITEMS:
            break
    return items


def parse_qq(raw) -> list:
    """tang returns song_mid plus a pay flag; playback is resolved per mid."""
    data = raw if isinstance(raw, list) else (raw.get('data') if isinstance(raw, dict) else None)
    if not isinstance(data, list):
        return []
    items, seen = [], set()
    for row in data:
        if not isinstance(row, dict):
            continue
        name = str(row.get('song_title') or '').strip()[:80]
        mid = str(row.get('song_mid') or '').strip()
        if not name or not re.match(r'^[A-Za-z0-9]{6,32}$', mid) or mid in seen:
            continue
        seen.add(mid)
        items.append({"source": "qq", "ref": mid, "name": name,
                      "artist": str(row.get('singer_name') or '').strip()[:80],
                      "album": ''})
        if len(items) >= MAX_ITEMS:
            break
    return items


class MusicSearch:
    """TTL caches in front of two flaky upstreams; failures never raise."""

    def __init__(self, fetch=fetch_json):
        self.fetch = fetch
        self.lock = threading.Lock()
        self.cache = {}
        self.urls = {}
        self.tracks = {}

    def _cached(self, store, key, ttl):
        with self.lock:
            hit = store.get(key)
        if hit and time.time() - hit['at'] < ttl:
            return hit['value']
        return None

    def _remember(self, items, query):
        """Opaque ids so the browser never has to know the upstream shapes."""
        stamped = []
        for item in items:
            uid = '%s-%s-%d' % (item['source'], abs(hash((query, item['ref']))) % 10 ** 8, len(stamped))
            with self.lock:
                self.tracks[uid] = {"at": time.time(), "query": query,
                                    "source": item['source'], "ref": item['ref']}
            stamped.append({"id": uid, "source": item['source'], "name": item['name'],
                            "artist": item['artist'], "album": item['album']})
        return stamped

    def search(self, query: str) -> dict:
        text = clean_query(query)
        if not text:
            return {"available": False, "reason": "invalid", "items": [],
                    "message": "请输入 1–40 个字符的歌名或歌手"}
        cached = self._cached(self.cache, text, SEARCH_TTL)
        if cached is not None:
            return {"available": True, "cached": True,
                    "source": cached.get('source'), "items": cached['items']}

        errors = []
        # QQ first: the NetEase proxy answers [] for long stretches, so it is
        # the fallback rather than the default.
        for source, url, parser in (
            ("qq", QQ_SEARCH.format(query=urllib.parse.quote(text)), parse_qq),
            ("netease", NETEASE_SEARCH + urllib.parse.quote(text), parse_netease),
        ):
            try:
                items = parser(self.fetch(url))
            except Exception as error:  # noqa: BLE001 - upstream is best effort
                errors.append('%s:%s' % (source, type(error).__name__))
                continue
            if not items:
                errors.append('%s:empty' % source)
                continue
            stamped = self._remember(items, text)
            with self.lock:
                self.cache[text] = {"at": time.time(),
                                    "value": {"source": source, "items": stamped}}
            return {"available": True, "cached": False, "source": source, "items": stamped}

        return {"available": False, "reason": "upstream", "items": [],
                "message": "第三方接口都不可用（%s），稍后再试" % ', '.join(errors)}

    def resolve(self, uid: str, timeout: float = TIMEOUT) -> dict:
        """Turn our opaque id into a direct CDN URL for the iPad to stream."""
        cached = self._cached(self.urls, uid, URL_TTL)
        if cached is not None:
            return {"available": True, "url": cached, "cached": True}
        with self.lock:
            track = self.tracks.get(uid)
        if not track:
            return {"available": False, "message": "结果已过期，请重新搜索"}
        try:
            url = self._resolve_url(track, timeout)
        except Exception as error:  # noqa: BLE001
            return {"available": False, "message": "取播放地址失败（%s）" % type(error).__name__}
        if not url or not host_allowed(url):
            return {"available": False, "message": "上游没有返回可播放的直链"}
        with self.lock:
            self.urls[uid] = {"at": time.time(), "value": url}
        return {"available": True, "url": url, "cached": False}

    def _resolve_url(self, track: dict, timeout: float) -> str:
        if track['source'] == 'netease':
            request = urllib.request.Request(NETEASE_URL + track['ref'],
                                             headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.geturl()
        detail = self.fetch(QQ_DETAIL.format(query=urllib.parse.quote(track['query']),
                                             mid=track['ref']), timeout)
        if not isinstance(detail, dict):
            return ''
        for key in ('song_play_url', 'song_play_url_hq', 'song_play_url_pq', 'song_play_url_sq'):
            value = str(detail.get(key) or '')
            if value.startswith(('http://', 'https://')):
                return value
        return ''


music_search = MusicSearch()
