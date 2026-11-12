"""Cached read-only Readhub hot topics; no scraping of the HTML site."""
import copy
import gzip
import json
import re
import threading
import time
import urllib.error
import urllib.request

API = 'https://api.readhub.cn/topic/list?lastCursor=&pageSize=10'
SITE = 'https://readhub.cn/topic/'
UA = 'iPad-dashboard/1.0 (personal home dashboard)'
REFRESH = 600
STALE = 3600
UID = re.compile(r'^[A-Za-z0-9_-]{1,60}$')


def topic(row: dict) -> dict | None:
    """Reduce one topic to display fields with a validated Readhub link."""
    uid = str(row.get('uid', ''))
    if not UID.match(uid):
        return None
    sites = row.get('siteCount')
    return {
        'title': str(row.get('title', ''))[:240],
        'summary': str(row.get('summary', ''))[:400],
        'url': SITE + uid,
        'source': str(row.get('siteNameDisplay') or '')[:60],
        'sites': sites if isinstance(sites, int) and 0 <= sites < 100000 else None,
        'published': str(row.get('publishDate') or row.get('createdAt') or '')[:40],
    }


def fetch_topics() -> list[dict]:
    """Fetch and validate the documented JSON endpoint."""
    request = urllib.request.Request(API, headers={
        'User-Agent': UA, 'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read()
        if response.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
    payload = json.loads(raw)
    rows = (payload.get('data') or {}).get('items')
    if not isinstance(rows, list):
        raise ValueError('Unexpected Readhub payload')
    return [item for row in rows if isinstance(row, dict) and (item := topic(row))][:10]


class ReadhubMonitor:
    """Refresh hot topics every ten minutes and keep the last good copy."""

    def __init__(self) -> None:
        """Start empty; the first refresh happens when the server starts."""
        self.lock = threading.Lock()
        self.data = {'available': False, 'message': '正在读取 Readhub', 'updated': None}
        self.wait = REFRESH

    def poll(self) -> None:
        """Store topics, or retain the previous list with an explicit notice."""
        try:
            rows = fetch_topics()
            with self.lock:
                self.data = {'available': True, 'updated': time.time(), 'topics': rows}
            self.wait = REFRESH
        except urllib.error.HTTPError as exc:
            hint = exc.headers.get('Retry-After') if exc.headers else None
            try:
                self.wait = min(int(hint), 3600) if hint else 120
            except ValueError:
                self.wait = 120
            self._fail()
        except (OSError, ValueError, KeyError, TypeError):
            self.wait = 120
            self._fail()

    def _fail(self) -> None:
        """Downgrade to a stale or unavailable state without inventing rows."""
        with self.lock:
            if self.data.get('available'):
                self.data['error'] = 'Readhub 暂时不可达，显示上次内容'
            else:
                self.data = {'available': False, 'message': 'Readhub 暂时不可达',
                             'updated': time.time()}

    def snapshot(self) -> dict:
        """Return a detached copy flagged when older than an hour."""
        with self.lock:
            data = copy.deepcopy(self.data)
        if data.get('available') and time.time() - data['updated'] > STALE:
            data['stale'] = True
        return data

    def run(self) -> None:
        """Refresh on a fixed cadence, backing off after failures."""
        while True:
            self.poll()
            time.sleep(self.wait)

    def start(self) -> None:
        """Start the background refresher."""
        threading.Thread(target=self.run, daemon=True, name='readhub-monitor').start()


readhub_monitor = ReadhubMonitor()
