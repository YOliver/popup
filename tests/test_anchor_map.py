import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])


def _doc(body):
    doc = QTextDocument()
    doc.setHtml('<html><body>%s</body></html>' % body)
    return doc


class TestBuildAnchorMap(unittest.TestCase):
    def test_returns_lines_and_monotonic_ys(self):
        doc = _doc(
            '<p><a id="popup-anchor-0"></a>第一段</p>'
            '<p><a id="popup-anchor-2"></a>第二段</p>'
            '<p><a id="popup-anchor-5"></a>第三段</p>'
        )
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, [0, 2, 5])
        self.assertEqual(len(ys), 3)
        self.assertEqual(ys, sorted(ys))

    def test_ignores_non_md_anchors(self):
        doc = _doc('<h1 id="toc"><a id="popup-anchor-1"></a>标题</h1>')
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, [1])

    def test_empty_when_no_anchors(self):
        doc = _doc('<p>无锚点段落</p>')
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, [])
        self.assertEqual(ys, [])


if __name__ == "__main__":
    unittest.main()
