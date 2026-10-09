import os

# 必须在 import PySide6 之前设置，否则 QApplication 会用默认平台插件
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer

from md_viewer import PIN_SVG_ON, PIN_SVG_OFF, _build_pin_icon

_app = QApplication.instance() or QApplication([])


class TestPinIcon(unittest.TestCase):
    def test_pin_svg_on_is_valid(self):
        renderer = QSvgRenderer(QByteArray(PIN_SVG_ON.encode("utf-8")))
        self.assertTrue(renderer.isValid())

    def test_pin_svg_off_is_valid(self):
        renderer = QSvgRenderer(QByteArray(PIN_SVG_OFF.encode("utf-8")))
        self.assertTrue(renderer.isValid())

    def test_build_pin_icon_not_null(self):
        self.assertFalse(_build_pin_icon().isNull())


if __name__ == "__main__":
    unittest.main()
