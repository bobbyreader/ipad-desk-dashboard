"""Counter correctness, privacy boundaries and failure recovery for proxy telemetry."""
import json
import subprocess
import unittest
from unittest.mock import patch
from proxy_monitor import ProxyMonitor
from settings import SETTINGS


class ProxyTests(unittest.TestCase):
    """Check meaningful telemetry behavior without contacting the actual proxy."""

    def setUp(self):
        self.monitor = ProxyMonitor()
        if self.monitor.reader:
            self.monitor.reader.close()
        self.monitor.reader = None

    def raw(self, download=100, upload=50, count=10):
        return {'download': download, 'upload': upload, 'connections': [
            {'id': 'secret-id', 'ip': '8.8.8.8', 'geo': ['US'], 'bytes': count, 'direct': False},
            {'id': 'private', 'ip': '192.168.1.10', 'geo': [], 'bytes': 0, 'direct': True},
        ]}

    def test_rates_and_privacy(self):
        first = self.monitor.ingest(self.raw(), 10)
        self.assertIsNone(first['download_rate'])
        second = self.monitor.ingest(self.raw(400, 110, 40), 13)
        self.assertEqual(second['download_rate'], 100)
        self.assertEqual(second['upload_rate'], 20)
        self.assertEqual(second['countries'][0]['bytes_per_sec'], 10)
        self.assertEqual(second['unknown'], 1)
        self.assertEqual(second['direct'], 1)
        encoded = json.dumps(second)
        self.assertNotIn('8.8.8.8', encoded)
        self.assertNotIn('secret-id', encoded)

    def test_reset_and_sampling_gap(self):
        self.monitor.ingest(self.raw(400, 110), 10)
        self.assertIsNone(self.monitor.ingest(self.raw(20, 10), 13)['download_rate'])
        self.assertIsNone(self.monitor.ingest(self.raw(400, 110), 50)['download_rate'])

    def test_unknown_and_empty(self):
        self.assertEqual(self.monitor.country({'ip': 'invalid', 'geo': ['US']}), '')
        self.assertEqual(self.monitor.country({'ip': '8.8.8.8', 'geo': ['ZZ']}), '')
        empty = self.monitor.ingest({'download': 0, 'upload': 0, 'connections': []}, 10)
        self.assertEqual(empty['countries'], [])
        self.assertEqual(empty['connections'], 0)

    def test_local_mode_collect(self):
        with patch.dict(SETTINGS['proxy'], {'mode': 'local', 'mihomo_config': '/tmp/c.yaml', 'mihomo_api': 'http://127.0.0.1:9090/connections'}):
            with patch('proxy_monitor.remote_proxy.collect', return_value=self.raw()) as col:
                self.monitor.poll()
        col.assert_called_once()
        self.assertTrue(self.monitor.snapshot()['available'])

    def test_unconfigured_ssh_host(self):
        with patch.dict(SETTINGS['proxy'], {'mode': 'ssh', 'ssh_host': ''}):
            self.monitor.poll()
        self.assertFalse(self.monitor.snapshot()['available'])
        self.assertIn('未配置', self.monitor.snapshot()['message'])

    @patch('proxy_monitor.subprocess.run', side_effect=subprocess.TimeoutExpired('ssh', 7))
    def test_failure_and_recovery(self, run):
        self.monitor.ingest(self.raw(), 10)
        with patch.dict(SETTINGS['proxy'], {'ssh_host': 'root@192.168.1.2'}):
            self.monitor.poll()
        self.assertFalse(self.monitor.snapshot()['available'])
        self.assertEqual(self.monitor.history, [])
        self.assertIsNone(self.monitor.ingest(self.raw(400, 110), 16)['download_rate'])

    def test_stalled_sampler(self):
        self.monitor.data = {'available': True, 'updated': 1}
        self.assertFalse(self.monitor.snapshot()['available'])


if __name__ == '__main__':
    unittest.main()
