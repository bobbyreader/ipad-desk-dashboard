"""Navidrome bridge: normalisation, caching, failure messages, range passthrough."""
from unittest.mock import patch
import urllib.parse
import time
import unittest

import music_library as ml
from settings import SETTINGS


def song(sid='s1', title='夜曲', suffix='wav', track=1, **extra):
    row = {"id": sid, "title": title, "artist": "示例歌手", "album": "示例专辑",
           "track": track, "duration": 228, "suffix": suffix, "size": 40356185}
    row.update(extra)
    return row


class FakeFetch:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def __call__(self, endpoint, **params):
        self.calls.append((endpoint, params))
        value = self.mapping.get(endpoint)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise AssertionError('unexpected endpoint ' + endpoint)
        return value


ALBUM = {"id": "a1", "name": "示例专辑", "artist": "示例歌手", "songCount": 2,
         "duration": 600, "coverArt": "al-1"}


class AlbumTests(unittest.TestCase):
    def test_lists_and_normalises(self):
        fetch = FakeFetch({'getAlbumList2': {"albumList2": {"album": [ALBUM]}}})
        library = ml.Library(fetch=fetch)
        result = library.albums()
        self.assertTrue(result['available'])
        self.assertEqual(result['albums'][0]['name'], '示例专辑')
        self.assertEqual(result['albums'][0]['songCount'], 2)
        self.assertTrue(result['albums'][0]['hasCover'])

    def test_cache_avoids_second_call(self):
        fetch = FakeFetch({'getAlbumList2': {"albumList2": {"album": [ALBUM]}}})
        library = ml.Library(fetch=fetch)
        library.albums()
        library.albums()
        self.assertEqual(len(fetch.calls), 1)

    def test_upstream_failure_degrades(self):
        fetch = FakeFetch({'getAlbumList2': OSError('down')})
        result = ml.Library(fetch=fetch).albums()
        self.assertFalse(result['available'])
        self.assertEqual(result['albums'], [])
        self.assertIn('不可用', result['message'])

    def test_unconfigured_degrades(self):
        with patch.dict(SETTINGS['library'], {'url': '', 'user': ''}):
            result = ml.Library().albums()
        self.assertFalse(result['available'])
        self.assertIn('未配置', result['message'])

    def test_cache_expires(self):
        fetch = FakeFetch({'getAlbumList2': {"albumList2": {"album": [ALBUM]}}})
        library = ml.Library(fetch=fetch)
        library.albums()
        with library.lock:
            library.cache['albums']['at'] = time.time() - ml.ALBUM_TTL - 1
        library.albums()
        self.assertEqual(len(fetch.calls), 2)


class DetailTests(unittest.TestCase):
    def test_songs_sorted_by_track_number(self):
        body = {"album": dict(ALBUM, song=[song('s2', '第二首', track=2), song('s1', track=1)])}
        library = ml.Library(fetch=FakeFetch({'getAlbum': body}))
        result = library.album('a1')
        self.assertTrue(result['available'])
        self.assertEqual([s['title'] for s in result['songs']], ['夜曲', '第二首'])

    def test_ape_is_playable_through_transcoding(self):
        body = {"album": dict(ALBUM, song=[song('s3', '第三首', suffix='ape')])}
        result = ml.Library(fetch=FakeFetch({'getAlbum': body})).album('a1')
        self.assertTrue(result['songs'][0]['playable'])
        self.assertEqual(result['songs'][0]['suffix'], 'ape')

    def test_rejects_non_id_paths(self):
        result = ml.Library(fetch=FakeFetch({})).album('../../etc/passwd')
        self.assertFalse(result['available'])
        self.assertEqual(result['songs'], [])

    def test_album_failure_message(self):
        result = ml.Library(fetch=FakeFetch({'getAlbum': IOError('boom')})).album('abc123')
        self.assertFalse(result['available'])
        self.assertIn('取专辑失败', result['message'])


class SearchTests(unittest.TestCase):
    def test_empty_query_never_hits_upstream(self):
        fetch = FakeFetch({})
        result = ml.Library(fetch=fetch).search('   ')
        self.assertFalse(result['available'])
        self.assertEqual(fetch.calls, [])

    def test_search_returns_songs(self):
        body = {"searchResult3": {"song": [song()]}}
        result = ml.Library(fetch=FakeFetch({'search3': body})).search('夜曲')
        self.assertTrue(result['available'])
        self.assertEqual(result['songs'][0]['title'], '夜曲')

    def test_search_failure_message(self):
        result = ml.Library(fetch=FakeFetch({'search3': OSError('x')})).search('夜曲')
        self.assertFalse(result['available'])
        self.assertIn('搜索失败', result['message'])


class StreamTests(unittest.TestCase):
    def test_rejects_bad_id_before_network(self):
        with self.assertRaises(ValueError):
            ml.Library(fetch=FakeFetch({})).open_stream('id with spaces')

    def test_transcoding_request_preserves_range(self):
        with patch.dict(SETTINGS['library'], {'url': 'http://192.168.1.50:4533', 'user': 'reader', 'password': 'secret'}):
            with patch.object(ml.urllib.request, 'urlopen') as opened:
                ml.Library().open_stream('abc123', 'bytes=0-1023')
        request = opened.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(query['format'], ['mp3'])
        self.assertEqual(query['maxBitRate'], ['320'])
        self.assertEqual(request.get_header('Range'), 'bytes=0-1023')

    def test_cover_rejects_paths_before_network(self):
        with patch.object(ml.urllib.request, 'urlopen') as opened:
            with self.assertRaises(ValueError):
                ml.Library().cover('../../etc/passwd')
        opened.assert_not_called()

    def test_cover_id_is_preserved(self):
        self.assertEqual(ml.album_row(ALBUM)['coverId'], 'al-1')

    def test_playable_list_covers_ios_codecs(self):
        for suffix in ('mp3', 'm4a', 'flac', 'wav', 'aac'):
            self.assertIn(suffix, ml.PLAYABLE)
        self.assertIn('ape', ml.PLAYABLE)
        self.assertFalse(ml.song_row(song(suffix='rar'))['playable'])


if __name__ == '__main__':
    unittest.main()
