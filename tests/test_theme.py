import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import md_viewer

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


class TestApplyTheme(unittest.TestCase):
    def setUp(self):
        # 隔离构造副作用：不装全局键盘钩子、不把 pytest 参数当文件打开、不读写用户 QSettings
        patcher_hotkey = mock.patch("md_viewer.GlobalHotkey")
        patcher_hotkey.start()
        self.addCleanup(patcher_hotkey.stop)
        patcher_argv = mock.patch.object(sys, "argv", ["md_viewer.py"])
        patcher_argv.start()
        self.addCleanup(patcher_argv.stop)
        patcher_settings = mock.patch(
            "md_viewer.QSettings",
            return_value=mock.MagicMock(value=mock.MagicMock(return_value=False)),
        )
        patcher_settings.start()
        self.addCleanup(patcher_settings.stop)

        self.viewer = MarkdownViewer()
        self.addCleanup(self.viewer.close)
        self.style_hints = mock.MagicMock()
        patcher_hints = mock.patch.object(
            QApplication.instance(), "styleHints", return_value=self.style_hints
        )
        patcher_hints.start()
        self.addCleanup(patcher_hints.stop)
        self.orig_style = QApplication.instance().style().name()

    def test_apply_theme_toggles_dark_and_light(self):
        self.viewer.apply_theme(True)
        self.style_hints.setColorScheme.assert_called_with(Qt.ColorScheme.Dark)
        self.assertIn(DARK["toc_bg"], self.viewer.toc_tree.styleSheet())
        self.assertEqual(QApplication.instance().style().name(), self.orig_style)

        self.viewer.apply_theme(False)
        self.style_hints.setColorScheme.assert_called_with(Qt.ColorScheme.Light)
        self.assertIn(LIGHT["toc_bg"], self.viewer.toc_tree.styleSheet())

    def test_toggle_dark_mode_persists(self):
        self.viewer.toggle_dark_mode(True)
        md_viewer.QSettings.return_value.setValue.assert_called_with(
            "appearance/dark_mode", True
        )

    def test_dark_mode_restored_from_settings(self):
        def _value(key, default, type=None):
            return True if key == "appearance/dark_mode" else default
        md_viewer.QSettings.return_value.value.side_effect = _value
        viewer = md_viewer.MarkdownViewer()
        try:
            self.assertTrue(viewer._dark_mode)
            self.assertTrue(viewer.dark_action.isChecked())
        finally:
            viewer.close()


if __name__ == "__main__":
    unittest.main()
