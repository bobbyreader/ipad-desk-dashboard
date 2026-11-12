"""Tests for asset allowlist, docker modes and snapshot endpoint."""
import subprocess
import unittest
from unittest.mock import patch
import server
from settings import SETTINGS


class AssetTests(unittest.TestCase):
    """Every script and stylesheet referenced by the page must be servable."""

    def test_referenced_assets_exist(self):
        import re
        from pathlib import Path
        html = (Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')
        referenced = re.findall(r'(?:src|href)="/([\w.-]+)"', html)
        self.assertTrue(referenced)
        for name in referenced:
            if name == 'config.js':
                continue
            self.assertIn(name, server.ASSETS, name)
            self.assertTrue((Path(__file__).resolve().parents[1] / name).is_file(), name)


class StatusTests(unittest.TestCase):
    """Exercise local/ssh docker modes and disabled boundaries."""

    def test_docker_disabled_by_default(self):
        with patch.dict(SETTINGS['features'], {'docker': False}):
            result = server.docker_status()
        self.assertFalse(result['available'])
        self.assertTrue(result.get('disabled'))

    @patch("server.subprocess.run")
    def test_local_docker_containers(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '{"Names":"navidrome","Status":"Up 2 hours","State":"running"}\n', '')
        with patch.dict(SETTINGS['features'], {'docker': True}), patch.dict(SETTINGS['docker'], {'mode': 'local'}):
            result = server.docker_status()
        self.assertTrue(result['available'])
        self.assertEqual(result['containers'][0]['name'], 'navidrome')
        self.assertEqual(run.call_args.args[0][0], 'docker')

    @patch("server.subprocess.run")
    def test_ssh_docker_containers(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '{"Names":"proxy","Status":"Up 1 hour","State":"running"}\n', '')
        with patch.dict(SETTINGS['features'], {'docker': True}), patch.dict(SETTINGS['docker'], {'mode': 'ssh', 'ssh_host': 'root@10.0.0.2'}):
            result = server.docker_status()
        self.assertTrue(result['available'])
        command = run.call_args.args[0]
        self.assertEqual(command[0], 'ssh')
        self.assertIn('root@10.0.0.2', command)
        self.assertIn('StrictHostKeyChecking=yes', command)

    @patch("server.subprocess.run", side_effect=subprocess.TimeoutExpired('docker', 4))
    def test_timeout(self, run):
        with patch.dict(SETTINGS['features'], {'docker': True}), patch.dict(SETTINGS['docker'], {'mode': 'local'}):
            self.assertFalse(server.docker_status()['available'])

    @patch("server.docker_status", return_value={"available": False})
    def test_host_snapshot(self, docker):
        host = server.snapshot()['host']
        self.assertGreater(host['disk_total_gb'], 0)
        self.assertGreaterEqual(host['disk_free_gb'], 0)
        if host['mem_percent'] is not None:
            self.assertGreaterEqual(host['mem_percent'], 0)
            self.assertLessEqual(host['mem_percent'], 100)
            self.assertGreater(host['mem_total_gb'], 0)


if __name__ == '__main__':
    unittest.main()
