import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

import markdown
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument, QTextTable, QTextTableCellFormat

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])


class TestQuoteRendering(unittest.TestCase):
    def test_quote_renders_as_styled_table(self):
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        body = md.convert("> quote text")
        body = MarkdownViewer._style_blockquotes(body)
        html = MarkdownViewer.wrap_html(body)

        doc = QTextDocument()
        doc.setHtml(html)

        tables = [c for c in doc.rootFrame().childFrames()
                  if isinstance(c, QTextTable)]
        self.assertEqual(len(tables), 1)

        fmt = tables[0].format()
        self.assertEqual(fmt.border(), 0.0)

        cell_fmt = QTextTableCellFormat(tables[0].cellAt(0, 0).format())
        self.assertEqual(cell_fmt.leftBorder(), 4.0)
        self.assertEqual(cell_fmt.topBorder(), 0.0)
        self.assertEqual(cell_fmt.rightBorder(), 0.0)
        self.assertEqual(cell_fmt.bottomBorder(), 0.0)
        self.assertEqual(cell_fmt.leftPadding(), 16.0)

        # 引用段落（p）的 block 背景为 #e8e8e8（table 背景 Qt 不渲染，改用段落背景）
        blk = doc.begin()
        found = False
        while blk.isValid():
            if blk.text() == "quote text":
                self.assertEqual(
                    blk.blockFormat().background().color().name(), "#e8e8e8"
                )
                found = True
            blk = blk.next()
        self.assertTrue(found)

    def test_table_inside_quote_not_affected(self):
        html_in = ("<blockquote><p>引用文字</p>"
                   "<table><tr><td>单元格</td></tr></table></blockquote>")
        body = MarkdownViewer._style_blockquotes(html_in)
        html = MarkdownViewer.wrap_html(body)

        doc = QTextDocument()
        doc.setHtml(html)

        tables = []

        def collect(frame):
            for c in frame.childFrames():
                if isinstance(c, QTextTable):
                    tables.append(c)
                    collect(c)

        collect(doc.rootFrame())

        self.assertEqual(len(tables), 2)

        outer = QTextTableCellFormat(tables[0].cellAt(0, 0).format())
        self.assertEqual(outer.leftBorder(), 4.0)
        self.assertEqual(outer.topBorder(), 0.0)

        inner = QTextTableCellFormat(tables[1].cellAt(0, 0).format())
        self.assertEqual(inner.topBorder(), 1.0)
        self.assertEqual(inner.bottomBorder(), 1.0)


if __name__ == "__main__":
    unittest.main()
