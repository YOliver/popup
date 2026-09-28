import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

import markdown
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])


class TestIndentRendering(unittest.TestCase):
    def _render(self, source, em_px):
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        normalized = MarkdownViewer._preserve_indent(source)
        body = md.convert(normalized)
        body = MarkdownViewer._apply_indent(body, em_px)
        html = MarkdownViewer.wrap_html(body)
        doc = QTextDocument()
        doc.setHtml(html)
        return doc

    def test_indented_paragraph_gets_text_indent(self):
        doc = self._render("\u3000\u3000正文", 14.0)
        found = False
        blk = doc.begin()
        while blk.isValid():
            if blk.text() == "正文":
                self.assertEqual(blk.blockFormat().textIndent(), 28.0)
                found = True
            blk = blk.next()
        self.assertTrue(found)

    def test_unindented_paragraph_has_no_indent(self):
        doc = self._render("正文", 14.0)
        blk = doc.begin()
        while blk.isValid():
            if blk.text() == "正文":
                self.assertEqual(blk.blockFormat().textIndent(), 0.0)
            blk = blk.next()

    def test_code_fence_content_preserved(self):
        doc = self._render("```\n\u3000\u3000code line\n```", 14.0)
        blk = doc.begin()
        found = False
        while blk.isValid():
            if "\u3000\u3000code line" in blk.text():
                self.assertEqual(blk.blockFormat().textIndent(), 0.0)
                found = True
            blk = blk.next()
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
