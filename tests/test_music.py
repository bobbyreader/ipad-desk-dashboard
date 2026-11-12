"""Online music search: query hygiene, upstream fallback, link resolution."""
import time
import unittest

import music_search as ms

QQ_ROW = {"song_title": "晴天", "singer_name": "周杰伦", "song_mid": "0039MnYb0qxYhV", "pay": "免费"}
NETEASE_ROW = {"name": "晴天", "artist": "周杰伦", "album": "叶惠美",
               "url": "https://api.qijieya.cn/meting/?server=netease&type=url&id=210049"}


class FakeFetch:
    """Records calls and replays canned upstream bodies per URL fragment."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        for fragment, value in self.mapping.items():
            if fragment in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError('unexpected upstream call: ' + url)


class QueryTest(unittest.TestCase):
    def test_tidies_spacing(self):
        self.assertEqual(ms.clean_query('  周杰伦   晴天 '), '周杰伦 晴天')

    def test_rejects_empty_and_overlong(self):
        self.assertEqual(ms.clean_query(''), '')
        self.assertEqual(ms.clean_query('   '), '')
        self.assertEqual(ms.clean_query('a' * 41), '')
        self.assertEqual(ms.clean_query('hello\nworld; rm -rf'), '')

    def test_accepts_chinese_and_punctuation(self):
        self.assertEqual(ms.clean_query("Let it be (Remastered)"), 'Let it be (Remastered)')


class SearchTest(unittest.TestCase):
    def test_qq_is_the_primary_source(self):
        fetch = FakeFetch({'tang.api': [QQ_ROW]})
        service = ms.MusicSearch(fetch=fetch)
        result = service.search('晴天')
        self.assertTrue(result['available'])
        self.assertEqual(result['source'], 'qq')
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['items'][0]['name'], '晴天')
        self.assertEqual(result['items'][0]['artist'], '周杰伦')
        self.assertEqual(len(fetch.calls), 1)

    def test_falls_back_to_netease(self):
        fetch = FakeFetch({'tang.api': [], 'meting': [NETEASE_ROW]})
        service = ms.MusicSearch(fetch=fetch)
        result = service.search('晴天')
        self.assertEqual(result['source'], 'netease')
        self.assertEqual(result['items'][0]['id'].split('-')[0], 'netease')

    def test_reports_both_upstreams_failing(self):
        fetch = FakeFetch({'tang.api': OSError('boom'), 'meting': OSError('boom')})
        service = ms.MusicSearch(fetch=fetch)
        result = service.search('晴天')
        self.assertFalse(result['available'])
        self.assertEqual(result['items'], [])
        self.assertIn('不可用', result['message'])

    def test_invalid_query_never_hits_the_network(self):
        fetch = FakeFetch({})
        service = ms.MusicSearch(fetch=fetch)
        result = service.search('x' * 90)
        self.assertFalse(result['available'])
        self.assertEqual(fetch.calls, [])

    def test_cache_keeps_the_source(self):
        fetch = FakeFetch({'tang.api': [QQ_ROW]})
        service = ms.MusicSearch(fetch=fetch)
        first = service.search('晴天')
        second = service.search('晴天')
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertEqual(second['source'], 'qq')
        self.assertEqual([i['id'] for i in first['items']], [i['id'] for i in second['items']])
        self.assertEqual(len(fetch.calls), 1)

    def test_duplicate_mids_collapse(self):
        fetch = FakeFetch({'tang.api': [QQ_ROW, dict(QQ_ROW, song_title='晴天 (Live)')]})
        service = ms.MusicSearch(fetch=fetch)
        self.assertEqual(len(service.search('晴天')['items']), 1)


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.fetch = FakeFetch({'&mid=': {
            'song_name': '晴天',
            'song_play_url': 'http://isure6.stream.qqmusic.qq.com/C400.m4a?vkey=1',
            'song_play_url_sq': 'http://isure6.stream.qqmusic.qq.com/C400.flac?vkey=1',
        }})
        self.service = ms.MusicSearch(fetch=self.fetch)

    def _qq_track(self):
        with self.service.lock:
            self.service.tracks['qq-x-0'] = {"at": time.time(), "query": '晴天',
                                             "source": 'qq', "ref": '0039MnYb0qxYhV'}
        return 'qq-x-0'

    def test_resolves_a_qq_link(self):
        result = self.service.resolve(self._qq_track())
        self.assertTrue(result['available'])
        self.assertIn('qqmusic.qq.com', result['url'])

    def test_caches_the_resolved_link(self):
        uid = self._qq_track()
        self.service.resolve(uid)
        again = self.service.resolve(uid)
        self.assertTrue(again['cached'])
        self.assertEqual(len(self.fetch.calls), 1)

    def test_unknown_id_asks_for_a_new_search(self):
        result = self.service.resolve('qq-nope-9')
        self.assertFalse(result['available'])
        self.assertIn('重新搜索', result['message'])

    def test_rejects_foreign_hosts(self):
        self.service.tracks['qq-bad-1'] = {"at": time.time(), "query": '晴天',
                                           "source": 'qq', "ref": 'midbad'}
        self.fetch.mapping['&mid='] = {'song_play_url': 'http://evil.example.com/a.mp3'}
        result = self.service.resolve('qq-bad-1')
        self.assertFalse(result['available'])

    def test_host_allowlist(self):
        self.assertTrue(ms.host_allowed('http://isure6.stream.qqmusic.qq.com/a.m4a'))
        self.assertTrue(ms.host_allowed('https://m701.music.126.net/a.mp3'))
        self.assertFalse(ms.host_allowed('http://qqmusic.qq.com.evil.tld/a.m4a'))
        self.assertFalse(ms.host_allowed('file:///etc/passwd'))


if __name__ == '__main__':
    unittest.main()
