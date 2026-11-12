"""Read-only Navidrome (Subsonic) client for the dashboard.

The browser never sees the Navidrome credentials: album lists, search and the
audio bytes all go through this process. Audio is passed through with Range
support so the iPad still does plain HTTP streaming against the host.
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request

from settings import SETTINGS

CLIENT = 'ipad-dashboard'
API_VERSION = '1.16.1'
TIMEOUT = 10
ALBUM_TTL = 300
DETAIL_TTL = 600
PLAYABLE = ('mp3', 'm4a', 'aac', 'flac', 'wav', 'ogg', 'opus', 'ape')


def _cfg() -> tuple[str, str, str]:
    lib = SETTINGS.get('library') or {}
    return (
        str(lib.get('url') or '').strip().rstrip('/'),
        str(lib.get('user') or '').strip(),
        str(lib.get('password') or ''),
    )


def _url(endpoint: str, base: str, user: str, password: str, **params) -> str:
    if not base or not user:
        raise ValueError('navidrome not configured')
    query = {'u': user, 'p': password, 'v': API_VERSION, 'c': CLIENT, 'f': 'json'}
    query.update({k: v for k, v in params.items() if v is not None})
    return '%s/rest/%s?%s' % (base, endpoint, urllib.parse.urlencode(query))


def call(endpoint: str, **params):
    base, user, password = _cfg()
    request = urllib.request.Request(
        _url(endpoint, base, user, password, **params),
        headers={'Accept': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read(4194304).decode('utf-8', 'replace'))
    body = payload.get('subsonic-response') or {}
    if body.get('status') != 'ok':
        raise IOError('navidrome: %s' % (body.get('error', {}).get('message') or 'unknown error'))
    return body


def album_row(raw: dict) -> dict:
    return {
        "id": str(raw.get('id') or ''),
        "name": str(raw.get('name') or raw.get('title') or '未命名专辑')[:80],
        "artist": str(raw.get('artist') or '')[:60],
        "songCount": int(raw.get('songCount') or 0),
        "duration": int(raw.get('duration') or 0),
        "hasCover": bool(raw.get('coverArt')),
        "coverId": str(raw.get('coverArt') or ''),
    }


def song_row(raw: dict) -> dict:
    suffix = str(raw.get('suffix') or '').lower()
    return {
        "id": str(raw.get('id') or ''),
        "title": str(raw.get('title') or '未命名')[:80],
        "artist": str(raw.get('artist') or '')[:60],
        "album": str(raw.get('album') or '')[:60],
        "track": int(raw.get('track') or 0),
        "duration": int(raw.get('duration') or 0),
        "suffix": suffix,
        "size": int(raw.get('size') or 0),
        "playable": suffix in PLAYABLE,
    }


class Library:
    """TTL cache around three Subsonic calls; every failure degrades to a message."""

    def __init__(self, fetch=call):
        self.fetch = fetch
        self.lock = threading.Lock()
        self.cache = {}

    def _cached(self, key, ttl, builder):
        with self.lock:
            hit = self.cache.get(key)
        if hit and time.time() - hit['at'] < ttl:
            return hit['value']
        value = builder()
        with self.lock:
            self.cache[key] = {"at": time.time(), "value": value}
        return value

    def albums(self, limit: int = 120) -> dict:
        def build():
            body = self.fetch('getAlbumList2', type='alphabeticalByName', size=max(1, min(limit, 400)))
            rows = ((body.get('albumList2') or {}).get('album')) or []
            return [album_row(row) for row in rows]

        try:
            items = self._cached('albums', ALBUM_TTL, build)
        except ValueError:
            return {"available": False, "albums": [], "message": "音乐库未配置（请在 config.json 填写 library）"}
        except Exception as error:  # noqa: BLE001 - dashboard must not crash
            return {"available": False, "albums": [], "message": "音乐库不可用（%s）" % type(error).__name__}
        return {"available": True, "albums": items}

    def album(self, album_id: str) -> dict:
        if not album_id or not album_id.replace('-', '').isalnum():
            return {"available": False, "songs": [], "message": "专辑 id 无效"}

        def build():
            body = self.fetch('getAlbum', id=album_id)
            album = body.get('album') or {}
            songs = [song_row(row) for row in (album.get('song') or [])]
            songs.sort(key=lambda s: (s['track'] or 999, s['title']))
            return {"album": album_row(album), "songs": songs}

        try:
            data = self._cached('album:' + album_id, DETAIL_TTL, build)
        except ValueError:
            return {"available": False, "songs": [], "message": "音乐库未配置"}
        except Exception as error:  # noqa: BLE001
            return {"available": False, "songs": [], "message": "取专辑失败（%s）" % type(error).__name__}
        return {"available": True, "album": data['album'], "songs": data['songs']}

    def search(self, query: str) -> dict:
        text = (query or '').strip()[:40]
        if not text:
            return {"available": False, "songs": [], "message": "请输入关键字"}
        try:
            body = self.fetch('search3', query=text, songCount=40, albumCount=0, artistCount=0)
        except ValueError:
            return {"available": False, "songs": [], "message": "音乐库未配置"}
        except Exception as error:  # noqa: BLE001
            return {"available": False, "songs": [], "message": "搜索失败（%s）" % type(error).__name__}
        rows = ((body.get('searchResult3') or {}).get('song')) or []
        return {"available": True, "songs": [song_row(row) for row in rows]}

    def cover(self, cover_id: str):
        """Fetch a bounded thumbnail from Navidrome, never an arbitrary URL."""
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', cover_id):
            raise ValueError('bad cover id')
        base, user, password = _cfg()
        with urllib.request.urlopen(_url('getCoverArt', base, user, password, id=cover_id, size=96), timeout=TIMEOUT) as response:
            mime = response.headers.get_content_type()
            data = response.read(1048577)
        if mime not in ('image/jpeg', 'image/png', 'image/webp') or len(data) > 1048576:
            raise ValueError('invalid cover')
        return mime, data

    def open_stream(self, song_id: str, range_header: str = None):
        """Return a file-like response so the caller can pipe bytes."""
        if not song_id or not song_id.replace('-', '').isalnum():
            raise ValueError('bad song id')
        base, user, password = _cfg()
        request = urllib.request.Request(_url('stream', base, user, password, id=song_id, format='mp3', maxBitRate=320))
        if range_header:
            request.add_header('Range', range_header)
        return urllib.request.urlopen(request, timeout=30)


library = Library()
