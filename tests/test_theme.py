import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from md_viewer import (
    DARK,
    LIGHT,
    MarkdownViewer,
    _build_pin_icon,
    _search_input_qss,
)

_app = QApplication.instance() or QApplication([])


class TestThemePalette(unittest.TestCase):
    def test_light_dark_same_keys(self):
        self.assertEqual(set(LIGHT.keys()), set(DARK.keys()))

    def test_wrap_html_light_contains_existing_colors(self):
        html = MarkdownViewer.wrap_html("<p>x</p>", LIGHT)
        for needle in (
            "background: #fff",
            "color: #333",
            "color: #0366d6",
            "background: #f4f4f4",
            "background-color: #e8e8e8",
        ):
            self.assertIn(needle, html)

    def test_wrap_html_dark_uses_dark_colors(self):
        html = MarkdownViewer.wrap_html("<p>x</p>", DARK)
        self.assertIn(DARK["bg"], html)
        self.assertIn(DARK["fg"], html)
        self.assertNotIn("background: #fff", html)


class TestThemeQss(unittest.TestCase):
    def test_search_input_qss_error(self):
        qss = _search_input_qss(LIGHT, error=True)
        self.assertIn(LIGHT["error_border"], qss)

    def test_search_input_qss_normal(self):
        qss = _search_input_qss(LIGHT, error=False)
        self.assertIn(LIGHT["input_border"], qss)


class TestPinIconTheme(unittest.TestCase):
    def test_pin_icon_on_bright_in_dark(self):
        icon = _build_pin_icon(DARK["pin_on"])
        pixmap = icon.pixmap(16, 16, QIcon.Mode.Normal, QIcon.State.On)
        self.assertFalse(pixmap.isNull())
        image = pixmap.toImage()
        total = 0
        count = 0
        for x in range(image.width()):
            for y in range(image.height()):
                c = image.pixelColor(x, y)
                if c.alpha() > 0:
                    total += (c.red() + c.green() + c.blue()) / 3
                    count += 1
        self.assertGreater(count, 0)
        self.assertGreater(total / count, 128)


if __name__ == "__main__":
    unittest.main()
