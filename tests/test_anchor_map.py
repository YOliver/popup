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


def _long_doc():
    para = '很长的段落文字' * 40
    return _doc(''.join(
        '<p><a id="popup-anchor-%d"></a>%s</p>' % (i * 3, para) for i in range(3)))


class TestSplitAnchorMap(unittest.TestCase):
    def test_collect_matches_build(self):
        doc = _long_doc()
        lines, blocks = MarkdownViewer._collect_anchor_blocks(doc)
        self.assertEqual(lines, MarkdownViewer._build_anchor_map(doc)[0])
        self.assertEqual(lines, [0, 3, 6])
        self.assertEqual(len(blocks), len(lines))

    def test_block_ys_monotonic_when_blocks_reversed(self):
        doc = _long_doc()
        _, blocks = MarkdownViewer._collect_anchor_blocks(doc)
        ys = MarkdownViewer._anchor_block_ys(doc, list(reversed(blocks)))
        self.assertEqual(ys, sorted(ys))
        self.assertEqual(len(ys), 3)

    def test_recompute_ys_after_width_change_matches_full_build(self):
        doc = _long_doc()
        doc.setTextWidth(800)
        _, blocks = MarkdownViewer._collect_anchor_blocks(doc)
        wide = MarkdownViewer._anchor_block_ys(doc, blocks)
        doc.setTextWidth(200)
        narrow = MarkdownViewer._anchor_block_ys(doc, blocks)
        self.assertEqual(narrow, MarkdownViewer._build_anchor_map(doc)[1])
        self.assertNotEqual(narrow, wide)  # 确认宽度变化确实改变了 Y，测试有效


if __name__ == "__main__":
    unittest.main()
