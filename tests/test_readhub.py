"""Readhub topic mapping, link validation and cache behavior."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from readhub_monitor import ReadhubMonitor, fetch_topics, topic


def row(uid='abc123', title='话题', sites=3):
    """Build one API topic shaped like the real payload."""
    return {'uid': uid, 'title': title, 'summary': '摘要', 'siteCount': sites,
            'siteNameDisplay': '某媒体', 'publishDate': '2026-11-11T10:00:00.000Z'}


class FakeResponse:
    """Minimal response context manager for mocked urlopen."""

    def __init__(self, body: bytes, encoding: str | None = None):
        """Keep raw bytes and a small header map."""
        self.body = body
        self.headers = {'Content-Encoding': encoding}

    def read(self) -> bytes:
        """Return the body."""
        return self.body

    def __enter__(self):
        """Enter context."""
        return self

    def __exit__(self, *exc):
        """Leave context."""
        return False


class TopicTests(unittest.TestCase):
    """Only well-formed identifiers become links."""


    def test_uid_validation(self):
        """Path traversal and empty identifiers are rejected, not escaped."""
        self.assertIsNone(topic(row(uid='../admin')))
        self.assertIsNone(topic(row(uid='')))
        self.assertIsNone(topic(row(uid='a b')))
        result = topic(row(uid='8xy7pPlRj6s'))
        self.assertEqual(result['url'], 'https://readhub.cn/topic/8xy7pPlRj6s')

    def test_sites_and_truncation(self):
        """Non-integer media counts are omitted; long text is bounded."""
        self.assertIsNone(topic(row(sites='3'))['sites'])
        self.assertIsNone(topic(row(sites=-1))['sites'])
        long_row = row(title='x' * 500)
        long_row['summary'] = 'y' * 2000
        result = topic(long_row)
        self.assertEqual(len(result['title']), 240)
        self.assertEqual(len(result['summary']), 400)


class FetchTests(unittest.TestCase):
    """Payload validation and compression handling."""

    def test_payload_and_limit(self):
        """Valid items are capped at ten and malformed rows skipped."""
        rows = [row(uid='ok%d' % i) for i in range(12)] + [{'title': 'no uid'}]
        body = json.dumps({'data': {'items': rows}}).encode()
        with patch('readhub_monitor.urllib.request.urlopen', return_value=FakeResponse(body)):
            result = fetch_topics()
        self.assertEqual(len(result), 10)
        self.assertTrue(all(item['url'].startswith('https://readhub.cn/topic/ok') for item in result))

    def test_unexpected_shape_raises(self):
        """A changed payload shape must not masquerade as an empty list."""
        body = json.dumps({'data': {'items': None}}).encode()
        with patch('readhub_monitor.urllib.request.urlopen', return_value=FakeResponse(body)):
            with self.assertRaises(ValueError):
                fetch_topics()

    def test_gzip(self):
        """Compressed responses are decoded."""
        import gzip
        body = gzip.compress(json.dumps({'data': {'items': [row()]}}).encode())
        with patch('readhub_monitor.urllib.request.urlopen', return_value=FakeResponse(body, 'gzip')):
            self.assertEqual(len(fetch_topics()), 1)


class MonitorTests(unittest.TestCase):
    """Caching and failure states."""

    def setUp(self):
        """Create a fresh monitor."""
        self.monitor = ReadhubMonitor()

    def test_success_then_failure_keeps_cache(self):
        """Cached topics survive a failed refresh and are marked as such."""
        body = json.dumps({'data': {'items': [row(title='Cached')]}}).encode()
        with patch('readhub_monitor.urllib.request.urlopen', return_value=FakeResponse(body)):
            self.monitor.poll()
        with patch('readhub_monitor.urllib.request.urlopen', side_effect=OSError('offline')):
            self.monitor.poll()
        data = self.monitor.snapshot()
        self.assertTrue(data['available'])
        self.assertEqual(data['topics'][0]['title'], 'Cached')
        self.assertIn('不可达', data['error'])
        self.assertEqual(self.monitor.wait, 120)

    def test_rate_limit(self):
        """429 honours a bounded Retry-After."""
        error = urllib.error.HTTPError('u', 429, 'slow', {'Retry-After': '30'}, io.BytesIO(b''))
        self.addCleanup(error.close)
        with patch('readhub_monitor.urllib.request.urlopen', side_effect=error):
            self.monitor.poll()
        self.assertFalse(self.monitor.snapshot()['available'])
        self.assertEqual(self.monitor.wait, 30)

    def test_stale(self):
        """Old data is flagged rather than presented as current."""
        self.monitor.data = {'available': True, 'updated': 1, 'topics': []}
        self.assertTrue(self.monitor.snapshot()['stale'])


if __name__ == '__main__':
    unittest.main()
