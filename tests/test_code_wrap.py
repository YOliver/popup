import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

from PySide6.QtWidgets import QApplication, QTextBrowser

import markdown

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])

LONG_LINE = "这是一段很长的代码内容，用来测试自动折行行为。" * 20


def _render_code_block(width=300):
    """渲染含超长行的 <pre> 代码块，返回 QTextBrowser。"""
    body = f"<pre><code>{LONG_LINE}</code></pre>"
    tb = QTextBrowser()
    tb.resize(width, 600)
    tb.setHtml(MarkdownViewer.wrap_html(body))
    tb.document().setTextWidth(width)
    return tb


def _max_line_count(doc):
    """遍历所有 block，返回最大的视觉行数。"""
    max_lines = 0
    blk = doc.begin()
    while blk.isValid():
        layout = blk.layout()
        if layout is not None:
            max_lines = max(max_lines, layout.lineCount())
        blk = blk.next()
    return max_lines


def _render_via_pipeline(width=300):
    source = "```\n" + LONG_LINE + "\n```"
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
    )
    body = md.convert(source)
    tb = QTextBrowser()
    tb.resize(width, 600)
    tb.setHtml(MarkdownViewer.wrap_html(body))
    tb.document().setTextWidth(width)
    return tb


class TestCodeBlockWrap(unittest.TestCase):
    def test_long_code_line_has_no_horizontal_scroll(self):
        tb = _render_code_block()
        self.assertEqual(tb.horizontalScrollBar().maximum(), 0)

    def test_long_code_line_wraps_into_multiple_lines(self):
        tb = _render_code_block()
        self.assertGreater(_max_line_count(tb.document()), 1)

    def test_wrap_html_contains_pre_wrap(self):
        html = MarkdownViewer.wrap_html("<p>正文</p>")
        self.assertIn("white-space: pre-wrap", html)

    def test_fenced_code_block_wraps_via_markdown_pipeline(self):
        tb = _render_via_pipeline()
        self.assertEqual(tb.horizontalScrollBar().maximum(), 0)
        self.assertGreater(_max_line_count(tb.document()), 1)

    def test_soft_wrap_preserves_text_content(self):
        tb = _render_code_block()
        self.assertEqual(tb.toPlainText().strip(), LONG_LINE)


if __name__ == "__main__":
    unittest.main()
