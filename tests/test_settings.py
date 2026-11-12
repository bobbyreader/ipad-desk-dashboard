"""Tests for configuration loading, env overrides and secret redaction."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import settings


class SettingsTests(unittest.TestCase):
    def test_default_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = settings.load_settings(Path(tmp) / 'missing.json')
        self.assertTrue(cfg['features']['host'])
        self.assertTrue(cfg['features']['aihot'])
        self.assertTrue(cfg['features']['readhub'])
        self.assertTrue(cfg['features']['radio'])
        self.assertTrue(cfg['features']['music_search'])
        self.assertFalse(cfg['features']['docker'])
        self.assertFalse(cfg['features']['router'])
        self.assertFalse(cfg['features']['proxy'])
        self.assertFalse(cfg['features']['library'])
        self.assertFalse(cfg['features']['links'])

    def test_file_and_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps({
                'features': {'docker': True, 'links': True},
                'site': {'links': [{'title': 'NAS', 'desc': 'DSM', 'url': 'https://nas.local'}]},
                'library': {'url': 'http://10.0.0.5:4533', 'user': 'u1', 'password': 'secret-pw'},
                'router': {'ssh_host': 'root@10.0.0.1'},
            }), encoding='utf-8')
            with patch.dict(os.environ, {'DASHBOARD_PORT': '9900', 'DASHBOARD_FEATURE_RADIO': 'false'}):
                cfg = settings.load_settings(path)
        self.assertEqual(cfg['server']['port'], 9900)
        self.assertTrue(cfg['features']['docker'])
        self.assertFalse(cfg['features']['radio'])
        pub = settings.public_config(cfg)
        encoded = json.dumps(pub)
        self.assertNotIn('secret-pw', encoded)
        self.assertNotIn('root@10.0.0.1', encoded)
        self.assertEqual(pub['router']['source_label'], '10.0.0.1')
        self.assertEqual(pub['site']['links'][0]['domain'], 'nas.local')


if __name__ == '__main__':
    unittest.main()
