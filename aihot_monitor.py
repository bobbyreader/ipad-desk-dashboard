"""Cached read-only AIHOT headlines; only the documented JSON API is contacted."""
import copy
import gzip
import json
import threading
import time
import urllib.error
import urllib.request

BASE = 'https://aihot.news'
UA = 'aihot-api/2.0.0'
REFRESH = 600
STALE = 3600
CATEGORIES = {'ai-models': '模型', 'ai-products': '产品', 'industry': '行业',
              'paper': '论文', 'tip': '教程', 'opinion': '观点'}


def fetch_json(path: str, etag: str | None = None) -> tuple[dict | None, str | None, int | None]:
    """Fetch an allowlisted AIHOT path, returning data, ETag and retry hint."""
    request = urllib.request.Request(BASE + path, headers={
        'User-Agent': UA, 'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
    if etag:
        request.add_header('If-None-Match', etag)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read()
            if response.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
            return json.loads(raw), response.headers.get('ETag'), None
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return None, etag, None
        hint = error.headers.get('Retry-After')
        try:
            retry = min(int(hint), 3600) if hint else None
        except ValueError:
            retry = None
        raise Retryable(error.code, retry) from error


class Retryable(Exception):
    """Carry a service status and optional Retry-After without leaking response bodies."""

    def __init__(self, status: int, retry: int | None) -> None:
        """Store the HTTP status and bounded retry delay."""
        super().__init__(f'AIHOT HTTP {status}')
        self.status = status
        self.retry = retry


def item(row: dict) -> dict:
    """Reduce API payloads to display fields and an allowlisted link."""
    link = (row.get('links') or {}).get('aihot', '')
    if not link.startswith(BASE + '/'):
        link = ''
    return {
        'title': str(row.get('title', ''))[:240], 'url': link,
        'source': str((row.get('source') or {}).get('name', ''))[:80],
        'category': CATEGORIES.get(row.get('category', ''), ''),
        'published': row.get('publishedAt') or row.get('latestAt') or '',
        'rank': row.get('rank'), 'sources': row.get('sourceCount'),
        'summary': str(row.get('summary', ''))[:400],
    }


class AihotMonitor:
    """Refresh two headline lists on one schedule and serve the last good copy."""

    def __init__(self) -> None:
        """Start empty; no request happens until the server starts."""
        self.lock = threading.Lock()
        self.data = {'available': False, 'message': '正在读取 AIHOT', 'updated': None}
        self.etags = {}
        self.wait = REFRESH

    def poll(self) -> None:
        """Fetch hot topics and daily selections; keep cached copy on partial failure."""
        error = None
        try:
            hot, hot_etag, _ = fetch_json('/api/v1/hot-topics', self.etags.get('hot'))
            self.etags['hot'] = hot_etag
            selected, sel_etag, _ = fetch_json(
                '/api/v1/items?mode=selected&window=24h&limit=15',
                self.etags.get('selected'))
            self.etags['selected'] = sel_etag
            with self.lock:
                previous = self.data if self.data.get('available') else {}
                rows = [item(row) for row in (hot or {}).get('items', [])][:10]
                daily = [item(row) for row in (selected or {}).get('items', [])][:15]
                self.data = {
                    'available': True, 'updated': time.time(),
                    'hot': rows or previous.get('hot', []),
                    'selected': daily or previous.get('selected', []),
                }
            self.wait = REFRESH
        except Retryable as exc:
            error = exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = exc
        if error is not None:
            with self.lock:
                if self.data.get('available'):
                    self.data['error'] = 'AIHOT 暂时不可达，显示上次内容'
                else:
                    self.data = {'available': False, 'message': 'AIHOT 暂时不可达',
                                 'updated': time.time()}
            self.wait = getattr(error, 'retry', None) or 120

    def snapshot(self) -> dict:
        """Return a detached copy with an explicit staleness flag."""
        with self.lock:
            data = copy.deepcopy(self.data)
        if data.get('available') and time.time() - data['updated'] > STALE:
            data['stale'] = True
        return data

    def run(self) -> None:
        """Refresh on a ten-minute cadence, backing off after failures."""
        while True:
            self.poll()
            time.sleep(self.wait)

    def start(self) -> None:
        """Start the background refresher."""
        threading.Thread(target=self.run, daemon=True, name='aihot-monitor').start()


aihot_monitor = AihotMonitor()
