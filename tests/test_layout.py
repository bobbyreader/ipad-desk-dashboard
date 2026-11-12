"""Layout contract: the page markup must keep every id the scripts touch."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LayoutTests(unittest.TestCase):
    """Guard the layout and absence of personal hardcoded endpoints."""

    def setUp(self):
        self.html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.app = (ROOT / 'app.js').read_text(encoding='utf-8')

    def test_view_switch(self):
        for name in ('view-home', 'view-invest', 'invest-view', 'invest-links'):
            self.assertIn('id="%s"' % name, self.html, name)

    def test_no_personal_hardcoded_endpoints(self):
        combined = self.html + self.app
        for forbidden in ('gafata.eu.cc', '192.168.2.', 'CT 103', '1q2w3e4r'):
            self.assertNotIn(forbidden, combined)

    def test_app_ids_exist(self):
        ids = set(re.findall(r"el\('([\w-]+)'\)", self.app))
        self.assertTrue(ids)
        for name in sorted(ids):
            self.assertIn('id="%s"' % name, self.html, name)

    def test_news_blocks_share_the_column(self):
        right = self.html.split('<section class="right"', 1)[1].split('</main>', 1)[0]
        self.assertEqual(right.count('<section class="news'), 2)


if __name__ == '__main__':
    unittest.main()
