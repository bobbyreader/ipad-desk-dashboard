"""Radio catalogue: validation, ICY parsing, health probes and title caching."""
import unittest
from unittest.mock import patch
import radio_monitor as radio


class CatalogueTests(unittest.TestCase):
    """A typo in stations.json must not break the player or reach private hosts."""

    def test_rejects_bad_rows(self):
        rows = radio.normalise([
            {"id": "ok1", "name": "好台", "url": "https://example.com/a.mp3"},
            {"id": "bad id!", "name": "非法 id", "url": "https://example.com/b.mp3"},
            {"id": "ok1", "name": "重复", "url": "https://example.com/c.mp3"},
            {"id": "lan", "name": "内网", "url": "http://192.168.2.10:8080/a.mp3"},
            {"id": "loc", "name": "本机", "url": "http://localhost:9000/a.mp3"},
            {"id": "ftp", "name": "协议", "url": "ftp://example.com/a.mp3"},
            {"id": "cred", "name": "带账号", "url": "https://user:pass@example.com/a.mp3"},
            {"id": "noname", "name": "", "url": "https://example.com/d.mp3"},
        ])
        self.assertEqual([row["id"] for row in rows], ["ok1"])
        self.assertEqual(rows[0]["codec"], "mp3")

    def test_codec_labels(self):
        self.assertEqual(radio.codec_of("https://a/b/index.m3u8"), "hls")
        self.assertEqual(radio.codec_of("https://a/b/192k.aac"), "aac")
        self.assertEqual(radio.codec_of("http://a/b/64k.mp3"), "mp3")

    def test_shipped_stations_are_valid(self):
        """The file we ship must survive our own validation."""
        stations = radio.load_stations()
        self.assertGreaterEqual(len(stations), 8)
        ids = [s["id"] for s in stations]
        self.assertEqual(len(ids), len(set(ids)))
        for station in stations:
            self.assertTrue(radio.valid_url(station["url"]), station["url"])
            self.assertIn(station["codec"], ("mp3", "aac", "hls"))
            self.assertTrue(station["group"])

    def test_missing_file_falls_back(self):
        """A deleted stations.json must not leave the panel with an empty list."""
        stations = radio.load_stations(path=radio.Path('/nonexistent/stations.json'))
        self.assertTrue(stations)


class IcyTests(unittest.TestCase):
    """ICY metadata is invisible to <audio>, so parsing has to be exact."""

    def block(self, meta: str, metaint: int = 16) -> bytes:
        payload = meta.encode('utf-8')
        padded = payload + b'\x00' * ((-len(payload)) % 16)
        length = len(padded) // 16
        return b'\xff' * metaint + bytes([length]) + padded

    def test_extracts_title(self):
        block = self.block("StreamTitle='周杰伦 - 晴天';")
        self.assertEqual(radio.parse_icy_title(block, 16), '周杰伦 - 晴天')

    def test_empty_title_and_garbage(self):
        self.assertEqual(radio.parse_icy_title(self.block("StreamTitle='';"), 16), '')
        self.assertEqual(radio.parse_icy_title(b'\x00' * 8, 16), '')
        self.assertEqual(radio.parse_icy_title(self.block('no title here'), 16), '')

    def test_zero_length_block(self):
        self.assertEqual(radio.parse_icy_title(b'\xff' * 20 + b'\x00', 20), '')


class MonitorTests(unittest.TestCase):
    """Health and now-playing must be honest when the network misbehaves."""

    def station(self):
        return [{"id": "s1", "name": "测试台", "group": "音乐",
                 "url": "https://example.com/a.mp3", "codec": "mp3"}]

    def test_probe_failure_is_not_success(self):
        monitor = radio.RadioMonitor(
            station_loader=lambda: self.station(),
            prober=lambda url: {"status": "fail", "at": 1},
            title_fetcher=lambda url: '')
        monitor.check_all()
        snapshot = monitor.snapshot()
        self.assertEqual(snapshot['stations'][0]['health']['status'], 'fail')

    def test_title_is_cached(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return '曲目 A'

        monitor = radio.RadioMonitor(station_loader=lambda: self.station(),
                                     prober=lambda url: {"status": "ok", "at": 1},
                                     title_fetcher=fetch)
        monitor.check_all()
        first = monitor.now('s1')
        second = monitor.now('s1')
        self.assertEqual(first['title'], '曲目 A')
        self.assertEqual(second['title'], '曲目 A')
        self.assertEqual(len(calls), 1)

    def test_unknown_station(self):
        monitor = radio.RadioMonitor(station_loader=lambda: self.station(),
                                     prober=lambda url: {"status": "ok", "at": 1},
                                     title_fetcher=lambda url: '')
        monitor.check_all()
        self.assertEqual(monitor.now('nope')['title'], '')

    @patch('radio_monitor.urllib.request.urlopen', side_effect=OSError('offline'))
    def test_probe_exception(self, _):
        self.assertEqual(radio.probe('https://example.com/a.mp3')['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
