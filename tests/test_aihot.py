"""AIHOT caching, ETag reuse, backoff and link sanitization."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from aihot_monitor import AihotMonitor, Retryable, item


class FakeResponse:
    """Minimal urlopen context manager with JSON or gzip content."""

    def __init__(self, body: bytes, etag: str = '"v1"', encoding: str | None = None, status: int = 200):
        """Store body bytes and headers used by fetch_json."""
        self.body = body
        self.headers = {'ETag': etag, 'Content-Encoding': encoding}
        self.status = status

    def read(self) -> bytes:
        """Return the raw body."""
        return self.body

    def __enter__(self):
        """Enter the response context."""
        return self

    def __exit__(self, *exc):
        """Exit the response context without suppressing errors."""
        return False


def payload(rows, field='items'):
    """Build a JSON API payload."""
    return json.dumps({field: rows}).encode()


class ItemTests(unittest.TestCase):
    """Display reduction must not trust arbitrary links."""


    def track(self, error):
        """Close HTTPError streams so tests do not leak file handles."""
        self.addCleanup(error.close)
        return error

    def test_link_allowlist(self):
        """Only https AIHOT item links survive sanitization."""
        row = {'title': 'T', 'links': {'aihot': 'javascript:alert(1)'}, 'source': {'name': 'S'}}
        self.assertEqual(item(row)['url'], '')
        row['links']['aihot'] = 'https://evil.example/x'
        self.assertEqual(item(row)['url'], '')
        row['links']['aihot'] = 'https://aihot.news/items/x'
        self.assertEqual(item(row)['url'], 'https://aihot.news/items/x')

    def test_field_truncation(self):
        """Long third-party strings cannot grow the local payload without bound."""
        row = {'title': 'x' * 500, 'summary': 'y' * 2000, 'source': {'name': 'z' * 300}}
        result = item(row)
        self.assertEqual(len(result['title']), 240)
        self.assertEqual(len(result['summary']), 400)
        self.assertEqual(len(result['source']), 80)


class MonitorTests(unittest.TestCase):
    """Verify refresh behavior, cache retention and failure states."""

    def setUp(self):
        """Use a fresh monitor for each case."""
        self.monitor = AihotMonitor()

    def test_success_and_etag(self):
        """Two endpoints are fetched and their ETags remembered."""
        responses = [FakeResponse(payload([{'id': 'a', 'title': 'Hot'}])),
                     FakeResponse(payload([{'id': 'b', 'title': 'Daily'}]))]
        with patch('aihot_monitor.urllib.request.urlopen', side_effect=responses) as open_url:
            self.monitor.poll()
        data = self.monitor.snapshot()
        self.assertTrue(data['available'])
        self.assertEqual(data['hot'][0]['title'], 'Hot')
        self.assertEqual(data['selected'][0]['title'], 'Daily')
        self.assertEqual(self.monitor.etags['hot'], '"v1"')
        request = open_url.call_args_list[1].args[0]
        self.assertTrue(request.full_url.startswith('https://aihot.news/api/v1/items'))
        self.assertEqual(request.get_header('User-agent'), 'aihot-api/2.0.0')

    def test_not_modified_keeps_content(self):
        """A 304 refresh must not erase previously published headlines."""
        with patch('aihot_monitor.urllib.request.urlopen',
                   side_effect=[FakeResponse(payload([{'title': 'Hot'}])),
                                FakeResponse(payload([{'title': 'Daily'}]))]):
            self.monitor.poll()
        not_modified = urllib.error.HTTPError('u', 304, 'Not Modified', {}, io.BytesIO(b''))
        with patch('aihot_monitor.urllib.request.urlopen', side_effect=not_modified):
            self.monitor.poll()
        data = self.monitor.snapshot()
        self.assertTrue(data['available'])
        self.assertEqual(data['hot'][0]['title'], 'Hot')

    def test_gzip(self):
        """Compressed responses are decoded."""
        import gzip
        body = gzip.compress(payload([{'title': 'Zipped'}]))
        with patch('aihot_monitor.urllib.request.urlopen',
                   side_effect=[FakeResponse(body, encoding='gzip'), FakeResponse(payload([]))]):
            self.monitor.poll()
        self.assertEqual(self.monitor.snapshot()['hot'][0]['title'], 'Zipped')

    def test_rate_limit_backoff_and_cache(self):
        """429 sets a bounded Retry-After and keeps the last good copy with a notice."""
        with patch('aihot_monitor.urllib.request.urlopen',
                   side_effect=[FakeResponse(payload([{'title': 'Cached'}])), FakeResponse(payload([]))]):
            self.monitor.poll()
        error = urllib.error.HTTPError('u', 429, 'Too Many', {'Retry-After': '90'}, io.BytesIO(b''))
        with patch('aihot_monitor.urllib.request.urlopen', side_effect=error):
            self.monitor.poll()
        data = self.monitor.snapshot()
        self.assertTrue(data['available'])
        self.assertEqual(data['hot'][0]['title'], 'Cached')
        self.assertIn('不可达', data['error'])
        self.assertEqual(self.monitor.wait, 90)

    def test_first_failure_is_unavailable(self):
        """Never fabricate placeholders when there is no cached content."""
        with patch('aihot_monitor.urllib.request.urlopen', side_effect=OSError('offline')):
            self.monitor.poll()
        data = self.monitor.snapshot()
        self.assertFalse(data['available'])
        self.assertIn('不可达', data['message'])
        self.assertEqual(self.monitor.wait, 120)

    def test_stale_flag(self):
        """Old cached content is flagged instead of presented as fresh."""
        self.monitor.data = {'available': True, 'updated': 1, 'hot': [], 'selected': []}
        self.assertTrue(self.monitor.snapshot()['stale'])

    def test_retryable_is_raised_for_http_errors(self):
        """HTTP errors surface as a retryable status rather than parsed content."""
        error = urllib.error.HTTPError('u', 503, 'Down', {}, io.BytesIO(b'<html>'))
        self.addCleanup(error.close)
        with patch('aihot_monitor.urllib.request.urlopen', side_effect=error):
            with self.assertRaises(Retryable) as caught:
                from aihot_monitor import fetch_json
                fetch_json('/api/v1/hot-topics')
        self.assertEqual(caught.exception.status, 503)


if __name__ == '__main__':
    unittest.main()
