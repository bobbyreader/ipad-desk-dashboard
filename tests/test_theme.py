"""Theme tokens: one palette file must cover both themes and the canvas."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(text, selector):
    """Return the declarations inside a simple top-level CSS block."""
    match = re.search(re.escape(selector) + r'\s*\{(.*?)\n\}', text, re.S)
    return match.group(1) if match else ''


def tokens(text):
    return set(re.findall(r'(--[\w-]+)\s*:', text))


class ThemeTests(unittest.TestCase):
    """A day/night switch is only trustworthy if both palettes are complete."""

    def setUp(self):
        self.theme = (ROOT / 'theme.css').read_text()
        self.day = tokens(block(self.theme, ':root'))
        self.night = tokens(block(self.theme, ':root.night'))

    def test_both_themes_define_the_same_tokens(self):
        """A token missing from one theme would silently inherit the other."""
        self.assertTrue(self.day)
        self.assertEqual(self.day, self.night)

    def test_every_used_token_is_defined(self):
        """Catch a var(--x) typo that would render as an empty colour."""
        used = set()
        for name in ('style.css', 'network.css'):
            used |= set(re.findall(r'var\((--[\w-]+)\)', (ROOT / name).read_text()))
        script = (ROOT / 'network.js').read_text()
        used |= set(re.findall(r"read\('(--[\w-]+)'\)", script))
        self.assertTrue(used)
        self.assertEqual(sorted(used - self.day), [])

    def test_canvas_has_no_hardcoded_colours(self):
        """The map and chart must follow the active theme, not a frozen hex value."""
        script = (ROOT / 'network.js').read_text()
        self.assertEqual(re.findall(r'#[0-9a-fA-F]{3,8}', script), [])

    def test_theme_assets_and_switch(self):
        """theme.css loads before the sheets that use its tokens."""
        html = (ROOT / 'index.html').read_text()
        self.assertIn('id="theme-toggle"', html)
        self.assertIn('src="/theme-init.js"', html)
        self.assertLess(html.index('href="/theme.css"'), html.index('href="/style.css"'))
        self.assertTrue((ROOT / 'theme-init.js').is_file())


if __name__ == '__main__':
    unittest.main()
